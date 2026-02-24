"""Generate few-shot examples for each rule in Derived_Normalisation_Rules.xlsx.

For every rule, uses the LLM to apply the rule to the real observed values
from the profiling JSON and produces only the valid [+] mappings
(input value -> normalised output value).

Writes a new Excel file with the same columns as the input, plus a
"Few Shots" column inserted after "Rule description".

Usage:
    python -m normalisation_rules.few_shots_generator [--input FILE] [--output FILE]
"""

import argparse
import re
from pathlib import Path

import openpyxl
from openpyxl.styles import Font
from langchain_core.messages import HumanMessage, SystemMessage

from normalisation_rules.config import PROJECT_ROOT, DEFAULT_PROFILING_JSON
from normalisation_rules.data_loader import load_profiling_json
from normalisation_rules.models import get_llm

DEFAULT_INPUT = PROJECT_ROOT / "Derived_Normalisation_Rules.xlsx"
DEFAULT_OUTPUT = PROJECT_ROOT / "Derived_Rules_with_FewShots_19.xlsx"

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a data normalisation expert. Given a normalisation rule and a list of \
observed values from real product data, your job is to identify which observed \
values are VALID and accepted by the rule, and show how they map to the \
normalised output.

Output ONLY the valid mappings, one per line, in this exact format:
[+] "input value" -> "normalised value"

Rules:
- Only include values that are clearly accepted/normalised by the rule.
- Do NOT include rejected, non-standard, or ambiguous values.
- Do NOT include any explanation, headers, or extra text.
- If no observed value matches the rule, output: NONE

--- FEW-SHOT REFERENCE EXAMPLES ---

# Multi-value fields
# Rule: attribute accepts multiple values.
# The canonical normalised separator is " || " (space-double-pipe-space).
# If the observed value already uses " || ", keep it exactly as-is.
# If the observed value uses "/" (slash) as separator, convert it to " || ".
[+] "DIN Rail Mount || Panel Mount" -> "DIN Rail Mount || Panel Mount"
[+] "AC || DC"                      -> "AC || DC"
[+] "50 Hz || 60 Hz"                -> "50 Hz || 60 Hz"
[+] "IEC || UL"                     -> "IEC || UL"
[+] "AC/DC"                         -> "AC || DC"
[+] "DIN Rail Mount/Panel Mount"    -> "DIN Rail Mount || Panel Mount"

# Auxiliary Contact normalization
# Rule: value must follow "XNO+YNC" pattern (NO count first, then NC count).
# Values already in correct combined format are kept as-is.
# Values with only one pole specified must have the missing pole added with count 0.
[+] "2NO+1NC" -> "2NO+1NC"
[+] "1NO+1NC" -> "1NO+1NC"
[+] "1NC"     -> "1NC+0NO"
[+] "1NO"     -> "1NO+0NC"
[+] "2NC"     -> "2NC+0NO"
[+] "2NO"     -> "2NO+0NC"

