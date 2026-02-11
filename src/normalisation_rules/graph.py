"""LangGraph workflow: Tavily context -> LLM -> parse rules."""

from datetime import datetime, timezone
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel
from langgraph.graph import StateGraph, END, START

from normalisation_rules.prompts import SYSTEM_PROMPT, build_user_prompt
from normalisation_rules.state import RuleDerivationState
from normalisation_rules.tavily_context import search_attribute_context


def _fetch_context_node(state: RuleDerivationState) -> dict:
    """Fetch web context for the current attribute using Tavily (if use_tavily is True)."""
    if not state.get("use_tavily", True):
        return {"web_context": "", "error": ""}
    attr = state.get("current_attribute") or {}
    name = attr.get("name", "")
    search_depth = state.get("search_depth", "basic")

    # Extract top sample values for better query targeting
    values = attr.get("values") or []
    sample_values = [str(v.get("value", "")) for v in values[:5] if v.get("value")]

    print(f"  [Tavily] Using web search for attribute: {name} (depth={search_depth})")
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
        n_chars = len(context)
        print(f"  [Tavily] Returned {n_chars} chars of context")
        log_path = state.get("tavily_log_path")
        if log_path and isinstance(log_path, str):
            path = Path(log_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            block = f"\n{'='*60}\n[{ts}] Attribute: {name}\nQuery: {query_used}\n\n{context}\n"
            with open(path, "a", encoding="utf-8") as f:
                f.write(block)
    except Exception as e:
        print(f"  [Tavily] Error: {e}")
        return {"web_context": "", "error": str(e)}
    return {"web_context": context, "error": ""}


def _derive_rules_node(state: RuleDerivationState, llm: BaseChatModel) -> dict:
    """Call LLM to derive normalisation rules for current attribute."""
    attr = state.get("current_attribute") or {}
    web_context = state.get("web_context", "")
    few_shot = state.get("few_shot_examples", "")
    domain = state.get("domain", "Contactors")

    user_text = build_user_prompt(attr, web_context, few_shot, domain)
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
    Build the LangGraph: START -> fetch_context -> derive_rules -> END.
    """
    graph = StateGraph(RuleDerivationState)

    def fetch_context(state: RuleDerivationState) -> dict:
        return _fetch_context_node(state)

    def derive_rules(state: RuleDerivationState) -> dict:
        return _derive_rules_node(state, llm)

    graph.add_node("fetch_context", fetch_context)
    graph.add_node("derive_rules", derive_rules)

    graph.add_edge(START, "fetch_context")
    graph.add_edge("fetch_context", "derive_rules")
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
) -> list[str]:
    """
    Run the graph for a single attribute (fetch Tavily context then derive rules). Returns list of rule lines.
    """
    compiled = build_rule_derivation_graph(llm).compile()
    initial: RuleDerivationState = {
        "current_attribute": attribute,
        "web_context": "",
        "few_shot_examples": few_shot_examples,
        "domain": domain,
        "use_tavily": use_tavily,
        "search_depth": search_depth,
        "tavily_log_path": tavily_log_path or "",
        "rules": [],
    }
    result = compiled.invoke(initial)
    return result.get("rules") or []
