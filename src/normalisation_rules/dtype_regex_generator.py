"""
Standalone generator: derive DATA TYPES and REGEX PATTERNS for Contactor attributes.

Inputs (same as normalisation rules pipeline):
  - Profiling JSON  : distinct values + statistics from the Python profiler
  - Tavily standards  : IEC 60947 / NEMA ICS canonical value formats
  - Tavily manufacturers: ABB, Siemens, Schneider Electric, Eaton, Square D catalogs

Persona: Senior Product Manager with deep contactor domain knowledge.

Output: TSV / JSON  →  Attribute | DataType | RegexPattern | PatternDescription

Usage:
    python -m normalisation_rules.dtype_regex_generator
    python -m normalisation_rules.dtype_regex_generator --output out/dtype_regex.tsv
    python -m normalisation_rules.dtype_regex_generator --search-depth advanced --only-priority
    python -m normalisation_rules.dtype_regex_generator --no-tavily
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow `python dtype_regex_generator.py` from any working directory
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from normalisation_rules.config import (
    DEFAULT_MANUFACTURERS,
    DEFAULT_PROFILING_JSON,
    OPENAI_API_KEY,
    TAVILY_API_KEY,
    get_openai_client,
)
from normalisation_rules.data_loader import extract_attributes_for_rules, load_profiling_json
from normalisation_rules.tavily_context import (
    search_attribute_context,
    search_manufacturer_values,
    should_skip_tavily,
)

# ---------------------------------------------------------------------------
# PROMPTS
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a senior product manager with deep domain expertise in electrical contactors
and low-voltage switchgear. You have extensive hands-on experience with IEC 60947 and
NEMA ICS standards, and with how ABB, Siemens, Schneider Electric, Eaton, and Square D
describe and classify contactors in their datasheets and product configurators.

Your task is to define the correct DATA TYPE and a REGEX VALIDATION PATTERN for a
contactor product catalog attribute. You will be given three evidence sources and must
use ALL THREE — they are not optional. Their authority is strictly ranked:

  ★ Priority 1 — STANDARDS (IEC 60947 / NEMA ICS)   [HIGHEST AUTHORITY]
      What IEC 60947 and NEMA ICS define as the canonical terminology, allowed value
      sets, measurement units, and value formats for this attribute. This is the ground
      truth. When standards context is available, it overrides everything else.

  ★ Priority 2 — MANUFACTURER CATALOGS   [SECOND AUTHORITY]
      How ABB, Siemens, Schneider Electric, Eaton, and Square D actually label and
      express this attribute in their datasheets, product selectors, and configurators.
      Use this to confirm or extend what the standard says, and to resolve ambiguity
      when the standard is silent. If multiple manufacturers agree on a format,
      treat that consensus as authoritative.

  ★ Priority 3 — PROFILING STATISTICS (customer data)   [EVIDENCE ONLY — NOT AUTHORITY]
      Observed distinct values with occurrence counts from real customer data. This data
      is frequently dirty: inconsistent formatting, mixed abbreviations, mixed types,
      range-like entries mixed with point values. Use profiling ONLY to:
        (a) understand what the attribute physically represents, and
        (b) as a last-resort fallback when both standards and manufacturer context
            are absent or insufficient.
      NEVER let messy profiling variants drive the data type choice or regex pattern
      when a standard or manufacturer context is available.

Your reasoning process — follow all four steps:
  Step 1 — Read Source 2 (standards) first. Determine whether IEC 60947 or NEMA ICS
           defines this attribute. If yes, that definition is your starting point.
           Then read Source 3 (manufacturers) to confirm or clarify.
           Finally, read Source 1 (profiling) to understand what real values look like.
  Step 2 — Choose the DATA TYPE using the decision rules below. Apply the source
           priority strictly: if standards say the type, use it; if manufacturers
           all agree on a type, use it; only fall back to profiling patterns if
           both higher-priority sources are absent or silent.
  Step 3 — Derive the REGEX from the canonical form defined by the highest-priority
           source that has evidence. Do not build the regex from messy profiling variants.
  Step 4 — Write the PatternDescription. Always state which source drove the decision
           (e.g. "IEC 60947-4-1 defines...", "Manufacturer consensus across ABB/Siemens...",
           "Profiling fallback — no standards or manufacturer context available").

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATA TYPE DECISION RULES  (choose exactly one)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  enum        The attribute has a small, fixed set of canonical values defined or
              strongly implied by IEC, NEMA, or consistent across all major
              manufacturers. The profiling data may show many spelling variants of
              the same underlying options — that is a normalisation problem, not a
              reason to assign string.

  unit_value  A single numeric quantity that always appears with a physical unit
              (e.g. amperes, volts, hertz, kilowatts). The unit is part of the value;
              the canonical form includes both number and unit symbol.

  range       A min–max numeric span with a unit. Use only when the attribute
              intrinsically defines a window (e.g. an operating range or a setting
              band), not when a single measurement value is simply expressed
              approximately.

  code        A structured alphanumeric string that follows a fixed schema but whose
              specific characters vary per product (e.g. contact configurations,
              protection-class codes, frame designations). Distinguish from enum:
              codes follow a constructive pattern; enums are a closed list.

  number      A bare numeric value with no unit, stored as a scalar (e.g. a count
              or index). Use only when the number itself is the complete value with
              no unit attached by convention.

  boolean     Strictly binary: Yes/No, True/False, or 1/0. Use only when the
              attribute has exactly two mutually exclusive states and all major
              sources confirm this.

  string      Free-form text with no enforceable pattern. Use as last resort only
              when no structural constraint can be confirmed from any source.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REGEX CONSTRUCTION RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1. Write a Python re-module compatible regex that validates ONE clean, normalised value.
  2. Anchor all patterns with ^ and $.
  3. Base the pattern on the CANONICAL form (from standards + manufacturers).
     Do not include messy customer-data variants — those are handled by normalisation rules.
  4. For enum     → anchored alternation of canonical values confirmed by IEC/NEMA
                    or consistent across manufacturers: ^(CanonA|CanonB|CanonC)$
  5. For unit_value → use named groups to separate numeric value and unit symbol;
                    include only the canonical unit symbol(s), not abbreviation variants:
                    ^(?P<value>\\d+(\\.\\d+)?)\\s*(?P<unit>UNIT1|UNIT2)$
  6. For range    → named groups for min, max, unit:
                    ^(?P<min>\\d+(\\.\\d+)?)\\s*[–-]\\s*(?P<max>\\d+(\\.\\d+)?)\\s*(?P<unit>UNIT)$
  7. For code     → model the structural schema (prefix, digits, separators, suffix)
                    exactly as confirmed by IEC notation or manufacturer conventions.
  8. For number   → ^\\d+(\\.\\d+)?$
  9. For boolean  → ^(Yes|No)$ or ^(True|False)$ — match the catalog convention.
  10. For string  → output NONE.
  11. If evidence from all three sources is insufficient to write a reliable pattern,
      output NONE and explain why in the PatternDescription.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT — exactly ONE tab-separated line, no header, no markdown
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Attribute\\tDataType\\tRegexPattern\\tPatternDescription

Output ONLY that single line — no reasoning text, no headers, no code fences.
"""