--- END OF REFERENCE EXAMPLES ---
"""


def _build_user_prompt(rule_description: str, observed_values: list[str]) -> str:
    values_str = "\n".join(f"- {v}" for v in observed_values)
    return (
        f"Rule:\n{rule_description}\n\n"
        f"Observed values:\n{values_str}\n\n"
        f"Generate only the valid [+] mappings."
    )


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

MAX_OBSERVED_VALUES = 200

# Attributes that are IDs / free-text descriptions — no useful few-shots possible.
# Skip LLM call entirely and leave Few Shots blank for these.
SKIP_ATTRIBUTES = {
    "zz_UPC Code",
    "zz_Web Overview",
    "zz_80 Character Description",
    "zz_Alternate Mfr Part Number",
}


def _get_observed_values(profiling: dict, attribute_name: str) -> list[str]:
    """Return list of distinct observed value strings for the given attribute.

    Capped at MAX_OBSERVED_VALUES to avoid exceeding the LLM context limit
    for attributes like zz_UPC Code or zz_Web Overview that have thousands of values.
    Meaningful attributes (e.g. zz_Auxiliary Contact, zz_Control Voltage) stay under
    this cap and get all their values sent.
    """
    attr_data = profiling.get(attribute_name, {})
    raw = attr_data.get("distinct_values") or attr_data.get("top_values") or []
    values = [str(v.get("value", "")).strip() for v in raw if v.get("value")]
    return values[:MAX_OBSERVED_VALUES]


_MAPPING_RE = re.compile(r'\[\+\]\s+"([^"]+)"\s+->\s+"([^"]+)"')
_CONTACT_ONLY_NC = re.compile(r'^\d+NC$', re.IGNORECASE)
_CONTACT_ONLY_NO = re.compile(r'^\d+NO$', re.IGNORECASE)


def _post_process_mappings(lines: list[str]) -> list[str]:
    """Fix known normalisation issues that the LLM consistently gets wrong.

    Rule 1 – Slash → double-pipe:
        If the input value contains "/" (used as a multi-value separator),
        the output must replace every "/" with "||" and keep ALL values.
        The LLM tends to drop values after the slash; this forces the full
        combined value through regardless of what the LLM produced.

        Input examples              LLM (wrong)              Fixed output
        --------------------------  -----------------------  --------------------------------
        "DIN Rail/Panel Mount"   -> "DIN Rail Mount"     =>  "DIN Rail || Panel Mount"
        "AC/DC"                  -> "AC"                 =>  "AC || DC"
        "50 Hz/60 Hz"            -> "50 Hz"              =>  "50 Hz || 60 Hz"

    Rule 2 – Auxiliary Contact single-pole expansion:
        Normalised contact values must follow the "XNO+YNC" pattern.
        If the LLM emits only one pole, the missing pole is appended with count 0.

        Input examples   LLM (wrong)   Fixed output
        ---------------  ------------  ---------------
        "1NC"         -> "1NC"      =>  "1NC+0NO"
        "1NO"         -> "1NO"      =>  "1NO+0NC"
        "2NC"         -> "2NC"      =>  "2NC+0NO"
        "2NO+1NC"     -> "2NO+1NC"  =>  "2NO+1NC"  (already correct — unchanged)
    """
    fixed = []
    for line in lines:
        m = _MAPPING_RE.search(line)
        if not m:
            fixed.append(line)
            continue

        inp, out = m.group(1), m.group(2)

        # Rule 1: slash → double-pipe with spaces (takes priority)
        if "/" in inp:
            out = inp.replace("/", " || ")
            line = f'[+] "{inp}" -> "{out}"'

        # Rule 2: auxiliary contact – add missing pole
        elif _CONTACT_ONLY_NC.match(out):
            out = f"{out}+0NO"
            line = f'[+] "{inp}" -> "{out}"'
        elif _CONTACT_ONLY_NO.match(out):
            out = f"{out}+0NC"
            line = f'[+] "{inp}" -> "{out}"'

        fixed.append(line)
    return fixed


def _generate_few_shots(llm, rule_description: str, observed_values: list[str]) -> str:
    """Call LLM to generate [+] mappings for valid values. Returns formatted string."""
    if not observed_values:
        return ""

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=_build_user_prompt(rule_description, observed_values)),
    ]
    try:
        response = llm.invoke(messages)
        content = (getattr(response, "content", "") or "").strip()
    except Exception as e:
        print(f"    [LLM Error] {e}")
        return ""

    if content.upper() == "NONE" or not content:
        return ""

    # Keep only lines that start with [+]
    valid_lines = [
        line.strip()
        for line in content.splitlines()
        if line.strip().startswith("[+]")
    ]

    # Apply deterministic post-processing to fix known LLM failure patterns
    valid_lines = _post_process_mappings(valid_lines)

    return "; ".join(valid_lines)


def generate_few_shots_excel(
    input_path: Path = DEFAULT_INPUT,
    output_path: Path = DEFAULT_OUTPUT,
    profiling_path: Path = DEFAULT_PROFILING_JSON,
    provider: str = "openai",
    model: str | None = None,
) -> Path:
    """Read derived rules Excel, add Few Shots column, write new Excel.

    Returns the output path.
    """
    profiling = load_profiling_json(profiling_path)
    llm = get_llm(provider=provider, model=model)

    wb_in = openpyxl.load_workbook(input_path)
    ws_in = wb_in.active

    # Read header row
    headers = [cell.value for cell in ws_in[1]]
    # Insert "Few Shots" after "Rule description" (index 3, 0-based)
    rule_desc_idx = headers.index("Rule description") if "Rule description" in headers else 3
    new_headers = headers[:rule_desc_idx + 1] + ["Few Shots"] + headers[rule_desc_idx + 1:]

    wb_out = openpyxl.Workbook()
    ws_out = wb_out.active
    ws_out.title = "Normalisation Rules"

    # Write header
    for col, h in enumerate(new_headers, start=1):
        cell = ws_out.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True)

    total = ws_in.max_row - 1
    print(f"Processing {total} rules...\n")

    for i, row in enumerate(ws_in.iter_rows(min_row=2, values_only=True), start=1):
        attribute = (row[1] or "").strip()
        rule_desc = (row[rule_desc_idx] or "").strip()

        print(f"[{i}/{total}] {attribute}")

        if attribute in SKIP_ATTRIBUTES:
            print(f"    -> (skipped — ID/free-text attribute)")
            few_shots = ""
        else:
            observed = _get_observed_values(profiling, attribute)
            few_shots = _generate_few_shots(llm, rule_desc, observed)

        if few_shots:
            print(f"    -> {few_shots[:100]}{'...' if len(few_shots) > 100 else ''}")
        else:
            print(f"    -> (no valid mappings)")

        # Build output row with Few Shots inserted after Rule description
        row_list = list(row)
        new_row = row_list[:rule_desc_idx + 1] + [few_shots] + row_list[rule_desc_idx + 1:]

        for col, val in enumerate(new_row, start=1):
            ws_out.cell(row=i + 1, column=col, value=val)

    # Column widths
    ws_out.column_dimensions["A"].width = 14
    ws_out.column_dimensions["B"].width = 32
    ws_out.column_dimensions["C"].width = 16
    ws_out.column_dimensions["D"].width = 70
    ws_out.column_dimensions["E"].width = 80  # Few Shots
    ws_out.column_dimensions["F"].width = 40  # Reference

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb_out.save(output_path)
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate few-shot examples for each derived normalisation rule."
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input derived rules Excel (default: {DEFAULT_INPUT.name})",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output Excel with Few Shots column (default: {DEFAULT_OUTPUT.name})",
    )
    parser.add_argument(
        "--profiling",
        type=Path,
        default=DEFAULT_PROFILING_JSON,
        help="Path to profiling JSON (default: Contactors_Profiling_distinct_values.json)",
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "groq"],
        default="openai",
        help="LLM provider (default: openai)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name (default: gpt-4o-mini for OpenAI)",
    )
    args = parser.parse_args()

    out = generate_few_shots_excel(
        input_path=args.input,
        output_path=args.output,
        profiling_path=args.profiling,
        provider=args.provider,
        model=args.model,
    )
    print(f"\nDone. Output saved to: {out}")


if __name__ == "__main__":
    main()
