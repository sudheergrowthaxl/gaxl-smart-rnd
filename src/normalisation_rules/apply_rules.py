"""Load dataset, apply normalisers, build before/after and comparison."""

from pathlib import Path
from typing import Any

import pandas as pd

from normalisation_rules.codegen import (
    compile_normaliser,
    generate_normaliser_code,
    load_generated_code,
    save_generated_code,
)
from normalisation_rules.rules_loader import load_rules_excel, group_rules_by_attribute


def load_dataset(path: Path) -> pd.DataFrame:
    """Load Contactors dataset from Excel."""
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    return pd.read_excel(path, engine="openpyxl")


def generate_all_normalisers(
    rules_by_attr: dict[str, list[dict[str, Any]]],
    llm: Any,
    generated_code_path: Path | None = None,
) -> dict[str, Any]:
    """Generate and compile normaliser for each attribute. Returns dict attribute -> callable. Persists code to JSON."""
    attribute_to_code: dict[str, str] = {}
    for attr, rules in rules_by_attr.items():
        if not rules:
            continue
        code = generate_normaliser_code(attr, rules, llm)
        attribute_to_code[attr] = code
    save_generated_code(attribute_to_code, generated_code_path)
    normalisers = {}
    for attr, code in attribute_to_code.items():
        try:
            normalisers[attr] = compile_normaliser(code, attr)
        except Exception as e:
            # Skip this attribute but keep others
            import warnings
            warnings.warn(f"Could not compile normaliser for {attr}: {e}", UserWarning)
    return normalisers


def load_compiled_normalisers(
    rules_by_attr: dict[str, list[dict[str, Any]]],
    generated_code_path: Path | None = None,
) -> dict[str, Any]:
    """Load previously generated code from JSON and compile. Returns dict attribute -> callable."""
    attribute_to_code = load_generated_code(generated_code_path)
    if not attribute_to_code:
        return {}
    normalisers = {}
    for attr, code in attribute_to_code.items():
        try:
            normalisers[attr] = compile_normaliser(code, attr)
        except Exception as e:
            import warnings
            warnings.warn(f"Could not compile normaliser for {attr}: {e}", UserWarning)
    return normalisers


def apply_normalisers(
    df: pd.DataFrame,
    normalisers: dict[str, Any],
) -> pd.DataFrame:
    """Build df_after: copy of df with each normaliser applied to its column. Columns not in normalisers are unchanged."""
    df_after = df.copy()
    for attr, fn in normalisers.items():
        if attr not in df_after.columns:
            continue
        def apply_cell(row: pd.Series) -> Any:
            val = row[attr]
            try:
                return fn(val, row)
            except Exception:
                return val
        df_after[attr] = df_after.apply(apply_cell, axis=1)
    return df_after


def build_comparison_table(
    df_before: pd.DataFrame,
    df_after: pd.DataFrame,
    attributes: list[str],
) -> pd.DataFrame:
    """Long form: RowIndex, Attribute, Value_Before, Value_After for (row, attr) where value changed."""
    rows = []
    for idx in df_before.index:
        for attr in attributes:
            if attr not in df_before.columns or attr not in df_after.columns:
                continue
            b = df_before.loc[idx, attr]
            a = df_after.loc[idx, attr]
            # Consider different if one is NaN and the other isn't, or values differ
            if pd.isna(b) and pd.isna(a):
                continue
            if pd.isna(b) or pd.isna(a) or b != a:
                rows.append({
                    "RowIndex": idx,
                    "Attribute": attr,
                    "Value_Before": b,
                    "Value_After": a,
                })
    return pd.DataFrame(rows)
