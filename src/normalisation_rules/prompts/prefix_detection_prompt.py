"""Prompt for LLM-based column prefix detection and stripping."""


def build_prefix_detection_prompt(columns: list[str], category: str) -> str:
    """Build a CoT prompt that detects vendor/system prefixes and maps to clean names."""
    cols_block = "\n".join(f"  - {c}" for c in columns)

    return f"""You are an expert in industrial product data modeling.

**Task**: Analyze the column names from a **{category}** dataset and identify any
common prefixes or naming patterns that are NOT part of the canonical attribute name.
Map each column to its clean, canonical name.

**Chain of Thought — follow these steps:**

1. **Pattern Detection**: Look for common prefixes (e.g., 'zz_', 'attr_', 'col_',
   vendor codes) or suffixes that are systematic data artifacts rather than
   meaningful attribute names.

2. **Functional Purpose**: For each column, determine what the clean attribute name
   should be based on what the attribute actually represents in the context of
   **{category}**. The clean name should be what a domain expert would call it.

3. **Preservation Rule**: If a column name has NO prefix/artifact and is already
   clean and meaningful, keep it exactly as-is.

4. **Mapping**: Output a mapping from original name to clean name for EVERY column.

**Columns from the {category} dataset ({len(columns)} total):**
{cols_block}

**Output ONLY valid JSON:**
{{
  "reasoning": "Detected prefix pattern '...' across N columns. These appear to be system-generated prefixes because ...",
  "prefix_pattern": "the detected prefix pattern or null if none",
  "mapping": {{
    "original_column_name": "Clean Canonical Name",
    "another_original": "Another Clean Name"
  }}
}}

Include ALL {len(columns)} columns in the mapping. If a column needs no change, map
it to itself.
"""
