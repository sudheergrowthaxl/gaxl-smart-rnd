"""LLM-based product category detection from uploaded dataset."""

import json

import pandas as pd

from normalisation_rules.config import get_openai_client, get_categories_from_docx
from normalisation_rules.prompts.category_detection_prompt import (
    build_category_detection_prompt,
)


def detect_category(
    df: pd.DataFrame,
    filename: str,
    known_categories: list[str] | None = None,
    model: str = "gpt-4o-mini",
) -> dict:
    """Auto-detect the product category from an uploaded dataset.

    Analyzes column names, sample values, and filename, then cross-references
    against the known category list from Electrical_Components.docx.

    Returns:
        dict with keys: category, confidence, reasoning
    """
    if known_categories is None:
        known_categories = get_categories_from_docx()

    columns = list(df.columns)

    sample_values: dict[str, list[str]] = {}
    for col in columns:
        vals = df[col].dropna().head(5).astype(str).tolist()
        sample_values[col] = vals

    prompt = build_category_detection_prompt(
        columns=columns,
        sample_values=sample_values,
        filename=filename,
        known_categories=known_categories,
    )

    client = get_openai_client()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            return _fallback(filename, known_categories)
        result = json.loads(content)
        result.setdefault("category", "Unknown")
        result.setdefault("confidence", 0.0)
        result.setdefault("reasoning", "")
        return result
    except (json.JSONDecodeError, TypeError, Exception) as exc:
        return {
            "category": "Unknown",
            "confidence": 0.0,
            "reasoning": f"Detection failed: {exc}",
            "error": str(exc),
        }


def _fallback(filename: str, known_categories: list[str]) -> dict:
    """Simple heuristic fallback if LLM call fails."""
    fn_lower = filename.lower()
    for cat in known_categories:
        if cat.lower() in fn_lower:
            return {
                "category": cat,
                "confidence": 0.6,
                "reasoning": f"Fallback: filename '{filename}' contains '{cat}'.",
            }
    return {
        "category": "Unknown",
        "confidence": 0.0,
        "reasoning": "Could not detect category from filename or LLM.",
    }
