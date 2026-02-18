"""Curate possible values from customer data, standards, and manufacturer sources."""

import json
from pathlib import Path
from typing import Any


def curate_possible_values(
    attribute: dict[str, Any],
    standards_context: str,
    manufacturer_context: str,
) -> dict[str, Any]:
    """
    Combine customer profiling values, standards context, and manufacturer context
    into a single curated dict for an attribute.

    Parameters
    ----------
    attribute : dict
        Attribute dict from data_loader (has 'name', 'values' with value/count pairs, etc.)
    standards_context : str
        Summary text from Tavily standards search.
    manufacturer_context : str
        Summary text from Tavily manufacturer catalog search.

    Returns
    -------
    dict with keys: attribute, customer_values, standards_context, manufacturer_context, combined_context
    """
    name = attribute.get("name", "")
    values = attribute.get("values") or []

    # Extract customer observed values as a flat list (ordered by count, descending)
    customer_values = [str(v.get("value", "")) for v in values if v.get("value")]

    # Build a formatted combined context string for the LLM prompt
    sections = []

    # Section 1: Customer observed values (structured list)
    if customer_values:
        val_lines = "\n".join(f"  - {v}" for v in customer_values[:30])
        sections.append(f"Customer observed values ({len(customer_values)} distinct):\n{val_lines}")
        if len(customer_values) > 30:
            sections[-1] += f"\n  ... and {len(customer_values) - 30} more."

    # Section 2: Standards context (summary)
    if standards_context.strip():
        sections.append(f"Standards context (IEC/NEMA):\n{standards_context.strip()}")

    # Section 3: Manufacturer catalog context (summary)
    if manufacturer_context.strip():
        sections.append(f"Manufacturer catalog values:\n{manufacturer_context.strip()}")

    combined_context = "\n\n".join(sections) if sections else ""

    return {
        "attribute": name,
        "customer_values": customer_values,
        "standards_context": standards_context.strip(),
        "manufacturer_context": manufacturer_context.strip(),
        "combined_context": combined_context,
    }


def save_curated_values(
    all_curated: list[dict[str, Any]],
    path: Path,
) -> None:
    """
    Save all curated values (one dict per attribute) to a JSON file.

    Parameters
    ----------
    all_curated : list of dicts from curate_possible_values()
    path : output JSON file path
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write without the combined_context field (it's large and redundant for review)
    output = []
    for entry in all_curated:
        output.append({
            "attribute": entry.get("attribute", ""),
            "customer_values": entry.get("customer_values", []),
            "standards_context": entry.get("standards_context", ""),
            "manufacturer_context": entry.get("manufacturer_context", ""),
        })

    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
