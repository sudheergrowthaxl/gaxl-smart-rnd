"""Prompt builders for attribute resolution."""


def build_standards_extraction_prompt(raw_excerpt: str) -> str:
    """Build the prompt to extract attribute names from standards search results."""
    return f"""You are an expert in electrical equipment standards (UNSPSC, IEC 60947, NEMA).

From the text below (search results about contactors and electrical equipment standards), extract a list of **attribute names** (product attributes, specifications, properties) that standards use to describe contactors or similar electrical controls.

Output ONLY valid JSON with this structure:
{{
  "attributes": [
    {{ "name": "Rated operational voltage", "source": "IEC 60947", "description": "Rated voltage for main circuit" }},
    ...
  ]
}}

Include all relevant attribute-like terms (voltage, current, poles, frequency, etc.). Use "source" to indicate UNSPSC, IEC 60947, IEC 60947-4-1, or NEMA where evident.

Text (excerpt):
{raw_excerpt[:12000]}
"""


def build_manufacturer_extraction_prompt(raw_excerpt: str) -> str:
    """Build the prompt to extract attribute names from manufacturer site search results."""
    return f"""You are an expert in electrical product data and manufacturer catalogs.

From the text below (search results from manufacturer sites and technical specs for contactors), extract a list of **attribute names** (product attributes, specifications, datasheet fields) that manufacturers use to describe contactors.

Output ONLY valid JSON with this structure:
{{
  "attributes": [
    {{ "name": "Rated current", "source": "Schneider Electric" }},
    ...
  ]
}}

Include all relevant attribute-like terms. Use "source" to indicate manufacturer or site name where evident.

Text (excerpt):
{raw_excerpt[:12000]}
"""


def build_cot_derivation_prompt(
    standards_preview: str,
    manu_preview: str,
    dataset_preview: str,
    dataset_excerpt: str,
) -> str:
    """Build the Chain-of-Thought prompt to derive the final recommended attribute list."""
    return f"""You are a schema builder that helps resolve or derive the core attributes for Contactors in the Electrical Equipment domain. You have expertise in electrical equipment, product taxonomy, and standards (IEC, NEMA, UNSPSC).

**Task**
Derive the set of attributes that best describe and classify products in the **Contactors** category. Use the three context sources below as reference and input to your reasoning. Do not restrict yourself to only the attributes listed — use your domain knowledge to include any additional attributes your reasoning justifies.

Organize your output into two perspectives (lenses):
- **Supply chain lens (ERP/procurement)**: attributes that support sourcing, inventory, logistics, and standards (e.g. UNSPSC, IEC, NEMA) — what procurement and operations need.
- **Ecommerce lens (selling/channel)**: attributes that support how buyers discover and compare products (e.g. category navigation, filters, merchandising) — what sales and storefronts need.
An attribute may appear in both lists if it serves both perspectives; use the same structure for each list.

**Instructions**
1. Reason step-by-step (Chain-of-Thought): consider what attributes are needed from standards, procurement, engineering, and ecommerce.
2. Produce explicit reasoning (e.g. "Step 1: ... Step 2: ... Therefore ...") before giving the final lists.
3. For each attribute in each list, provide a short description and a brief rationale; optionally indicate which source(s) it aligns with (IEC/Manufacturer/Dataset).

**Context from standards (UNSPSC, IEC, NEMA):**
{standards_preview}

**Context from manufacturer sites / technical specs:**
{manu_preview}

**Context from Contactors dataset (columns and sample values):**
{dataset_preview}
Excerpt: {dataset_excerpt[:800] if dataset_excerpt else "N/A"}

**Output**
Return ONLY valid JSON in this structure:
{{
  "reasoning": "Step 1: ... Step 2: ... Therefore ...",
  "supply_chain_attributes": [
    {{ "name": "...", "description": "...", "rationale": "...", "sources": "optional: IEC/Manufacturer/Dataset" }}
  ],
  "ecommerce_attributes": [
    {{ "name": "...", "description": "...", "rationale": "...", "sources": "optional: IEC/Manufacturer/Dataset" }}
  ],
  "confidence": 0.95
}}
"""
