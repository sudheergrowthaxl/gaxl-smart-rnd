"""Validate derived normalisation rules against manufacturer datasheets."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from normalisation_rules.tavily_context import get_tavily_client, should_skip_tavily
from normalisation_rules.config import TAVILY_API_KEY
from normalisation_rules.prompts import (
    VALIDATION_SYSTEM_PROMPT,
    build_validation_prompt,
    FEW_SHOT_EXAMPLES_SYSTEM_PROMPT,
    build_few_shot_examples_prompt,
)


# Major contactor manufacturers for targeted datasheet search
_TARGET_MANUFACTURERS = ["Schneider Electric", "Siemens", "ABB", "Eaton"]


def search_datasheet_context(
    attribute_name: str,
    domain: str = "electrical contactors",
    max_results: int = 8,
    max_content_chars: int = 12000,
    search_depth: str = "advanced",
) -> tuple[str, str]:
    """
    Search for manufacturer datasheet information about an attribute.

    Returns (context_string, query_used).
    """
    if not TAVILY_API_KEY:
        return ("", "")

    if should_skip_tavily(attribute_name):
        return ("", f"(skipped: '{attribute_name}' not suitable for datasheet search)")

    client = get_tavily_client()
    label = attribute_name.replace("zz_", "").strip()

    manufacturers = " ".join(_TARGET_MANUFACTURERS)
    query = (
        f"{manufacturers} {domain} datasheet "
        f"'{label}' specifications standard values accepted ranges"
    )

    if search_depth == "advanced":
        max_results = max(max_results, 10)
        max_content_chars = max(max_content_chars, 15000)

    try:
        response = client.search(
            query=query,
            search_depth=search_depth,
            max_results=max_results,
            include_answer=True,
        )
    except Exception:
        return ("", query)

    parts: list[str] = []
    if response.get("answer"):
        parts.append(response["answer"])
    for r in (response.get("results") or [])[:max_results]:
        content = (r.get("content") or "").strip()
        url = (r.get("url") or "").strip()
        if content:
            if len(content) > 1500:
                content = content[:1500] + "..."
            source_line = f"[Source: {url}]" if url else ""
            parts.append(f"{content}\n{source_line}")

    combined = "\n\n".join(parts)
    if len(combined) > max_content_chars:
        combined = combined[:max_content_chars] + "..."
    return (combined.strip(), query)


def validate_rules(
    rules: list[str],
    attribute_name: str,
    datasheet_context: str,
    llm: BaseChatModel,
) -> list[tuple[str, str]]:
    """
    Validate a list of rules for one attribute against datasheet context.

    Returns list of (status, notes) tuples — one per input rule.
    Status is one of: "Valid", "Invalid", "Needs Review".
    """
    if not rules:
        return []

    user_text = build_validation_prompt(rules, attribute_name, datasheet_context)
    messages = [
        SystemMessage(content=VALIDATION_SYSTEM_PROMPT),
        HumanMessage(content=user_text),
    ]

    try:
        response = llm.invoke(messages)
        content = getattr(response, "content", "") or str(response)
    except Exception as e:
        return [("Error", f"LLM error: {e}")] * len(rules)

    # Parse response: expect one line per rule with Status\tNotes
    result_lines = [s.strip() for s in content.splitlines() if s.strip()]
    results: list[tuple[str, str]] = []
    valid_statuses = {"Valid", "Invalid", "Needs Review"}

    for line in result_lines:
        if "\t" in line:
            parts = line.split("\t", 1)
            status = parts[0].strip()
            notes = parts[1].strip() if len(parts) > 1 else ""
            if status not in valid_statuses:
                # Try to recover: treat whole line as notes
                results.append(("Needs Review", line))
            else:
                results.append((status, notes))
        elif any(line.startswith(s) for s in valid_statuses):
            # Handle cases where separator is missing
            for s in valid_statuses:
                if line.startswith(s):
                    notes = line[len(s):].strip().lstrip(":|-–").strip()
                    results.append((s, notes))
                    break
        # Skip non-result lines (preamble, etc.)

    # Pad or truncate to match number of input rules
    while len(results) < len(rules):
        results.append(("Needs Review", "Could not parse validation result"))
    results = results[: len(rules)]

    return results


def run_validation(
    rules_by_attribute: dict[str, list[dict]],
    llm: BaseChatModel,
    domain: str = "electrical contactors",
    search_depth: str = "advanced",
    log_path: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """
    Run validation on grouped rules.

    Parameters
    ----------
    rules_by_attribute : dict mapping attribute name -> list of rule dicts
        Each rule dict has keys: entity, attribute, normalization, description, reference
    llm : LangChain LLM instance
    domain : domain string for Tavily search
    search_depth : Tavily search depth
    log_path : optional path to log Tavily responses
    limit : optional max number of attributes to validate

    Returns
    -------
    List of rule dicts with added 'validation' and 'validation_notes' keys.
    """
    all_validated: list[dict] = []
    attr_names = list(rules_by_attribute.keys())
    if limit:
        attr_names = attr_names[:limit]

    for i, attr_name in enumerate(attr_names):
        attr_rules = rules_by_attribute[attr_name]
        rule_descriptions = [r["description"] for r in attr_rules]

        print(f"  [{i + 1}/{len(attr_names)}] Validating: {attr_name} ({len(attr_rules)} rules)")

        # Search for manufacturer datasheet context
        print(f"    [Tavily] Searching datasheets for: {attr_name}")
        context, query_used = search_datasheet_context(
            attribute_name=attr_name,
            domain=domain,
            search_depth=search_depth,
        )
        n_chars = len(context)
        print(f"    [Tavily] Returned {n_chars} chars of datasheet context")

        # Log Tavily response
        if log_path:
            path = Path(log_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            block = (
                f"\n{'=' * 60}\n[{ts}] Validation - Attribute: {attr_name}\n"
                f"Query: {query_used}\n\n{context}\n"
            )
            with open(path, "a", encoding="utf-8") as f:
                f.write(block)

        # Validate rules against datasheet context
        validation_results = validate_rules(
            rules=rule_descriptions,
            attribute_name=attr_name,
            datasheet_context=context,
            llm=llm,
        )

        for rule, (status, notes) in zip(attr_rules, validation_results):
            validated_rule = {**rule, "validation": status, "validation_notes": notes}
            all_validated.append(validated_rule)
            print(f"    -> [{status}] {notes[:80]}{'...' if len(notes) > 80 else ''}")

    return all_validated


# ---------------------------------------------------------------------------
# Few-shot examples generation
# ---------------------------------------------------------------------------


def generate_few_shot_examples(
    rules: list[str],
    attribute_name: str,
    datasheet_context: str,
    llm: BaseChatModel,
) -> list[str]:
    """
    Generate few-shot examples (positive + negative) for each rule.

    Returns list of example strings — one per input rule.
    """
    if not rules:
        return []

    user_text = build_few_shot_examples_prompt(rules, attribute_name, datasheet_context)
    messages = [
        SystemMessage(content=FEW_SHOT_EXAMPLES_SYSTEM_PROMPT),
        HumanMessage(content=user_text),
    ]

    try:
        response = llm.invoke(messages)
        content = getattr(response, "content", "") or str(response)
    except Exception as e:
        return [f"Error generating examples: {e}"] * len(rules)

    # Parse: one line per rule with [+] and [-] examples
    result_lines = [s.strip() for s in content.splitlines() if s.strip()]
    # Filter to lines that actually contain examples
    examples = [line for line in result_lines if "[+]" in line or "[-]" in line]

    # Pad or truncate to match number of input rules
    while len(examples) < len(rules):
        examples.append("No examples generated")
    examples = examples[: len(rules)]

    return examples


def run_few_shot_generation(
    rules_by_attribute: dict[str, list[dict]],
    llm: BaseChatModel,
    domain: str = "electrical contactors",
    search_depth: str = "advanced",
    log_path: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """
    Generate few-shot examples for grouped rules.

    Parameters
    ----------
    rules_by_attribute : dict mapping attribute name -> list of rule dicts
    llm : LangChain LLM instance
    domain : domain string for Tavily search
    search_depth : Tavily search depth
    log_path : optional path to log Tavily responses
    limit : optional max number of attributes to process

    Returns
    -------
    List of rule dicts with added 'few_shot_examples' key.
    """
    all_results: list[dict] = []
    attr_names = list(rules_by_attribute.keys())
    if limit:
        attr_names = attr_names[:limit]

    for i, attr_name in enumerate(attr_names):
        attr_rules = rules_by_attribute[attr_name]
        rule_descriptions = [r["description"] for r in attr_rules]

        print(f"  [{i + 1}/{len(attr_names)}] Generating examples: {attr_name} ({len(attr_rules)} rules)")

        # Search for manufacturer datasheet context (for realistic values)
        print(f"    [Tavily] Searching datasheets for: {attr_name}")
        context, query_used = search_datasheet_context(
            attribute_name=attr_name,
            domain=domain,
            search_depth=search_depth,
        )
        n_chars = len(context)
        print(f"    [Tavily] Returned {n_chars} chars of datasheet context")

        # Log Tavily response
        if log_path:
            path = Path(log_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            block = (
                f"\n{'=' * 60}\n[{ts}] Few-shot Examples - Attribute: {attr_name}\n"
                f"Query: {query_used}\n\n{context}\n"
            )
            with open(path, "a", encoding="utf-8") as f:
                f.write(block)

        # Generate few-shot examples
        examples = generate_few_shot_examples(
            rules=rule_descriptions,
            attribute_name=attr_name,
            datasheet_context=context,
            llm=llm,
        )

        for rule, ex in zip(attr_rules, examples):
            enriched_rule = {**rule, "few_shot_examples": ex}
            all_results.append(enriched_rule)
            print(f"    -> {ex[:100]}{'...' if len(ex) > 100 else ''}")

    return all_results
