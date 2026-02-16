"""Prompts for normalisation rule derivation and validation."""

SYSTEM_PROMPT = """You are an expert in data normalisation for Electrical Equipment, specifically Contactors.
Your task is to derive clear, actionable normalisation rules based on:
1) Attribute-level statistics (datatype, range, cardinality, missing %, imbalance, patterns across values) for a given attribute,
2) Web/domain context about standard terminology and practices (when provided).

Rules must be GENERALISED over the entire attribute—do not output one rule per distinct value.
- Output 1–2 rules per attribute (3 only if clearly needed). Match the style of the few-shot examples: general format standardisation, conditional logic, or mapping families, not exhaustive value-by-value mappings.
- Use attribute-level statistics and patterns to infer general normalisation rules (e.g. "normalize to format X", "if condition then Y", "A/B/C become Z").

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
    web_context: str,
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

    # Few-shot examples first (target style)
    lines = [
        "--- Few-shot examples (output 1–2 rules per attribute in this style, general not per-value) ---",
        few_shot_examples.strip() if few_shot_examples.strip() else "(none)",
        "",
        "--- Attribute to derive rules for ---",
        f"Domain: {domain}",
        f"Attribute: {name}",
        f"Datatype: {datatype}",
        f"Semantic type: {semantic_type}",
        f"Missing %: {missing}",
        f"Range: {range_val}",
        "",
        "Observed values (value -> count) — use to see patterns, do not list one rule per value:",
    ]
    # Summary: top 15–20 values plus note if more
    n_show = min(20, len(values))
    for v in values[:n_show]:
        val = v.get("value")
        cnt = v.get("count", 0)
        lines.append(f"  - {val!r} -> {cnt}")
    if len(values) > n_show:
        lines.append(f"  ... and {len(values) - n_show} more distinct values.")

    if web_context.strip():
        lines.extend([
            "",
            "--- Web search context for this attribute (use this to align with domain standards and terminology) ---",
            web_context[:6000],
            "",
        ])

    lines.append("")
    lines.append(
        "Derive 1–2 generalised normalisation rules for this attribute. "
        "Do not list one rule per value; generalise from the statistics, patterns, and the web search context above. "
        "Output only the rule lines (tab-separated: Entity, Attribute, Normalization, Rule description), one per line."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Validation prompts
# ---------------------------------------------------------------------------

VALIDATION_SYSTEM_PROMPT = """You are an expert in electrical equipment data validation, specifically Contactors.
Your task is to validate normalisation rules against official manufacturer datasheet specifications.

Target manufacturers: Schneider Electric, Siemens, ABB, Eaton.

For each rule provided, determine:
1) Whether the rule is consistent with how manufacturers represent this attribute in their datasheets.
2) Whether the canonical/normalized values in the rule match industry-standard terminology (IEC 60947, NEMA ICS).
3) Whether the rule logic (mappings, conditions, format standardisations) is accurate per manufacturer specs.

Output format: one line per rule, tab-separated:
Status\tValidation Notes

Status must be exactly one of:
- "Valid" — rule is confirmed accurate per manufacturer datasheets and industry standards.
- "Invalid" — rule contradicts manufacturer datasheet data or industry standards. Explain what is wrong.
- "Needs Review" — insufficient datasheet evidence to confirm or deny; or rule is partially correct.

Output exactly one result line per input rule, in the same order. Do not output headers or extra text—only the result lines.
"""


def build_validation_prompt(
    rules: list[str],
    attribute_name: str,
    datasheet_context: str,
) -> str:
    """Build the user message for rule validation."""
    lines = [
        f"--- Attribute: {attribute_name} ---",
        "",
        "--- Rules to validate ---",
    ]
    for i, rule in enumerate(rules, 1):
        lines.append(f"Rule {i}: {rule}")

    lines.append("")

    if datasheet_context.strip():
        lines.extend([
            "--- Manufacturer datasheet context (Schneider Electric, Siemens, ABB, Eaton) ---",
            datasheet_context[:8000],
            "",
        ])
    else:
        lines.extend([
            "--- No manufacturer datasheet context available ---",
            "(Validate based on your knowledge of IEC 60947, NEMA ICS standards, and major manufacturer practices.)",
            "",
        ])

    lines.append(
        f"Validate each of the {len(rules)} rule(s) above against the manufacturer datasheet data. "
        "Output exactly one line per rule in the format: Status\\tValidation Notes"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Few-shot examples prompts
# ---------------------------------------------------------------------------

FEW_SHOT_EXAMPLES_SYSTEM_PROMPT = """You are an expert in data normalisation for Electrical Equipment, specifically Contactors.
Your task is to generate concrete few-shot examples for each normalisation rule — both positive (valid/acceptable) and negative (invalid/unacceptable) cases.

These examples help downstream models and humans understand exactly how each rule should be applied.

For each rule provided, generate:
- 2-3 POSITIVE examples: real-world input values that the rule correctly handles, showing input -> expected normalised output.
- 2-3 NEGATIVE examples: real-world input values that should NOT be normalised by this rule, with a brief reason why.

Use realistic values that would appear in electrical contactor product data from manufacturers like Schneider Electric, Siemens, ABB, and Eaton.

Output format: one line per rule, containing the few-shot examples in this exact format:
[+] input -> output; [+] input -> output; [-] input -> reason; [-] input -> reason

Example output for a rule "Normalize to format 1NO+1NC":
[+] "1 NO + 1 NC" -> "1NO+1NC"; [+] "1NO 1NC" -> "1NO+1NC"; [+] "One NO One NC" -> "1NO+1NC"; [-] "24V DC" -> not an auxiliary contact value; [-] "N/A" -> missing value, skip normalisation

Output exactly one result line per input rule, in the same order. Do not output headers or extra text—only the example lines.
"""


def build_few_shot_examples_prompt(
    rules: list[str],
    attribute_name: str,
    datasheet_context: str,
) -> str:
    """Build the user message for few-shot examples generation."""
    lines = [
        f"--- Attribute: {attribute_name} ---",
        "",
        "--- Rules to generate few-shot examples for ---",
    ]
    for i, rule in enumerate(rules, 1):
        lines.append(f"Rule {i}: {rule}")

    lines.append("")

    if datasheet_context.strip():
        lines.extend([
            "--- Manufacturer datasheet context (use for realistic example values) ---",
            datasheet_context[:8000],
            "",
        ])

    lines.append(
        f"Generate few-shot examples for each of the {len(rules)} rule(s) above. "
        "For each rule, provide 2-3 positive [+] and 2-3 negative [-] examples using realistic contactor data values. "
        "Output exactly one line per rule with examples in the format: "
        "[+] input -> output; [+] input -> output; [-] input -> reason; [-] input -> reason"
    )
    return "\n".join(lines)
