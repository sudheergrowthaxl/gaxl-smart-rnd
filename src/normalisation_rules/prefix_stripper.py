"""LLM-based column prefix detection and stripping."""

import json

import pandas as pd

from normalisation_rules.config import get_openai_client
from normalisation_rules.prompts.prefix_detection_prompt import (
    build_prefix_detection_prompt,
)


def strip_column_prefixes(
    df: pd.DataFrame,
    category: str,
    model: str = "gpt-4o-mini",
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Detect and remove vendor/system prefixes from column names.

    Uses the LLM to analyze column naming patterns and produce a mapping
    from original names to clean canonical names.

    Returns:
        (renamed_df, mapping_dict) where mapping_dict is {original: clean}.
    """
    columns = list(df.columns)
    if not columns:
        return df, {}

    prompt = build_prefix_detection_prompt(columns, category)
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
            return df, {c: c for c in columns}
        result = json.loads(content)
        mapping = result.get("mapping", {})
    except (json.JSONDecodeError, TypeError, Exception):
        return df, {c: c for c in columns}

    # Ensure all columns are in the mapping (identity for missing ones)
    for col in columns:
        if col not in mapping:
            mapping[col] = col

    # Validate: no duplicate clean names
    clean_names = list(mapping.values())
    if len(set(clean_names)) < len(clean_names):
        seen: set[str] = set()
        deduped: dict[str, str] = {}
        for orig, clean in mapping.items():
            if clean in seen:
                deduped[orig] = orig
            else:
                seen.add(clean)
                deduped[orig] = clean
        mapping = deduped

    renamed = df.rename(columns=mapping)
    return renamed, mapping
