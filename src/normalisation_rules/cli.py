"""CLI entrypoint for deriving and validating normalisation rules."""

import argparse
from collections import defaultdict
from pathlib import Path

from normalisation_rules.config import (
    DEFAULT_PROFILING_JSON,
    DEFAULT_FEW_SHOT_PATH,
    OUTPUT_RULES_FILE,
    get_tavily_log_path_for_run,
    DOMAIN,
    ensure_api_keys,
    PROJECT_ROOT,
)
from normalisation_rules.data_loader import load_profiling_json, extract_attributes_for_rules
from normalisation_rules.export import (
    write_rules_to_excel,
    write_rules_to_text,
    load_rules_from_excel,
    load_validated_rules_from_excel,
    write_validated_rules_to_excel,
    write_few_shot_rules_to_excel,
)
from normalisation_rules.graph import run_for_attribute
from normalisation_rules.models import get_llm


def _cmd_derive(args: argparse.Namespace) -> None:
    """Derive normalisation rules (original behaviour)."""
    use_tavily = not args.no_tavily
    missing = ensure_api_keys(
        use_openai=(args.provider == "openai"),
        use_groq=(args.provider == "groq"),
        use_tavily=use_tavily,
    )
    if missing:
        print("Missing API keys:", ", ".join(missing))
        print("Set them in .env or environment and run again.")
        raise SystemExit(1)

    if not args.profiling.exists():
        print(f"Profiling file not found: {args.profiling}")
        raise SystemExit(1)
    if not args.few_shot.exists():
        print(f"Few-shot file not found: {args.few_shot}")
        raise SystemExit(1)

    few_shot_text = args.few_shot.read_text(encoding="utf-8")
    profiling = load_profiling_json(args.profiling)
    attributes = extract_attributes_for_rules(profiling, only_priority=args.priority_only)
    if args.limit:
        attributes = attributes[: args.limit]

    if not attributes:
        print("No attributes to process.")
        raise SystemExit(0)

    tavily_log_path: str | None = None
    if use_tavily:
        tavily_log_path = str(get_tavily_log_path_for_run())
        print(f"Tavily context will be logged to: {tavily_log_path}")

    llm = get_llm(provider=args.provider, model=args.model)
    reference = "Profiling; Few-shot examples" + ("; Web search (Tavily)" if use_tavily else "")
    all_rules: list[tuple[str, str]] = []

    for i, attr in enumerate(attributes):
        name = attr.get("name", "?")
        print(f"[{i + 1}/{len(attributes)}] Processing: {name}")
        try:
            rules = run_for_attribute(
                llm=llm,
                attribute=attr,
                few_shot_examples=few_shot_text,
                domain=DOMAIN,
                use_tavily=use_tavily,
                tavily_log_path=tavily_log_path,
                search_depth=args.search_depth,
            )
            for r in rules:
                all_rules.append((r, reference))
                preview = r[:80] + "..." if len(r) > 80 else r
                print(f"  -> {preview}")
        except Exception as e:
            print(f"  Error: {e}")
            continue

    if args.output.suffix.lower() == ".xlsx":
        write_rules_to_excel(all_rules, args.output)
    else:
        write_rules_to_text(all_rules, args.output)
    print(f"Wrote {len(all_rules)} rules to {args.output}")


def _cmd_validate(args: argparse.Namespace) -> None:
    """Validate existing normalisation rules against manufacturer datasheets."""
    from normalisation_rules.validation import run_validation

    missing = ensure_api_keys(
        use_openai=(args.provider == "openai"),
        use_groq=(args.provider == "groq"),
        use_tavily=True,
    )
    if missing:
        print("Missing API keys:", ", ".join(missing))
        print("Set them in .env or environment and run again.")
        raise SystemExit(1)

    input_path = args.input
    if not input_path.exists():
        print(f"Input rules file not found: {input_path}")
        raise SystemExit(1)

    print(f"Loading rules from: {input_path}")
    rules = load_rules_from_excel(input_path)
    print(f"Loaded {len(rules)} rules")

    if not rules:
        print("No rules to validate.")
        raise SystemExit(0)

    # Group rules by attribute (one Tavily call per attribute)
    rules_by_attribute: dict[str, list[dict]] = defaultdict(list)
    for rule in rules:
        rules_by_attribute[rule["attribute"]].append(rule)
    print(f"Found {len(rules_by_attribute)} unique attributes")

    # Setup Tavily logging
    tavily_log_path = str(get_tavily_log_path_for_run())
    print(f"Tavily datasheet search logs: {tavily_log_path}")

    llm = get_llm(provider=args.provider, model=args.model)

    print(f"\nStarting validation (search_depth={args.search_depth})...")
    print("=" * 60)

    validated_rules = run_validation(
        rules_by_attribute=dict(rules_by_attribute),
        llm=llm,
        domain="electrical contactors",
        search_depth=args.search_depth,
        log_path=tavily_log_path,
        limit=args.limit,
    )

    # Write output
    write_validated_rules_to_excel(validated_rules, args.output)

    # Summary
    valid_count = sum(1 for r in validated_rules if r.get("validation") == "Valid")
    invalid_count = sum(1 for r in validated_rules if r.get("validation") == "Invalid")
    review_count = sum(1 for r in validated_rules if r.get("validation") == "Needs Review")
    total = len(validated_rules)

    print("\n" + "=" * 60)
    print(f"Validation complete: {total} rules validated")
    print(f"  Valid:        {valid_count} ({valid_count * 100 // total if total else 0}%)")
    print(f"  Invalid:      {invalid_count} ({invalid_count * 100 // total if total else 0}%)")
    print(f"  Needs Review: {review_count} ({review_count * 100 // total if total else 0}%)")
    print(f"\nOutput written to: {args.output}")


