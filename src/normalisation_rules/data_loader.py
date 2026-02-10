"""Load Contactors profiling JSON and extract attributes suitable for normalisation rules."""

from pathlib import Path
import json
from typing import Any

# Attributes we prioritise (match Few_Shot_Examples and domain)
PRIORITY_ZZ_ATTRS = {
    "zz_Auxiliary Contact",
    "zz_Number of Poles",
    "zz_Mounting Type",
    "zz_Type",
}

# Semantic types to skip for rule derivation
SKIP_SEMANTIC_TYPES = {"Empty/NA", "ID", "Constant"}

# Max distinct/top values to include per attribute (avoid huge payloads)
MAX_VALUES_PER_ATTR = 50


def load_profiling_json(path: Path) -> dict[str, Any]:
    """Load the Contactors profiling distinct values JSON."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _get_values_for_attr(attr_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Get list of value/count dicts: prefer distinct_values, else top_values, capped."""
    raw = attr_data.get("distinct_values") or attr_data.get("top_values") or []
    if not isinstance(raw, list):
        return []
    return raw[:MAX_VALUES_PER_ATTR]


def _is_useful_for_rules(attr_name: str, attr_data: dict[str, Any]) -> bool:
    """Decide if this attribute is useful for deriving normalisation rules."""
    if not attr_name.startswith("zz_"):
        return False
    semantic = (attr_data.get("semantic_type") or "").strip()
    if semantic in SKIP_SEMANTIC_TYPES:
        return False
    values = _get_values_for_attr(attr_data)
    return len(values) > 0


def extract_attributes_for_rules(
    profiling: dict[str, Any],
    *,
    only_priority: bool = False,
) -> list[dict[str, Any]]:
    """
    Extract attribute summaries for rule derivation.
    Returns list of dicts: name, datatype, semantic_type, missing_percentage, range, values (value/count).
    """
    result = []
    for attr_name, attr_data in profiling.items():
        if not isinstance(attr_data, dict):
            continue
        if only_priority and attr_name not in PRIORITY_ZZ_ATTRS:
            continue
        if not _is_useful_for_rules(attr_name, attr_data):
            continue
        values = _get_values_for_attr(attr_data)
        result.append({
            "name": attr_name,
            "datatype": attr_data.get("datatype"),
            "semantic_type": attr_data.get("semantic_type"),
            "missing_percentage": attr_data.get("missing_percentage"),
            "range": attr_data.get("range"),
            "values": values,
        })
    # Put priority attributes first
    def order_key(a: dict) -> tuple[int, str]:
        name = a["name"]
        if name in PRIORITY_ZZ_ATTRS:
            idx = list(PRIORITY_ZZ_ATTRS).index(name)
            return (0, str(idx))
        return (1, name)

    result.sort(key=order_key)
    return result
