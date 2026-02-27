"""Prompt builders for attribute resolution.

All prompts can optionally receive canonical backbone data from domain_backbone.yaml
to ground the LLM output against the domain model.
"""

from normalisation_rules.config import (
    get_backbone_attributes_summary,
    get_backbone_invariants_summary,
)


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


def build_backbone_modeling_prompt(
    standards_preview: str,
    manu_preview: str,
    dataset_preview: str,
    dataset_excerpt: str,
) -> str:
    """Build the prompt for canonical backbone schema modeling with structural classification."""
    backbone_ref = get_backbone_attributes_summary()
    invariants_ref = get_backbone_invariants_summary()

    backbone_section = ""
    if backbone_ref:
        backbone_section = f"""
**CANONICAL REFERENCE SCHEMA (domain_backbone.yaml)**
The following is the authoritative attribute list from the domain backbone. Use it as your
primary reference. You MUST include all Tier 1 and Tier 2 attributes. You may add Tier 3
or new attributes if the evidence supports them. If you disagree with any classification
below, override it and explain why in your rationale.

{backbone_ref}
"""

    invariants_section = ""
    if invariants_ref:
        invariants_section = f"""
**DOMAIN INVARIANTS (must hold true in your output)**
{invariants_ref}
"""

    return f"""You are an ontology and schema architect for the Electrical Equipment domain, specifically **Contactors**. You have deep expertise in IEC 60947, IEC 60947-4-1, NEMA ICS, UNSPSC, and electrical product data modeling.

**Task**
Derive the canonical backbone schema for the **Contactors** category. This schema defines the structurally complete set of attributes that characterize any contactor as a product object, independent of how those attributes are later used (ERP, ecommerce, engineering).
{backbone_section}{invariants_section}
**For each attribute, you must determine:**

1. **structural_role** — what role does this attribute play in defining the object?
   - `identity`: defines what the object IS (e.g., contactor type/class distinction)
   - `variant-defining`: distinguishes variants within the category (e.g., rated current, number of poles — different values mean different product variants)
   - `descriptive`: characterizes the object but does not define variants (e.g., weight, dimensions)
   - `contextual`: depends on usage context or is derived from other attributes (e.g., utilization category, application class)

2. **data_type** — structural typing for schema modeling:
   - `scalar`: single numeric or string value (e.g., 25A, 3)
   - `range`: min/max or continuous span (e.g., 100-240V)
   - `enumeration`: fixed set of allowed values (e.g., AC-1, AC-3, AC-4)
   - `boolean`: true/false (e.g., DIN Rail mountable)
   - `conditional`: value depends on another attribute's value
   - `composite`: structured multi-part value (e.g., 2NO+1NC)

3. **unit** — unit model: {{"base_unit": "A", "unit_system": "SI"}} or null for dimensionless/enumeration attributes.

4. **dependencies** — inter-attribute relationships (list, may be empty):
   - `conditional`: value changes based on another attribute (e.g., rated current depends on utilization category)
   - `co-determined`: must be specified together (e.g., current and voltage)
   - `derived`: can be computed from other attributes
   - `constrains`: limits the valid range of another attribute

5. **intrinsic** — boolean: is this attribute inherent to the object's physical/electrical identity, or is it external (e.g., price, availability)?

6. **standards_defined** — boolean: is this explicitly defined in IEC/NEMA/UNSPSC standards?

7. **cross_manufacturer_stability** — how consistently do manufacturers (ABB, Siemens, Schneider, Eaton, Square D) use this attribute: `high`, `medium`, or `low`.

8. **confidence** — composite with three sub-scores:
   - `ontological_necessity` (0.0–1.0): probability this attribute is non-optional for defining any contactor.
   - `cross_manufacturer_stability` (0.0–1.0): consistency of this attribute across manufacturers.
   - `standards_coverage` (0.0–1.0): how explicitly defined in formal standards.
   - `composite` (0.0–1.0): weighted blend = 0.5 * ontological_necessity + 0.3 * cross_manufacturer_stability + 0.2 * standards_coverage.
   All scores MUST vary across attributes. Do NOT use the same values for all.

9. **sources** — list of standards or sources (e.g., ["IEC 60947-4-1", "NEMA ICS 2"]).

10. **rationale** — modeling rationale explaining: why this structural_role, why these dependencies, how it fits the object definition. Do NOT explain usage context (e.g., "important for procurement"). Explain structural decisions (e.g., "Variant-defining because different current ratings distinguish product variants within a family. Co-determined with voltage per IEC 60947-4-1 Table 2.").

**Instructions**
1. Start from the CANONICAL REFERENCE SCHEMA above. Include every Tier 1 and Tier 2 attribute.
2. Validate and refine each attribute's classification against the evidence sources below.
3. Add any additional attributes the evidence justifies (assign them Tier 3).
4. Ensure all DOMAIN INVARIANTS hold in your output.
5. Reason step-by-step: first identity, then variant-defining, then descriptive, then contextual.
6. For each attribute, explicitly state its dependencies before finalizing the schema.
7. Produce explicit reasoning before the backbone array.

**Evidence from standards (UNSPSC, IEC, NEMA):**
{standards_preview}

**Evidence from manufacturer sites / technical specs:**
{manu_preview}

**Evidence from Contactors dataset (columns and sample values):**
{dataset_preview}
Excerpt: {dataset_excerpt[:800] if dataset_excerpt else "N/A"}

**Output**
Return ONLY valid JSON:
{{
  "reasoning": "Step 1: Validate reference schema... Step 2: Check evidence... Step 3: Dependencies... Step 4: Invariants... Therefore...",
  "backbone": [
    {{
      "name": "Rated operational current",
      "description": "Maximum current the contactor can continuously carry in a given utilization category",
      "structural_role": "variant-defining",
      "data_type": "scalar",
      "unit": {{"base_unit": "A", "unit_system": "SI"}},
      "dependencies": [
        {{"attribute": "Utilization category", "type": "conditional", "note": "Value changes per AC-1, AC-3, AC-4"}},
        {{"attribute": "Rated operational voltage", "type": "co-determined", "note": "Current rating is specified at a given voltage"}}
      ],
      "intrinsic": true,
      "standards_defined": true,
      "cross_manufacturer_stability": "high",
      "confidence": {{
        "composite": 0.94,
        "ontological_necessity": 0.97,
        "cross_manufacturer_stability": 0.92,
        "standards_coverage": 0.95
      }},
      "sources": ["IEC 60947-4-1", "NEMA ICS 2"],
      "rationale": "Defined in IEC 60947-4-1 as a primary rated value. Co-determined with voltage and utilization category. Variant-defining because different current ratings distinguish product variants within a family."
    }}
  ]
}}
"""


