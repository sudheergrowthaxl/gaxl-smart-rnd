"""Prompts for normalisation rule derivation.

Loads canonical normalization patterns from domain_backbone.yaml when available,
so the LLM produces rules aligned with the domain model.
"""

from normalisation_rules.config import get_backbone_normalization_for_attribute

SYSTEM_PROMPT = """You are an expert in data normalisation for Electrical Equipment, specifically Contactors.
Your task is to derive clear, actionable normalisation rules based on:
1) Attribute-level statistics (datatype, range, cardinality, missing %, imbalance, patterns across values) for a given attribute,
2) Curated possible values from three sources (when provided):
   a) Customer observed values (distinct values from profiling data),
   b) Standards context (IEC 60947, NEMA ICS terminology and accepted values),
   c) Manufacturer catalog values (how ABB, Siemens, Schneider Electric, Eaton, Square D etc. represent this attribute),
3) Canonical domain backbone metadata (when provided): structural role, data type, allowed values, canonical formats, and mapping tables from the domain model. Rules MUST align with these canonical definitions.

Rules must be GENERALISED over the entire attribute—do not output one rule per distinct value.
- Output 1–2 rules per attribute (3 only if clearly needed). Match the style of the few-shot examples: general format standardisation, conditional logic, or mapping families, not exhaustive value-by-value mappings.
- Use attribute-level statistics and patterns to infer general normalisation rules (e.g. "normalize to format X", "if condition then Y", "A/B/C become Z").
- When backbone metadata provides canonical_format, allowed_values, or mappings, your rules MUST normalise values toward those canonical forms.
- Exclude any rule related to NULL or missing values. Do not generate rules that deal with handling, replacing, or flagging nulls, blanks, or missing data. Only generate rules that normalise and standardise actual present values.

Output format: one rule per line, tab-separated:
Entity\tAttribute\tNormalization\tRule description

Example lines (general, not per-value):
Contactors\tzz_Auxiliary Contact\tNormalization\tNormalize to format 1NO+1NC
Contactors\tzz_Number of Poles\tNormalization\t"3P", "3 Pole", "Three Pole" normalize them to 3
Contactors\tzz_Mounting Type\tNormalization\t"On Rail", "35mm rail" becomes "DIN Rail"

- Use the exact format above with tabs. Do not output any header line—only rule lines.
- If no meaningful rule can be derived, output a single line explaining why (still in the same format with Attribute and "Normalization" and the explanation as Rule description).
"""


def build_user_prompt(
    attribute: dict,
    curated_context: str,
    few_shot_examples: str,
    domain: str,
) -> str:
    """Build the user message for the LLM."""
    name = attribute.get("name", "")
    datatype = attribute.get("datatype", "")
    semantic_type = attribute.get("semantic_type", "")
    missing = attribute.get("missing_percentage")
    range_val = attribute.get("range")
    values = attribute.get("values", [])

    backbone_guidance = get_backbone_normalization_for_attribute(name)

    lines = [
        "--- Few-shot examples (output 1–2 rules per attribute in this style, general not per-value) ---",
        few_shot_examples.strip() if few_shot_examples.strip() else "(none)",
        "",
    ]

    if backbone_guidance:
        lines.extend([
            "--- Domain backbone guidance (canonical definitions — rules MUST align with these) ---",
            backbone_guidance,
            "",
        ])

    lines.extend([
        "--- Attribute to derive rules for ---",
        f"Domain: {domain}",
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
            "--- Curated possible values from all sources (use this to align rules with standards and industry practice) ---",
            curated_context[:12000],
            "",
        ])

    lines.append("")
    lines.append(
        "Derive 1–2 generalised normalisation rules for this attribute. "
        "Do not list one rule per value; generalise from the statistics, patterns, "
        "and the curated context above (customer data, standards, and manufacturer catalogs). "
        "When domain backbone guidance is provided, ensure your rules normalise toward "
        "the canonical formats, allowed values, and mappings defined there. "
        "Exclude any rule related to NULL or missing values—only rules for actual present values. "
        "Output only the rule lines (tab-separated: Entity, Attribute, Normalization, Rule description), one per line."
    )
    return "\n".join(lines)
