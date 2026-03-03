"""Prompt builders for attribute resolution.

All prompts use the runtime domain model (LLM-generated) as context.
No static YAML backbone files.
"""


def build_standards_extraction_prompt(raw_excerpt: str, category: str) -> str:
    """Build the prompt to extract attribute names from standards search results."""
    return f"""You are an expert in electrical equipment standards (UNSPSC, IEC, NEMA, UL) and industrial product data modeling.

You are analyzing the category **{category}**.

**Chain of Thought — mandatory reasoning steps:**
1. **What IS a {category.lower()}?** Describe its physical form, its electrical/mechanical function, and its role in an industrial system. If you are uncertain, reason from the category name and the evidence below.
2. **Which standards govern it?** Identify the relevant IEC, NEMA, UNSPSC, or UL standards for this specific category.
3. **What attributes do those standards define?** Extract the attributes that standards use to specify, classify, and differentiate products in this category.

From the text below (search results about {category.lower()} and electrical equipment standards), extract a list of **attribute names** (product attributes, specifications, properties) that standards use to describe {category.lower()} or similar electrical controls.

Output ONLY valid JSON with this structure:
{{
  "attributes": [
    {{ "name": "Rated operational voltage", "source": "IEC 60947", "description": "Rated voltage for main circuit" }},
    ...
  ]
}}

Include all relevant attribute-like terms (voltage, current, poles, frequency, etc.). Use "source" to indicate UNSPSC, IEC, or NEMA where evident.

Text (excerpt):
{raw_excerpt[:12000]}
"""


def build_manufacturer_extraction_prompt(raw_excerpt: str, category: str) -> str:
    """Build the prompt to extract attribute names from manufacturer site search results."""
    return f"""You are an expert in electrical product data and manufacturer catalogs.

You are analyzing the category **{category}**.

**Chain of Thought — mandatory reasoning steps:**
1. **What IS a {category.lower()}?** Describe its physical form, its electrical/mechanical function, and how manufacturers differentiate product variants.
2. **How is it sold?** What are the key specifications that appear on a datasheet or in a catalog listing?
3. **Extract attributes**: From the text below, identify all attributes manufacturers use to specify this type of component.

From the text below (search results from manufacturer sites and technical specs for {category.lower()}), extract a list of **attribute names** (product attributes, specifications, datasheet fields) that manufacturers use to describe {category.lower()}.

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
    category: str,
    domain_model_context: str = "",
) -> str:
    """Build the prompt for canonical backbone schema modeling with structural classification."""
    backbone_section = ""
    if domain_model_context:
        backbone_section = f"""
**DOMAIN MODEL CONTEXT (runtime-generated)**
The following domain model was generated for this category. Use it as the PRIMARY context
to guide your attribute schema. It describes entities, properties, ontology relationships,
and operational logic. Validate each attribute against this model:

{domain_model_context}
"""
    else:
        backbone_section = f"""
**NO DOMAIN MODEL AVAILABLE**
No domain model exists for "{category}". You must derive the schema entirely from:
1) Your intrinsic knowledge of what a {category.lower()} IS (functional purpose, physical components, electrical characteristics),
2) The evidence sources provided below (standards, manufacturer data, user dataset).
Reason from first principles: "What defines this entity? What attributes are needed to distinguish one variant from another?"
"""

    invariants_section = ""

    return f"""You are an ontology and schema architect for the Electrical Equipment domain, specifically **{category}**. You have deep expertise in IEC standards, NEMA, UNSPSC, and electrical product data modeling.

**Task**
Derive the canonical backbone schema for the **{category}** category. This schema defines the structurally complete set of attributes that characterize any {category.lower()} as a product object, independent of how those attributes are later used (ERP, ecommerce, engineering).

**Critical Reasoning Requirement**: You must reason from the FUNCTIONAL PURPOSE of a {category.lower()} — what it IS physically, what it does electrically, and what attributes are needed to fully characterize it as a product. Do not blindly copy a reference schema; validate every attribute against "does this attribute exist because of what a {category.lower()} fundamentally is?"
{backbone_section}{invariants_section}
**For each attribute, you must determine:**

1. **structural_role** — what role does this attribute play in defining the object?
   - `identity`: defines what the object IS (e.g., type/class distinction)
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
   - `ontological_necessity` (0.0–1.0): probability this attribute is non-optional for defining any {category.lower()}.
   - `cross_manufacturer_stability` (0.0–1.0): consistency of this attribute across manufacturers.
   - `standards_coverage` (0.0–1.0): how explicitly defined in formal standards.
   - `composite` (0.0–1.0): weighted blend = 0.5 * ontological_necessity + 0.3 * cross_manufacturer_stability + 0.2 * standards_coverage.
   All scores MUST vary across attributes. Do NOT use the same values for all.

9. **sources** — list of standards or sources (e.g., ["IEC 60947-4-1", "NEMA ICS 2"]).

10. **rationale** — modeling rationale explaining: why this structural_role, why these dependencies, how it fits the object definition. Do NOT explain usage context (e.g., "important for procurement"). Explain structural decisions (e.g., "Variant-defining because different current ratings distinguish product variants within a family. Co-determined with voltage per IEC 60947-4-1 Table 2.").

