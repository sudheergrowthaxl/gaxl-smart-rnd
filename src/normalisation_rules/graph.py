"""LangGraph workflow: Tavily context (standards + manufacturers) -> extract values -> merge -> LLM -> parse rules."""

from datetime import datetime, timezone
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel
from langgraph.graph import StateGraph, END, START

from normalisation_rules.curation import (
    extract_and_merge_values_via_llm,
    get_customer_values_from_attribute,
    merge_possible_values,
)
from normalisation_rules.prompts import SYSTEM_PROMPT, build_user_prompt
from normalisation_rules.state import RuleDerivationState
from normalisation_rules.tavily_context import search_standards_context, search_manufacturers_context


def _fetch_context_node(state: RuleDerivationState) -> dict:
    """Fetch web context from Tavily: standards (NEMA/IEC) and manufacturers (if use_tavily)."""
    if not state.get("use_tavily", True):
        return {
            "web_context": "",
            "standards_context": "",
            "manufacturers_context": "",
            "error": "",
        }
    attr = state.get("current_attribute") or {}
    name = attr.get("name", "")
    log_path = state.get("tavily_log_path") or ""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    standards_context = ""
    manufacturers_context = ""
    try:
        print(f"  [Tavily] Standards (NEMA/IEC) for attribute: {name}")
        standards_context, std_query = search_standards_context(
            attribute_name=name,
            domain="electrical contactors",
            max_results=5,
            max_content_chars=6000,
        )
        print(f"  [Tavily] Standards returned {len(standards_context)} chars")
        if log_path:
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*60}\n[{ts}] Attribute: {name}\n[Standards] Query: {std_query}\n\n{standards_context}\n")
    except Exception as e:
        print(f"  [Tavily] Standards error: {e}")
        standards_context = ""

    try:
        print(f"  [Tavily] Manufacturers for attribute: {name}")
        manufacturers_context, mfr_query = search_manufacturers_context(
            attribute_name=name,
            domain="electrical contactors",
            max_results=5,
            max_content_chars=6000,
        )
        print(f"  [Tavily] Manufacturers returned {len(manufacturers_context)} chars")
        if log_path:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n---\n[Manufacturers] Query: {mfr_query}\n\n{manufacturers_context}\n")
    except Exception as e:
        print(f"  [Tavily] Manufacturers error: {e}")
        manufacturers_context = ""

    web_context = (standards_context + "\n\n" + manufacturers_context).strip()
    return {
        "web_context": web_context,
        "standards_context": standards_context,
        "manufacturers_context": manufacturers_context,
        "error": "",
    }


def _extract_and_merge_node(state: RuleDerivationState, llm: BaseChatModel) -> dict:
    """Single AI call: extract values from standards and manufacturers text and merge with customer values."""
    attr = state.get("current_attribute") or {}
    standards_context = state.get("standards_context") or ""
    manufacturers_context = state.get("manufacturers_context") or ""
    dedup = state.get("dedup_merged_values", True)
    name = attr.get("name", "")

    customer_values = get_customer_values_from_attribute(attr)

    if standards_context.strip() or manufacturers_context.strip():
        try:
            merged = extract_and_merge_values_via_llm(
                llm,
                attribute_name=name,
                customer_values=customer_values,
                standards_context=standards_context,
                manufacturers_context=manufacturers_context,
                dedup=dedup,
                max_text_chars=5000,
            )
            print(f"  [AI merge] Merged possible values: {len(merged)} (dedup={dedup})")
        except Exception as e:
            print(f"  [AI merge] Error: {e}, using customer values only")
            merged = merge_possible_values(customer_values, [], [], dedup=dedup)
    else:
        merged = merge_possible_values(customer_values, [], [], dedup=dedup)
        print(f"  [Merge] Customer values only: {len(merged)}")

    # Log curated/merged list to the same Tavily log file
    log_path = state.get("tavily_log_path") or ""
    if log_path:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n---\n[Curated merged values] Attribute: {name} (dedup={dedup}, count={len(merged)})\n")
                f.write(f"[{ts}]\n\n")
                for v in merged:
                    f.write(f"  {v}\n")
                f.write("\n")
        except Exception as e:
            print(f"  [Log] Could not write curated list: {e}")

    return {"merged_possible_values": merged}


def _derive_rules_node(state: RuleDerivationState, llm: BaseChatModel) -> dict:
    """Call LLM to derive normalisation rules for current attribute using merged possible values."""
    attr = state.get("current_attribute") or {}
    few_shot = state.get("few_shot_examples", "")
    domain = state.get("domain", "Contactors")
    merged_possible_values = state.get("merged_possible_values") or []
    standards_context = state.get("standards_context") or ""
    manufacturers_context = state.get("manufacturers_context") or ""

    user_text = build_user_prompt(
        attr,
        few_shot_examples=few_shot,
        domain=domain,
        merged_possible_values=merged_possible_values,
        standards_context=standards_context,
        manufacturers_context=manufacturers_context,
    )
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_text),
    ]
    try:
        response = llm.invoke(messages)
        content = getattr(response, "content", "") or str(response)
    except Exception as e:
        return {"rules": [], "error": str(e)}

    # Parse rule lines: Entity\tAttribute\tNormalization\tRule
    lines = [s.strip() for s in content.splitlines() if s.strip()]
    rules = []
    for line in lines:
        if "\t" in line:
            rules.append(line)
        elif line.startswith(domain) or "Normalization" in line:
            rules.append(line)

    # Cap at 6 rules per attribute (safety net if LLM over-generates)
    max_rules_per_attribute = 6
    if len(rules) > max_rules_per_attribute:
        rules = rules[:max_rules_per_attribute]

    return {"rules": rules, "error": ""}


def build_rule_derivation_graph(llm: BaseChatModel) -> StateGraph:
    """
    Build the LangGraph: START -> fetch_context -> extract_and_merge -> derive_rules -> END.
    """
    graph = StateGraph(RuleDerivationState)

    def fetch_context(state: RuleDerivationState) -> dict:
        return _fetch_context_node(state)

    def extract_and_merge(state: RuleDerivationState) -> dict:
        return _extract_and_merge_node(state, llm)

    def derive_rules(state: RuleDerivationState) -> dict:
        return _derive_rules_node(state, llm)

    graph.add_node("fetch_context", fetch_context)
    graph.add_node("extract_and_merge", extract_and_merge)
    graph.add_node("derive_rules", derive_rules)

    graph.add_edge(START, "fetch_context")
    graph.add_edge("fetch_context", "extract_and_merge")
    graph.add_edge("extract_and_merge", "derive_rules")
    graph.add_edge("derive_rules", END)

    return graph


def run_for_attribute(
    llm: BaseChatModel,
    attribute: dict,
    few_shot_examples: str,
    domain: str = "Contactors",
    use_tavily: bool = True,
    tavily_log_path: str | None = None,
    dedup_merged_values: bool = True,
) -> list[str]:
    """
    Run the graph for a single attribute: fetch Tavily (standards + manufacturers), extract values, merge with customer values, derive rules. Returns list of rule lines.
    """
    compiled = build_rule_derivation_graph(llm).compile()
    initial: RuleDerivationState = {
        "current_attribute": attribute,
        "web_context": "",
        "standards_context": "",
        "manufacturers_context": "",
        "merged_possible_values": [],
        "dedup_merged_values": dedup_merged_values,
        "few_shot_examples": few_shot_examples,
        "domain": domain,
        "use_tavily": use_tavily,
        "tavily_log_path": tavily_log_path or "",
        "rules": [],
    }
    result = compiled.invoke(initial)
    return result.get("rules") or []
