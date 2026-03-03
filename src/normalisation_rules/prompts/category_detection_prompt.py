"""Prompt for LLM-based product category detection from uploaded dataset."""


def build_category_detection_prompt(
    columns: list[str],
    sample_values: dict[str, list[str]],
    filename: str,
    known_categories: list[str],
) -> str:
    """Build a Chain-of-Thought prompt to identify the product category.

    The LLM examines column names, sample values, filename, and cross-references
    the known category list from Electrical_Components.docx.
    """
    cols_block = "\n".join(f"  - {c}" for c in columns)

    samples_block = ""
    for col, vals in sample_values.items():
        preview = ", ".join(repr(v) for v in vals[:5])
        samples_block += f"  - {col}: [{preview}]\n"

    categories_block = ", ".join(known_categories) if known_categories else "(none provided)"

    return f"""You are an expert in industrial electrical equipment product data.

**Task**: Identify the product category of the uploaded dataset.

**Chain of Thought — you MUST follow these steps explicitly:**

1. **Column Analysis**: Examine each column name below. Which domain-specific terms
   appear (e.g., 'coil voltage' suggests contactors or relays, 'trip curve' suggests
   circuit breakers, 'contact rating' suggests relays or switches)?

2. **Value Analysis**: Examine the sample values. Do they contain technical patterns
   like voltage ratings (e.g., '24V DC'), current ratings (e.g., '10A'), part number
   prefixes from known manufacturers, utilization categories (e.g., 'AC-3'), or
   configuration codes (e.g., '2NO+1NC')?

3. **Filename Analysis**: Does the filename contain a category hint?

4. **Cross-Reference**: Compare your analysis against the known category list. Which
   category is the best match? If none match exactly, choose the closest one and
   explain why.

5. **Confidence Assessment**: How confident are you? Consider:
   - High (0.85–1.0): Multiple strong signals from columns, values, and filename
   - Medium (0.6–0.84): Some signals but ambiguous (could be multiple categories)
   - Low (0.0–0.59): Very few signals, mostly guessing

**Dataset evidence:**

Filename: {filename}

Columns ({len(columns)}):
{cols_block}

Sample values:
{samples_block}

Known categories (from Electrical_Components.docx):
{categories_block}

**Output ONLY valid JSON:**
{{
  "reasoning": "Step 1: Column analysis — ... Step 2: Value analysis — ... Step 3: Filename — ... Step 4: Cross-reference — ... Step 5: Confidence — ...",
  "category": "the identified category name (use exact name from known list if possible)",
  "confidence": 0.0
}}
"""
