"""Prompts for normalisation rule derivation.

Uses runtime domain model context for normalization guidance.
No static YAML backbone files.
"""

from normalisation_rules.config import get_domain_normalization_context


def get_system_prompt(domain: str) -> str:
    return f"""You are an expert in data normalisation for Industrial Electrical Equipment, currently working on the category **{domain}**.

**Your approach — Chain of Thought reasoning:**
Before deriving any rule, you MUST first reason about the functional purpose of the attribute within this product category. Follow these steps explicitly:

1) **Functional Purpose**: What does this attribute MEAN for a {domain.lower()}? What is its physical or electrical significance? If you are unfamiliar with this specific category, reason from first principles about what kind of component it is, what it does, and why this attribute matters.

2) **Expected Format**: What format would an engineer, procurement specialist, or ecommerce buyer expect to see? Consider how this attribute would appear in a purchase order, a datasheet, and a product listing.

3) **Pattern Analysis**: What patterns exist in the observed data that deviate from that expected format? Are there abbreviations, unit inconsistencies, text vs numeric mismatches?

4) **Canonical Representation**: What would the canonical (standard) representation be, and why? Ground your answer in IEC, NEMA, UNSPSC, or manufacturer conventions where applicable.

**Inputs you will receive:**
1) Attribute-level statistics (datatype, range, cardinality, missing %, patterns across values),
2) Curated possible values from up to three sources (when provided):
   a) Customer observed values (distinct values from profiling data),
   b) Standards context (IEC, NEMA, UNSPSC terminology and accepted values),
   c) Manufacturer catalog values (how major manufacturers represent this attribute),
3) Domain backbone reference (when available): structural role, data type, allowed values, canonical formats, and mapping tables. This is REFERENCE CONTEXT to guide your reasoning — not an absolute constraint. If you believe the data or your domain expertise suggests a different approach, override the backbone and explain why.

**If NO domain backbone is provided:**
Reason from FIRST PRINCIPLES. Ask: "What IS a {domain.lower()}? What is its function in an industrial electrical system? What attributes define it and how should they be represented?" Use your intrinsic knowledge of electrical engineering, IEC/NEMA standards, and product data modeling.

**Rule derivation guidelines:**
- Rules must be GENERALISED over the entire attribute — do not output one rule per distinct value.
- Output 1–2 rules per attribute (3 only if clearly needed).
- Use attribute-level statistics and patterns to infer general normalisation rules.
- Each rule MUST include a brief reasoning statement explaining WHY this normalisation is needed (based on the functional purpose of the attribute).
- Exclude any rule related to NULL or missing values.

**Output format:** one rule per line, tab-separated:
Entity\tAttribute\tNormalization\tRule description

- Use the exact format above with tabs. Do not output any header line — only rule lines.
- If no meaningful rule can be derived, output a single line explaining why.
"""


def build_user_prompt(
    attribute: dict,
    curated_context: str,
    few_shot_examples: str,
    domain: str,
    domain_model: dict | None = None,
) -> str:
    """Build the user message for the LLM."""
    name = attribute.get("name", "")
    datatype = attribute.get("datatype", "")
    semantic_type = attribute.get("semantic_type", "")
    missing = attribute.get("missing_percentage")
    range_val = attribute.get("range")
    values = attribute.get("values", [])

    dm_guidance = get_domain_normalization_context(domain_model, name) if domain_model else ""

    lines = [
        "--- Few-shot examples (output 1–2 rules per attribute in this style, general not per-value) ---",
        few_shot_examples.strip() if few_shot_examples.strip() else "(none)",
        "",
    ]

    if dm_guidance:
        lines.extend([
            "--- Domain model context (use as primary guide for reasoning) ---",
            dm_guidance,
            "",
        ])

    lines.extend([
        "--- Attribute to derive rules for ---",
        f"Category: {domain}",
        f"Attribute: {name}",
        f"Datatype: {datatype}",
        f"Semantic type: {semantic_type}",
        f"Missing %: {missing}",
        f"Range: {range_val}",
        "",
        "Observed values (value -> count) — use to see patterns, do not list one rule per value:",
    ])
    n_show = min(20, len(values))
    for v in values[:n_show]:
        val = v.get("value")
        cnt = v.get("count", 0)
        lines.append(f"  - {val!r} -> {cnt}")
    if len(values) > n_show:
        lines.append(f"  ... and {len(values) - n_show} more distinct values.")

    if curated_context.strip():
        lines.extend([
            "",
            "--- Curated possible values from all sources ---",
            curated_context[:12000],
            "",
        ])

    lines.append("")
    lines.append(
        "Derive 1–2 generalised normalisation rules for this attribute. "
        "Do not list one rule per value; generalise from the statistics, patterns, "
        "and the curated context above (customer data, standards, and manufacturer catalogs). "
        "When domain backbone reference is provided, use it as context to guide your reasoning — "
        "but if the data or your domain expertise suggests a different canonical form, use that instead and explain why. "
        "Exclude any rule related to NULL or missing values — only rules for actual present values. "
        "Chain of Thought: For each rule, briefly reason about WHY this normalisation is needed "
        "based on the functional purpose of the attribute. "
        "Include this reasoning in the Rule description. "
        "Output only the rule lines (tab-separated: Entity, Attribute, Normalization, Rule description), one per line."
    )
    return "\n".join(lines)


def build_rules_lens_projection_prompt(
    rules_text: str,
    category: str,
    view_type: str,
) -> str:
    """On-demand prompt to project derived normalisation rules into a specific view.

    Args:
        rules_text: The derived rules (tab-separated lines).
        category: Product category.
        view_type: One of 'supply_chain', 'ecommerce', 'analytical'.
    """
    view_descriptions = {
        "supply_chain": (
            "**Supply Chain / ERP perspective**: Focus on how these normalisation rules "
            "support procurement, inventory management, P2P workflows, and standards compliance. "
            "Which rules ensure data consistency for purchase orders, vendor comparison, and "
            "spend classification? Which rules align with IEC/NEMA/UNSPSC coding?"
        ),
        "ecommerce": (
            "**Ecommerce / Selling perspective**: Focus on how these normalisation rules "
            "support product discovery, comparison, filtering, and merchandising. "
            "Which rules ensure data is buyer-friendly? Which rules support faceted search, "
            "product matching, and cross-sell/up-sell?"
        ),
        "analytical": (
            "**Analytical / Data Quality perspective**: Focus on how these normalisation rules "
            "support data quality assessment, reporting, and analytics. "
            "Which rules ensure completeness, consistency, and accuracy metrics? "
            "Which rules enable meaningful aggregation and trend analysis?"
        ),
    }

    view_desc = view_descriptions.get(view_type, view_descriptions["supply_chain"])

    return f"""You are a product data architect projecting normalisation rules into domain-specific views.

**Task**: Given the normalisation rules derived for **{category}**, project them into the
{view_type.replace('_', ' ')} view.

{view_desc}

**Chain of Thought**: For each rule, reason about:
1) Does this rule matter for the {view_type.replace('_', ' ')} context? Why or why not?
2) How would applying this rule improve data quality in this specific context?
3) What is the business impact of NOT applying this rule in this context?

**Derived Normalisation Rules:**
{rules_text}

**Output ONLY valid JSON:**
{{
  "view_type": "{view_type}",
  "reasoning": "Overall rationale for which rules matter in this view and why...",
  "projected_rules": [
    {{
      "rule": "the original rule text",
      "relevance": "critical|important|supplementary",
      "view_rationale": "Why this rule matters (or doesn't) for {view_type.replace('_', ' ')}"
    }}
  ]
}}
"""