def build_user_prompt(
    attribute: dict,
    standards_context: str,
    manufacturer_context: str,
) -> str:
    """Assemble the user message sent to the LLM for one attribute."""
    name = attribute.get("name", "")
    datatype = attribute.get("datatype", "")
    semantic_type = attribute.get("semantic_type", "")
    missing = attribute.get("missing_percentage")
    range_val = attribute.get("range")
    values = attribute.get("values", [])

    lines = [
        f"Attribute: {name}",
        "",
        "── Source 1: Profiling statistics (customer data — may be messy) ──────────",
        f"  Profiler inferred datatype : {datatype}",
        f"  Semantic type              : {semantic_type}",
        f"  Missing %                  : {missing}",
        f"  Observed value range       : {range_val}",
        f"  Total distinct values      : {len(values)}",
        "",
        "  Distinct values with occurrence counts (top 25, ordered by frequency):",
    ]
    shown = values[:25]
    for v in shown:
        val = v.get("value")
        cnt = v.get("count", 0)
        lines.append(f"    {val!r}  →  {cnt} occurrences")
    if len(values) > len(shown):
        lines.append(f"    ... and {len(values) - len(shown)} more distinct values not shown.")

    if standards_context.strip():
        lines += [
            "",
            "── Source 2: Standards context (IEC 60947 / NEMA ICS) ─────────────────",
            standards_context[:6000],
        ]
    else:
        lines += [
            "",
            "── Source 2: Standards context (IEC 60947 / NEMA ICS) ─────────────────",
            "  (no standards context retrieved)",
        ]

    if manufacturer_context.strip():
        lines += [
            "",
            "── Source 3: Manufacturer catalog context ──────────────────────────────",
            "  (ABB, Siemens, Schneider Electric, Eaton, Square D datasheets / selectors)",
            manufacturer_context[:6000],
        ]
    else:
        lines += [
            "",
            "── Source 3: Manufacturer catalog context ──────────────────────────────",
            "  (no manufacturer context retrieved)",
        ]

    lines += [
        "",
        "── Your task ────────────────────────────────────────────────────────────",
        f"Derive the correct DATA TYPE and REGEX PATTERN for '{name}' as it should",
        f"appear in a clean, normalised contactor product catalog.",
        "",
        "Follow this source priority strictly:",
        "",
        "  STEP 1 — Start with Source 2 (IEC 60947 / NEMA ICS standards).",
        "           If standards context is present, it is your primary authority.",
        "           Identify the canonical value format and unit defined by the standard.",
        "",
        "  STEP 2 — Cross-check with Source 3 (manufacturer catalogs).",
        "           If manufacturers (ABB, Siemens, Schneider, Eaton, Square D) agree",
        "           on a format, use that to confirm or extend the standard's definition.",
        "           If standards are silent, manufacturer consensus becomes the authority.",
        "",
        "  STEP 3 — Use Source 1 (profiling) only to understand WHAT the attribute",
        "           physically represents, or as a last resort if Sources 2 and 3 are",
        "           both absent. NEVER use messy profiling variants to define the regex.",
        "           If you use profiling as fallback, say so explicitly in the description.",
        "",
        "  STEP 4 — Output one tab-separated line. In PatternDescription, state which",
        "           source drove your decision: IEC 60947 / NEMA / manufacturer consensus /",
        "           profiling fallback.",
        "",
        "Respond with exactly ONE tab-separated line (no header, no markdown):",
        "Attribute\\tDataType\\tRegexPattern\\tPatternDescription",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PIPELINE
# ---------------------------------------------------------------------------

def run(
    profiling_json: Path | None = None,
    output_csv: Path | None = None,
    output_json: Path | None = None,
    use_tavily: bool = True,
    search_depth: str = "basic",
    manufacturers: list[str] | None = None,
    only_priority: bool = False,
) -> list[dict]:
    """
    Run the data type + regex pattern generator for all (or priority) attributes.

    Returns
    -------
    list of dicts:
        { attribute, data_type, regex_pattern, description,
          standards_context, manufacturer_context }
    """
    if not OPENAI_API_KEY:
        raise EnvironmentError("OPENAI_API_KEY is not set. Add it to your .env file.")

    profiling_path = profiling_json or DEFAULT_PROFILING_JSON
    if not profiling_path.exists():
        raise FileNotFoundError(f"Profiling JSON not found: {profiling_path}")

    mfrs = manufacturers or DEFAULT_MANUFACTURERS
    client = get_openai_client()

    print(f"\nLoading profiling data: {profiling_path}")
    profiling = load_profiling_json(profiling_path)
    attributes = extract_attributes_for_rules(profiling, only_priority=only_priority)
    print(f"  {len(attributes)} attributes to process.\n")

    results: list[dict] = []

    for i, attr in enumerate(attributes, 1):
        name = attr["name"]
        print(f"[{i}/{len(attributes)}] {name}")

        # ── Tavily searches ──────────────────────────────────────────────────
        standards_ctx = ""
        manufacturer_ctx = ""
        sample_vals = [str(v.get("value", "")) for v in attr.get("values", [])[:5]]

        if use_tavily and TAVILY_API_KEY:
            if not should_skip_tavily(name):
                print("  Searching standards context (IEC/NEMA)...")
                standards_ctx, _ = search_attribute_context(
                    attribute_name=name,
                    sample_values=sample_vals,
                    search_depth=search_depth,
                )
                print("  Searching manufacturer catalog context...")
                manufacturer_ctx, _ = search_manufacturer_values(
                    attribute_name=name,
                    manufacturers=mfrs,
                    sample_values=sample_vals,
                    search_depth=search_depth,
                )
            else:
                print("  Skipping Tavily (attribute not suitable for web search).")
        elif use_tavily and not TAVILY_API_KEY:
            print("  TAVILY_API_KEY not set — skipping web search.")

        # ── LLM call ─────────────────────────────────────────────────────────
        user_msg = build_user_prompt(attr, standards_ctx, manufacturer_ctx)
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.1,
                max_tokens=256,
            )
            raw_line = (response.choices[0].message.content or "").strip()
        except Exception as exc:
            print(f"  LLM error: {exc}")
            raw_line = f"{name}\terror\tNONE\tLLM error: {exc}"

        # ── Parse TSV line ────────────────────────────────────────────────────
        # LLM sometimes outputs literal \t instead of real tab characters — normalise
        raw_line = raw_line.replace("\\t", "\t")
        parts = raw_line.split("\t")
        if len(parts) >= 4:
            rec = {
                "attribute": parts[0].strip(),
                "data_type": parts[1].strip(),
                "regex_pattern": parts[2].strip(),
                "description": parts[3].strip(),
                "standards_context": standards_ctx,
                "manufacturer_context": manufacturer_ctx,
            }
        else:
            # Fallback: LLM didn't follow format — store raw output
            rec = {
                "attribute": name,
                "data_type": "unknown",
                "regex_pattern": "NONE",
                "description": raw_line,
                "standards_context": standards_ctx,
                "manufacturer_context": manufacturer_ctx,
            }

        results.append(rec)
        print(f"  → data_type={rec['data_type']}  |  regex={rec['regex_pattern']}")

    # ── Save outputs ──────────────────────────────────────────────────────────
    if output_csv:
        import csv
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(output_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["attribute", "data_type", "regex_pattern", "description"],
            )
            writer.writeheader()
            for r in results:
                writer.writerow({
                    "attribute": r["attribute"],
                    "data_type": r["data_type"],
                    "regex_pattern": r["regex_pattern"],
                    "description": r["description"],
                })
        print(f"\nCSV saved → {output_csv}")

    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        slim = [
            {
                "attribute": r["attribute"],
                "data_type": r["data_type"],
                "regex_pattern": r["regex_pattern"],
                "description": r["description"],
            }
            for r in results
        ]
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(slim, f, indent=2, ensure_ascii=False)
        print(f"JSON saved → {output_json}")

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate data types and regex patterns for Contactor attributes.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--profiling-json",
        type=Path,
        default=None,
        help="Path to profiling distinct-values JSON (default: project default)",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Output CSV file path (default: <project_root>/DataType_Regex_Patterns.csv)",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Also save results as JSON (optional)",
    )
    parser.add_argument(
        "--no-tavily",
        action="store_true",
        help="Disable Tavily web search (run on profiling data only)",
    )
    parser.add_argument(
        "--search-depth",
        choices=["basic", "advanced"],
        default="basic",
        help="Tavily search depth: basic (faster/cheaper) or advanced (richer context)",
    )
    parser.add_argument(
        "--only-priority",
        action="store_true",
        help="Process only priority attributes (zz_Auxiliary Contact, zz_Number of Poles, etc.)",
    )
    args = parser.parse_args()

    csv_out = args.output_csv or (_PROJECT_ROOT / "DataType_Regex_Patterns.csv")

    run(
        profiling_json=args.profiling_json,
        output_csv=csv_out,
        output_json=args.output_json,
        use_tavily=not args.no_tavily,
        search_depth=args.search_depth,
        only_priority=args.only_priority,
    )
