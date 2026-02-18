"""LangGraph workflow: Tavily context (standards + manufacturers) -> curate values -> LLM -> parse rules."""

from datetime import datetime, timezone
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel
from langgraph.graph import StateGraph, END, START

from normalisation_rules.config import DEFAULT_MANUFACTURERS
from normalisation_rules.prompts import SYSTEM_PROMPT, build_user_prompt
from normalisation_rules.state import RuleDerivationState
from normalisation_rules.tavily_context import search_attribute_context, search_manufacturer_values
from normalisation_rules.curate_values import curate_possible_values


def _log_tavily_result(state: RuleDerivationState, name: str, query_used: str, context: str, label: str) -> None:
    """Write a Tavily result block to the shared log file."""
    log_path = state.get("tavily_log_path")
    if log_path and isinstance(log_path, str):
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        block = f"\n{'='*60}\n[{ts}] [{label}] Attribute: {name}\nQuery: {query_used}\n\n{context}\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(block)


def _fetch_context_node(state: RuleDerivationState) -> dict:
    """Fetch standards web context for the current attribute using Tavily."""
    if not state.get("use_tavily", True):
        return {"web_context": "", "error": ""}
    attr = state.get("current_attribute") or {}
    name = attr.get("name", "")
    search_depth = state.get("search_depth", "basic")

    # Extract top sample values for better query targeting
    values = attr.get("values") or []
    sample_values = [str(v.get("value", "")) for v in values[:5] if v.get("value")]

    print(f"  [Tavily/Standards] Searching for attribute: {name} (depth={search_depth})")
    context = ""
    query_used = ""
    try:
        context, query_used = search_attribute_context(
            attribute_name=name,
            domain="electrical contactors",
            max_results=5,
            max_content_chars=6000,
            search_depth=search_depth,
            sample_values=sample_values,
        )
        print(f"  [Tavily/Standards] Returned {len(context)} chars of context")
        _log_tavily_result(state, name, query_used, context, "Standards")
    except Exception as e:
        print(f"  [Tavily/Standards] Error: {e}")
        return {"web_context": "", "error": str(e)}
    return {"web_context": context, "error": ""}


def _fetch_manufacturer_context_node(state: RuleDerivationState) -> dict:
    """Fetch manufacturer catalog context for the current attribute using Tavily."""
    if not state.get("use_tavily", True):
        return {"manufacturer_context": "", "error": ""}
    attr = state.get("current_attribute") or {}
    name = attr.get("name", "")
    search_depth = state.get("search_depth", "basic")
    manufacturers = state.get("manufacturers") or DEFAULT_MANUFACTURERS

    # Extract top sample values for better query targeting
    values = attr.get("values") or []
    sample_values = [str(v.get("value", "")) for v in values[:5] if v.get("value")]

    print(f"  [Tavily/Manufacturer] Searching for attribute: {name} (manufacturers: {len(manufacturers)})")
    context = ""
    query_used = ""
    try:
        context, query_used = search_manufacturer_values(
            attribute_name=name,
            manufacturers=manufacturers,
            domain="electrical contactors",
            max_results=5,
            max_content_chars=6000,
            search_depth=search_depth,
            sample_values=sample_values,
        )
        print(f"  [Tavily/Manufacturer] Returned {len(context)} chars of context")
        _log_tavily_result(state, name, query_used, context, "Manufacturer")
    except Exception as e:
        print(f"  [Tavily/Manufacturer] Error: {e}")
        return {"manufacturer_context": "", "error": str(e)}
    return {"manufacturer_context": context, "error": ""}


def _curate_values_node(state: RuleDerivationState) -> dict:
    """Combine customer data, standards context, and manufacturer context into curated values."""
    attr = state.get("current_attribute") or {}
    name = attr.get("name", "")
    standards_context = state.get("web_context", "")
    manufacturer_context = state.get("manufacturer_context", "")

    curated = curate_possible_values(
        attribute=attr,
        standards_context=standards_context,
        manufacturer_context=manufacturer_context,
    )
    combined = curated.get("combined_context", "")
    n_customer = len(curated.get("customer_values", []))
    print(f"  [Curate] {name}: {n_customer} customer values, "
          f"standards={len(standards_context)} chars, manufacturer={len(manufacturer_context)} chars")
    return {"curated_values": combined, "error": ""}


def _derive_rules_node(state: RuleDerivationState, llm: BaseChatModel) -> dict:
    """Call LLM to derive normalisation rules for current attribute."""
    attr = state.get("current_attribute") or {}
    curated_values = state.get("curated_values", "")
    few_shot = state.get("few_shot_examples", "")
    domain = state.get("domain", "Contactors")

    user_text = build_user_prompt(attr, curated_values, few_shot, domain)
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

    # Cap at 3 rules per attribute (safety net if LLM over-generates)
    max_rules_per_attribute = 3
    if len(rules) > max_rules_per_attribute:
        rules = rules[:max_rules_per_attribute]

    return {"rules": rules, "error": ""}


def build_rule_derivation_graph(llm: BaseChatModel) -> StateGraph:
    """
    Build the LangGraph:
    START -> fetch_context -> fetch_manufacturer_context -> curate_values -> derive_rules -> END
    """
    graph = StateGraph(RuleDerivationState)

    def fetch_context(state: RuleDerivationState) -> dict:
        return _fetch_context_node(state)

    def fetch_manufacturer_context(state: RuleDerivationState) -> dict:
        return _fetch_manufacturer_context_node(state)

    def curate_values(state: RuleDerivationState) -> dict:
        return _curate_values_node(state)

    def derive_rules(state: RuleDerivationState) -> dict:
        return _derive_rules_node(state, llm)

    graph.add_node("fetch_context", fetch_context)
    graph.add_node("fetch_manufacturer_context", fetch_manufacturer_context)
    graph.add_node("curate_values", curate_values)
    graph.add_node("derive_rules", derive_rules)

    graph.add_edge(START, "fetch_context")
    graph.add_edge("fetch_context", "fetch_manufacturer_context")
    graph.add_edge("fetch_manufacturer_context", "curate_values")
    graph.add_edge("curate_values", "derive_rules")
    graph.add_edge("derive_rules", END)

    return graph


def run_for_attribute(
    llm: BaseChatModel,
    attribute: dict,
    few_shot_examples: str,
    domain: str = "Contactors",
    use_tavily: bool = True,
    tavily_log_path: str | None = None,
    search_depth: str = "basic",
    manufacturers: list[str] | None = None,
) -> tuple[list[str], dict]:
    """
    Run the graph for a single attribute. Returns (list_of_rule_lines, curated_values_dict).

    The curated_values_dict contains the structured data from all three sources,
    which can be collected and saved to a JSON file for review.
    """
    compiled = build_rule_derivation_graph(llm).compile()
    initial: RuleDerivationState = {
        "current_attribute": attribute,
        "web_context": "",
        "manufacturer_context": "",
        "curated_values": "",
        "few_shot_examples": few_shot_examples,
        "domain": domain,
        "use_tavily": use_tavily,
        "search_depth": search_depth,
        "tavily_log_path": tavily_log_path or "",
        "manufacturers": manufacturers or DEFAULT_MANUFACTURERS,
        "rules": [],
    }
    result = compiled.invoke(initial)

    # Rebuild the curated dict for saving (the combined_context is in state, but we
    # also want the structured breakdown for the JSON export)
    curated_dict = curate_possible_values(
        attribute=attribute,
        standards_context=result.get("web_context", ""),
        manufacturer_context=result.get("manufacturer_context", ""),
    )

    return result.get("rules") or [], curated_dict
