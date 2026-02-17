"""Extract mentioned values from web context and merge with customer distinct values using a single LLM call."""

import re
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage


EXTRACT_AND_MERGE_SYSTEM = """You are a precise assistant for electrical contactor data. You will receive:
1) An attribute name
2) Customer distinct values (from profiling)
3) Optional text from NEMA/IEC standards about this attribute
4) Optional text from manufacturer/vendor catalogs about this attribute

Your task: Extract every possible value or option mentioned for this attribute in the standards and manufacturers text. Then merge those with the customer values into one list. Remove duplicates (same meaning, different wording: keep one canonical form). Output ONLY the final merged list, exactly one value per line. No numbering, bullets, or headers. Use exact terms (codes, numbers, labels) as they appear."""


def extract_and_merge_values_via_llm(
    llm: BaseChatModel,
    attribute_name: str,
    customer_values: list[str],
    standards_context: str,
    manufacturers_context: str,
    dedup: bool = True,
    max_text_chars: int = 5000,
) -> list[str]:
    """
    Single LLM call: extract possible values from standards and manufacturers text, then merge with customer values (with optional dedup). Returns merged list.
    Falls back to customer_values only if both contexts are empty or LLM fails.
    """
    label = attribute_name.replace("zz_", "").strip()
    customer_block = "\n".join(f"  - {v!r}" for v in customer_values[:50]) if customer_values else "  (none)"
    if len(customer_values) > 50:
        customer_block += f"\n  ... and {len(customer_values) - 50} more"

    std_excerpt = (standards_context.strip()[:max_text_chars] + "...") if len(standards_context) > max_text_chars else standards_context.strip()
    mfr_excerpt = (manufacturers_context.strip()[:max_text_chars] + "...") if len(manufacturers_context) > max_text_chars else manufacturers_context.strip()

    has_std = bool(std_excerpt)
    has_mfr = bool(mfr_excerpt)
    if not has_std and not has_mfr:
        return list(customer_values) if customer_values else []

    user_parts = [
        f"Attribute: {label}",
        f"Deduplicate: {dedup}",
        "",
        "Customer distinct values:",
        customer_block,
        "",
    ]
    if has_std:
        user_parts.extend(["Standards (NEMA/IEC) text:", std_excerpt, ""])
    if has_mfr:
        user_parts.extend(["Manufacturers text:", mfr_excerpt, ""])
    user_parts.append("Output the merged list of possible values (one per line) for this attribute:")
    user_content = "\n".join(user_parts)

    messages = [
        SystemMessage(content=EXTRACT_AND_MERGE_SYSTEM),
        HumanMessage(content=user_content),
    ]
    try:
        response = llm.invoke(messages)
        content = getattr(response, "content", "") or str(response)
    except Exception:
        return merge_possible_values(customer_values, [], [], dedup=dedup)

    values = []
    for line in content.splitlines():
        line = line.strip()
        line = re.sub(r"^[\d\.\)\-]\s*", "", line).strip()
        if line and len(line) < 500:
            values.append(line)
    if not values:
        return merge_possible_values(customer_values, [], [], dedup=dedup)
    return values


def merge_possible_values(
    customer_values: list[str],
    values_from_standards: list[str],
    values_from_manufacturers: list[str],
    dedup: bool = True,
) -> list[str]:
    """
    Merge customer distinct values with extracted values from standards and manufacturers.
    If dedup is True, deduplicate by normalised form (strip, case-insensitive); order is preserved (first occurrence kept).
    """
    merged: list[str] = []
    seen_normalized: set[str] = set()

    def add(v: str) -> None:
        s = (v or "").strip()
        if not s:
            return
        if dedup:
            key = s.lower()
            if key in seen_normalized:
                return
            seen_normalized.add(key)
        merged.append(s)

    for v in customer_values:
        add(str(v).strip() if v is not None else "")
    for v in values_from_standards:
        add(v)
    for v in values_from_manufacturers:
        add(v)
    return merged


def get_customer_values_from_attribute(attribute: dict[str, Any], max_n: int = 50) -> list[str]:
    """Get list of distinct value strings from the profiling attribute (value -> count)."""
    values = attribute.get("values") or []
    result = []
    for item in values[:max_n]:
        val = item.get("value")
        if val is None:
            continue
        s = str(val).strip()
        if s:
            result.append(s)
    return result