**Instructions — Chain of Thought Reasoning (mandatory)**
1. **Step 1 — Functional Analysis**: What IS a {category.lower()}? Describe its physical form, its electrical/mechanical function, and its role in an industrial system. This grounds every subsequent decision.
2. **Step 2 — Identity Attributes**: What attributes define WHAT this object is? (e.g., manufacturer, part number, product family)
3. **Step 3 — Variant-Defining Attributes**: What attributes distinguish one {category.lower()} variant from another within the same family? (e.g., rated current, voltage, number of poles — if applicable to this category)
4. **Step 4 — Descriptive Attributes**: What attributes characterize the object but do NOT define variants? (e.g., weight, dimensions, durability)
5. **Step 5 — Contextual Attributes**: What attributes depend on usage context? (e.g., utilization category, application class)
6. **Step 6 — Evidence Validation**: Cross-check your reasoning against the standards evidence, manufacturer evidence, and dataset evidence below. Add any attribute the evidence supports. Remove any attribute that has no evidence AND no strong functional justification.
7. **Step 7 — Dependencies**: For each attribute, state what other attributes it depends on or constrains.
8. **Step 8 — Invariants**: Verify that domain invariants (if provided) hold in your output. If no invariants are provided, derive the key invariants for this category from your functional analysis.
9. If a domain backbone reference is provided above, use it as a STARTING POINT — but you must validate every attribute against your functional analysis. Override anything that does not fit.
10. Produce explicit reasoning BEFORE the backbone array in your JSON output.

**Evidence from standards (UNSPSC, IEC, NEMA):**
{standards_preview}

**Evidence from manufacturer sites / technical specs:**
{manu_preview}

**Evidence from {category} dataset (columns and sample values):**
{dataset_preview}
Excerpt: {dataset_excerpt[:800] if dataset_excerpt else "N/A"}

**COVERAGE REQUIREMENT — CRITICAL**
You MUST produce a COMPREHENSIVE attribute list. Typical industrial product categories
require **40–80+ attributes** spanning identity, variant-defining, descriptive, and
contextual roles. Do NOT stop at 10–20 attributes. Cover ALL of:
- Electrical ratings (voltage, current, power, frequency, phases, etc.)
- Mechanical/physical properties (dimensions, weight, mounting, enclosure, terminals)
- Performance/duty ratings (utilization category, breaking capacity, endurance, etc.)
- Environmental/compliance (IP rating, temperature range, altitude, certifications)
- Classification & identity (part number, manufacturer, series/family, product type)
- Accessories & configuration (auxiliary contacts, coil voltage, suppression, etc.)
- Lifecycle & packaging (country of origin, GTIN/EAN, packaging unit, weight unit)
If a relevant attribute exists in ANY evidence source (standards, manufacturer, dataset),
include it. If you know from domain expertise that an attribute SHOULD exist for this
category even without explicit evidence, include it with appropriate confidence scores.

**Output**
Return ONLY valid JSON:
{{
  "reasoning": "Step 1: Functional Analysis... A {category} is primarily defined by... Therefore we need attributes X, Y... Step 2: Validate reference schema... Step 3: Check evidence... Step 4: Dependencies... Step 5: Invariants... Therefore...",
  "backbone": [
    {{
      "name": "Rated operational current",
      "description": "Maximum current the {category.lower()} can continuously carry in a given utilization category",
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


def build_lens_projection_prompt(backbone_json: str, category: str) -> str:
    """Build the prompt that projects the canonical backbone into supply chain and ecommerce views."""
    return f"""You are a product data architect projecting a canonical backbone schema into domain-specific views.

**Task**
Given the canonical backbone schema for **{category}** below, produce three lens projections:

1. **Supply chain lens (ERP/procurement)**: select backbone attributes relevant to sourcing, inventory, logistics, standards compliance, and procurement workflows. For each, add:
   - `procurement_priority`: `critical`, `important`, or `supplementary`
   - `erp_field_note`: brief note on how this maps to ERP/procurement usage

2. **Ecommerce lens (selling/channel)**: select backbone attributes relevant to product discovery, comparison, filtering, and merchandising. For each, add:
   - `display_priority`: `primary`, `secondary`, or `tertiary`
   - `filter_suitable`: boolean — whether this attribute is suitable as a faceted search filter
   - `merchandising_note`: brief note on how this supports buyer navigation

3. **Analytical lens (Data Quality/Reporting)**: select backbone attributes that are critical for data quality assessment and reporting. For each, add:
    - `dq_priority`: `critical`, `high`, `medium`
    - `completeness_requirement`: `mandatory`, `recommended`, `optional`

An attribute may appear in multiple lenses. Reference attributes by their exact `name` from the backbone.

**Canonical Backbone Schema:**
{backbone_json}

**Output**
Return ONLY valid JSON:
{{
  "supply_chain": [
    {{
      "name": "Rated operational current",
      "procurement_priority": "critical",
      "erp_field_note": "Primary specification for matching {category.lower()} to load requirements in purchase orders"
    }}
  ],
  "ecommerce": [
    {{
      "name": "Rated operational current",
      "display_priority": "primary",
      "filter_suitable": true,
      "merchandising_note": "Key filter for buyers selecting {category.lower()}s by amperage rating"
    }}
  ],
  "analytical": [
    {{
        "name": "Rated operational current",
        "dq_priority": "critical",
        "completeness_requirement": "mandatory"
    }}
  ]
}}
"""