def _cmd_few_shot(args: argparse.Namespace) -> None:
    """Generate few-shot examples (positive + negative) for existing rules."""
    from normalisation_rules.validation import run_few_shot_generation

    missing = ensure_api_keys(
        use_openai=(args.provider == "openai"),
        use_groq=(args.provider == "groq"),
        use_tavily=True,
    )
    if missing:
        print("Missing API keys:", ", ".join(missing))
        print("Set them in .env or environment and run again.")
        raise SystemExit(1)

    input_path = args.input
    if not input_path.exists():
        print(f"Input rules file not found: {input_path}")
        raise SystemExit(1)

    # Auto-detect if input has validation columns
    print(f"Loading rules from: {input_path}")
    try:
        rules = load_validated_rules_from_excel(input_path)
    except Exception:
        rules = load_rules_from_excel(input_path)
    print(f"Loaded {len(rules)} rules")

    if not rules:
        print("No rules to process.")
        raise SystemExit(0)

    # Group rules by attribute
    rules_by_attribute: dict[str, list[dict]] = defaultdict(list)
    for rule in rules:
        rules_by_attribute[rule["attribute"]].append(rule)
    print(f"Found {len(rules_by_attribute)} unique attributes")

    # Setup Tavily logging
    tavily_log_path = str(get_tavily_log_path_for_run())
    print(f"Tavily datasheet search logs: {tavily_log_path}")

    llm = get_llm(provider=args.provider, model=args.model)

    print(f"\nGenerating few-shot examples (search_depth={args.search_depth})...")
    print("=" * 60)

    enriched_rules = run_few_shot_generation(
        rules_by_attribute=dict(rules_by_attribute),
        llm=llm,
        domain="electrical contactors",
        search_depth=args.search_depth,
        log_path=tavily_log_path,
        limit=args.limit,
    )

    # Write output
    write_few_shot_rules_to_excel(enriched_rules, args.output)

    print("\n" + "=" * 60)
    print(f"Few-shot examples generated for {len(enriched_rules)} rules")
    print(f"Output written to: {args.output}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Derive and validate normalisation rules for Contactors."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- derive subcommand (original behaviour) ---
    derive_parser = subparsers.add_parser(
        "derive",
        help="Derive normalisation rules from profiling data",
    )
    derive_parser.add_argument(
        "--profiling",
        type=Path,
        default=DEFAULT_PROFILING_JSON,
        help="Path to Contactors_Profiling_distinct_values.json",
    )
    derive_parser.add_argument(
        "--few-shot",
        type=Path,
        default=DEFAULT_FEW_SHOT_PATH,
        help="Path to few-shot examples text file",
    )
    derive_parser.add_argument(
        "--output", "-o",
        type=Path,
        default=OUTPUT_RULES_FILE,
        help="Output file for derived rules",
    )
    derive_parser.add_argument(
        "--provider",
        choices=["openai", "groq"],
        default="openai",
        help="LLM provider (openai or groq)",
    )
    derive_parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name (default: gpt-4o-mini for OpenAI, llama-3.1-8b-instant for Groq)",
    )
    derive_parser.add_argument(
        "--priority-only",
        action="store_true",
        help="Process only priority attributes",
    )
    derive_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of attributes to process",
    )
    derive_parser.add_argument(
        "--no-tavily",
        action="store_true",
        help="Skip Tavily web search context",
    )
    derive_parser.add_argument(
        "--search-depth",
        choices=["basic", "advanced"],
        default="basic",
        help="Tavily search depth",
    )

    # --- validate subcommand ---
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate existing rules against manufacturer datasheets",
    )
    validate_parser.add_argument(
        "--input", "-i",
        type=Path,
        default=OUTPUT_RULES_FILE,
        help="Input Excel file with derived rules (default: Derived_Normalisation_Rules.xlsx)",
    )
    validate_parser.add_argument(
        "--output", "-o",
        type=Path,
        default=PROJECT_ROOT / "Validated_Normalisation_Rules.xlsx",
        help="Output Excel file with validation results",
    )
    validate_parser.add_argument(
        "--provider",
        choices=["openai", "groq"],
        default="openai",
        help="LLM provider (openai or groq)",
    )
    validate_parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name",
    )
    validate_parser.add_argument(
        "--search-depth",
        choices=["basic", "advanced"],
        default="advanced",
        help="Tavily search depth (default: advanced for richer datasheet context)",
    )
    validate_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of attributes to validate (default: all)",
    )

    # --- few-shot subcommand ---
    few_shot_parser = subparsers.add_parser(
        "few-shot",
        help="Generate few-shot examples (positive + negative) for existing rules",
    )
    few_shot_parser.add_argument(
        "--input", "-i",
        type=Path,
        default=OUTPUT_RULES_FILE,
        help="Input Excel file with rules (derived or validated)",
    )
    few_shot_parser.add_argument(
        "--output", "-o",
        type=Path,
        default=PROJECT_ROOT / "Rules_with_Few_Shot_Examples.xlsx",
        help="Output Excel file with few-shot examples column",
    )
    few_shot_parser.add_argument(
        "--provider",
        choices=["openai", "groq"],
        default="openai",
        help="LLM provider (openai or groq)",
    )
    few_shot_parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name",
    )
    few_shot_parser.add_argument(
        "--search-depth",
        choices=["basic", "advanced"],
        default="advanced",
        help="Tavily search depth (default: advanced for realistic example values)",
    )
    few_shot_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of attributes to process (default: all)",
    )

    args = parser.parse_args()

    if args.command == "derive":
        _cmd_derive(args)
    elif args.command == "validate":
        _cmd_validate(args)
    elif args.command == "few-shot":
        _cmd_few_shot(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