def build_lens_projection_prompt(backbone_json: str) -> str:
    """Build the prompt that projects the canonical backbone into supply chain and ecommerce views."""
    return f"""You are a product data architect projecting a canonical backbone schema into domain-specific views.

**Task**
Given the canonical backbone schema for **Contactors** below, produce two lens projections:

1. **Supply chain lens (ERP/procurement)**: select backbone attributes relevant to sourcing, inventory, logistics, standards compliance, and procurement workflows. For each, add:
   - `procurement_priority`: `critical`, `important`, or `supplementary`
   - `erp_field_note`: brief note on how this maps to ERP/procurement usage

2. **Ecommerce lens (selling/channel)**: select backbone attributes relevant to product discovery, comparison, filtering, and merchandising. For each, add:
   - `display_priority`: `primary`, `secondary`, or `tertiary`
   - `filter_suitable`: boolean — whether this attribute is suitable as a faceted search filter
   - `merchandising_note`: brief note on how this supports buyer navigation

An attribute may appear in both lenses. Reference attributes by their exact `name` from the backbone.

**Canonical Backbone Schema:**
{backbone_json}

**Output**
Return ONLY valid JSON:
{{
  "supply_chain": [
    {{
      "name": "Rated operational current",
      "procurement_priority": "critical",
      "erp_field_note": "Primary specification for matching contactor to load requirements in purchase orders"
    }}
  ],
  "ecommerce": [
    {{
      "name": "Rated operational current",
      "display_priority": "primary",
      "filter_suitable": true,
      "merchandising_note": "Key filter for buyers selecting contactors by amperage rating"
    }}
  ]
}}
"""
