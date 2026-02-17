"""CLI for applying normalisation rules to raw dataset and writing before/after comparison."""

import argparse
from pathlib import Path

from normalisation_rules.apply_rules import (
    load_dataset,
    generate_all_normalisers,
    load_compiled_normalisers,
    apply_normalisers,
    build_comparison_table,
)
from normalisation_rules.codegen import load_generated_code, save_generated_code
from normalisation_rules.config import (
    OUTPUT_RULES_FILE,
    CONTACTORS_DATASET_XLSX,
    CONTACTORS_COMPARISON_XLSX,
    GENERATED_NORMALISERS_JSON,
    ensure_api_keys,
)
from normalisation_rules.export_comparison import write_comparison_workbook
from normalisation_rules.models import get_llm
from normalisation_rules.rules_loader import load_rules_excel, group_rules_by_attribute


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply derived normalisation rules to raw Contactors dataset and write before/after comparison."
    )
    parser.add_argument(
        "--rules",
        type=Path,
        default=OUTPUT_RULES_FILE,
        help="Path to Derived_Normalisation_Rules.xlsx",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=CONTACTORS_DATASET_XLSX,
        help="Path to raw Contactors_Dataset.xlsx",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=CONTACTORS_COMPARISON_XLSX,
        help="Output path for comparison workbook",
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "groq"],
        default="openai",
        help="LLM provider for code generation",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name (default: gpt-4o-mini for OpenAI, llama-3.1-8b-instant for Groq)",
    )
    parser.add_argument(
        "--skip-generate",
        action="store_true",
        help="Reuse stored Python from generated_normalisers.json; do not call LLM",
    )
    parser.add_argument(
        "--limit-rows",
        type=int,
        default=None,
        help="Limit dataset to first N rows for testing",
    )
    args = parser.parse_args()

    if not args.skip_generate:
        missing = ensure_api_keys(use_openai=(args.provider == "openai"), use_groq=(args.provider == "groq"), use_tavily=False)
        if missing:
            print("Missing API keys:", ", ".join(missing))
            raise SystemExit(1)

    if not args.rules.exists():
        print(f"Rules file not found: {args.rules}")
        raise SystemExit(1)
    if not args.dataset.exists():
        print(f"Dataset not found: {args.dataset}")
        raise SystemExit(1)

    print("Loading rules...")
    df_rules = load_rules_excel(args.rules)
    rules_by_attr = group_rules_by_attribute(df_rules)
    print(f"Found {len(rules_by_attr)} attributes with rules.")

    if args.skip_generate:
        print("Loading stored normalisers (--skip-generate)...")
        normalisers = load_compiled_normalisers(rules_by_attr, GENERATED_NORMALISERS_JSON)
        attribute_to_code = load_generated_code(GENERATED_NORMALISERS_JSON)
    else:
        print("Generating Python normalisers via LLM...")
        llm = get_llm(provider=args.provider, model=args.model)
        normalisers = generate_all_normalisers(rules_by_attr, llm, GENERATED_NORMALISERS_JSON)
        attribute_to_code = load_generated_code(GENERATED_NORMALISERS_JSON)
    print(f"Compiled {len(normalisers)} normalisers.")

    print("Loading dataset...")
    df_before = load_dataset(args.dataset)
    if args.limit_rows:
        df_before = df_before.head(args.limit_rows)
        print(f"Limited to {args.limit_rows} rows.")
    print(f"Applying normalisers to {len(df_before)} rows...")
    df_after = apply_normalisers(df_before, normalisers)
    attrs_with_rules = list(normalisers.keys())
    df_comparison = build_comparison_table(df_before, df_after, attrs_with_rules)
    print(f"Comparison: {len(df_comparison)} cells changed.")

    print(f"Writing {args.output}...")
    write_comparison_workbook(
        df_before,
        df_after,
        df_comparison,
        args.output,
        attribute_to_code=attribute_to_code or None,
    )
    print("Done.")


if __name__ == "__main__":
    main()
