"""Load derived rules from Excel and group by Attribute."""

from pathlib import Path
from typing import Any

import pandas as pd


def load_rules_excel(path: Path) -> pd.DataFrame:
    """Load the rules workbook (sheet 'Normalisation Rules'). Expects columns Entity, Attribute, Normalization, Rule description, Reference."""
    if not path.exists():
        raise FileNotFoundError(f"Rules file not found: {path}")
    df = pd.read_excel(path, sheet_name="Normalisation Rules", engine="openpyxl")
    required = {"Entity", "Attribute", "Normalization", "Rule description"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Rules Excel missing columns: {missing}. Found: {list(df.columns)}")
    return df


def group_rules_by_attribute(df: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    """Group rows by Attribute. Each value is a list of rule dicts (Entity, Attribute, Normalization, Rule description, Reference) in row order."""
    out: dict[str, list[dict[str, Any]]] = {}
    for _, row in df.iterrows():
        attr = row.get("Attribute")
        if pd.isna(attr) or not str(attr).strip():
            continue
        attr = str(attr).strip()
        rule = {
            "Entity": row.get("Entity"),
            "Attribute": attr,
            "Normalization": row.get("Normalization"),
            "Rule description": row.get("Rule description"),
            "Reference": row.get("Reference"),
        }
        # Coerce to str for Rule description
        if pd.notna(rule["Rule description"]):
            rule["Rule description"] = str(rule["Rule description"]).strip()
        else:
            rule["Rule description"] = ""
        if attr not in out:
            out[attr] = []
        out[attr].append(rule)
    return out
