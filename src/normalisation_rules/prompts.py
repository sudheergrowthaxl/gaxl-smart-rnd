"""Prompts for normalisation rule derivation."""

SYSTEM_PROMPT = """You are an expert in data normalisation for Electrical Equipment, specifically Contactors.
Your task is to derive clear, actionable normalisation rules using the MERGED LIST OF POSSIBLE VALUES provided (from customer data, NEMA/IEC standards, and manufacturers). Use this list to align terminology and derive generalised rules.

Rules must be GENERALISED over the entire attribute—do not output one rule per distinct value.
- Output as many rules as needed (typically 1–4) to cover normalisation for this attribute. Match the style of the few-shot examples: general format standardisation, conditional logic, or mapping families, not exhaustive value-by-value mappings.
- Use the merged possible values (and any standards/manufacturers context when provided) to infer general normalisation rules (e.g. "normalize to format X", "if condition then Y", "A/B/C become Z").

Output format: one rule per line, tab-separated (5 columns):
Entity\tAttribute\tNormalization\tRule description\tFew Shot examples

Few Shot examples column format: use [+] for correct mappings and [-] for invalid/non-standard examples with a short reason. Separate multiple examples with "; ". Example:
[+] "1 NO" -> "1NO"; [+] "1 NC" -> "1NC"; [+] "2 NO || 2 NC" -> "2NO||2NC"; [-] "1NO1NC" -> missing space and separator; [-] "One NO" -> non-standard abbreviation, should be numeric format

Example lines (general, not per-value):
Contactors\tzz_Auxiliary Contact\tNormalization\tNormalize to format 1NO+1NC\t[+] "1 NO" -> "1NO"; [+] "1 NC" -> "1NC"; [-] "1NO1NC" -> missing space and separator
Contactors\tzz_Number of Poles\tNormalization\t"3P", "3 Pole" normalize to 3\t[+] "3 Pole" -> "3"; [+] "3P" -> "3"; [-] "Three Pole" -> use numeric
Contactors\tzz_Mounting Type\tNormalization\t"On Rail", "35mm rail" becomes "DIN Rail"\t[+] "35mm rail" -> "DIN Rail"; [-] "Panel" -> specify rail type

- Use the exact format above with tabs. Do not output any header line—only rule lines. Every rule line must have all 5 columns; include at least one [+] and one [-] in Few Shot examples.
- If no meaningful rule can be derived, output a single line explaining why (still in the same format with Attribute and "Normalization" and the explanation as Rule description).
"""


def build_user_prompt(
    attribute: dict,
    few_shot_examples: str,
    domain: str,
    merged_possible_values: list[str],
    standards_context: str = "",
    manufacturers_context: str = "",
) -> str:
    """Build the user message for the LLM using merged possible values (customer + NEMA/IEC + manufacturers)."""
    name = attribute.get("name", "")
    datatype = attribute.get("datatype", "")
    semantic_type = attribute.get("semantic_type", "")
    missing = attribute.get("missing_percentage")
    range_val = attribute.get("range")
    values = attribute.get("values", [])

    lines = [
        "--- Few-shot examples (output as many rules as needed per attribute in this style, general not per-value) ---",
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
        "--- Customer data distinct values (value -> count) ---",
    ]
    n_show = min(20, len(values))
    for v in values[:n_show]:
        val = v.get("value")
        cnt = v.get("count", 0)
        lines.append(f"  - {val!r} -> {cnt}")
    if len(values) > n_show:
        lines.append(f"  ... and {len(values) - n_show} more distinct values.")

    lines.extend([
        "",
        "--- Merged possible values (customer + NEMA/IEC standards + manufacturers) — use this list to derive rules ---",
    ])
    if merged_possible_values:
        for v in merged_possible_values[:100]:  # cap for prompt size
            lines.append(f"  - {v!r}")
        if len(merged_possible_values) > 100:
            lines.append(f"  ... and {len(merged_possible_values) - 100} more.")
    else:
        lines.append("  (none)")

    if standards_context.strip():
        lines.extend([
            "",
            "--- Standards (NEMA, IEC) context (reference) ---",
            (standards_context[:4000] + "...") if len(standards_context) > 4000 else standards_context,
        ])
    if manufacturers_context.strip():
        lines.extend([
            "",
            "--- Manufacturers context (reference) ---",
            (manufacturers_context[:4000] + "...") if len(manufacturers_context) > 4000 else manufacturers_context,
        ])

    lines.append("")
    lines.append(
        "Derive as many generalised normalisation rules as needed for this attribute using the merged possible values above. "
        "Do not list one rule per value; generalise. "
        "Output only the rule lines (tab-separated: Entity, Attribute, Normalization, Rule description, Few Shot examples in format [+] \"input\" -> \"output\"; [-] \"bad\" -> reason), one per line."
    )
    return "\n".join(lines)
