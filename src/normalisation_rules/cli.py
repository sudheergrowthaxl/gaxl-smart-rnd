"""CLI entrypoint for deriving normalisation rules."""

import argparse
from pathlib import Path

from normalisation_rules.config import (
    DEFAULT_PROFILING_JSON,
    DEFAULT_FEW_SHOT_PATH,
    OUTPUT_RULES_FILE,
    get_tavily_log_path_for_run,
    get_curated_values_path_for_run,
    DOMAIN,
    DEFAULT_MANUFACTURERS,
    ensure_api_keys,
)
from normalisation_rules.data_loader import load_profiling_json, extract_attributes_for_rules
from normalisation_rules.export import write_rules_to_excel, write_rules_to_text
from normalisation_rules.graph import run_for_attribute
from normalisation_rules.curate_values import save_curated_values
from normalisation_rules.models import get_llm


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Derive normalisation rules for Contactors using profiling JSON, Tavily search (standards + manufacturers), and LLMs (OpenAI/Groq)."
    )
    parser.add_argument(
        "--profiling",
        type=Path,
        default=DEFAULT_PROFILING_JSON,
        help="Path to Contactors_Profiling_distinct_values.json",
    )
    parser.add_argument(
        "--few-shot",
        type=Path,
        default=DEFAULT_FEW_SHOT_PATH,
        help="Path to few-shot examples text file",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=OUTPUT_RULES_FILE,
        help="Output file for derived rules",
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "groq"],
        default="openai",
        help="LLM provider (openai or groq)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name (default: gpt-4o-mini for OpenAI, llama-3.1-8b-instant for Groq)",
    )
    parser.add_argument(
        "--priority-only",
        action="store_true",
        help="Process only priority attributes (zz_Auxiliary Contact, zz_Number of Poles, zz_Mounting Type, zz_Type)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of attributes to process (default: all)",
    )
    parser.add_argument(
        "--no-tavily",
        action="store_true",
        help="Do not use Tavily (skip web search context for both standards and manufacturers)",
    )
    parser.add_argument(
        "--search-depth",
        choices=["basic", "advanced"],
        default="basic",
        help="Tavily search depth: 'basic' (faster, lower cost) or 'advanced' (richer context, higher cost)",
    )
    parser.add_argument(
        "--manufacturers",
        type=str,
        default=None,
        help="Comma-separated list of manufacturers to search (default: ABB,Eaton Cutler Hammer,Schneider Electric,Siemens,Square D)",
    )
    parser.add_argument(
        "--curated-output",
        type=Path,
        default=None,
        help="Path for curated values JSON output (default: auto-timestamped in curated_values/)",
    )
    args = parser.parse_args()

    use_tavily = not args.no_tavily

    # Parse manufacturers list
    if args.manufacturers:
        manufacturers = [m.strip() for m in args.manufacturers.split(",") if m.strip()]
    else:
        manufacturers = DEFAULT_MANUFACTURERS

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
        print(f"Manufacturers to search: {', '.join(manufacturers)}")

    curated_output_path = args.curated_output or get_curated_values_path_for_run()
    print(f"Curated values will be saved to: {curated_output_path}")

    llm = get_llm(provider=args.provider, model=args.model)
    reference = "Profiling; Few-shot examples"
    if use_tavily:
        reference += "; Standards (Tavily); Manufacturer catalogs (Tavily)"

    all_rules: list[tuple[str, str]] = []
    all_curated: list[dict] = []

    for i, attr in enumerate(attributes):
        name = attr.get("name", "?")
        print(f"\n[{i + 1}/{len(attributes)}] Processing: {name}")
        try:
            rules, curated_dict = run_for_attribute(
                llm=llm,
                attribute=attr,
                few_shot_examples=few_shot_text,
                domain=DOMAIN,
                use_tavily=use_tavily,
                tavily_log_path=tavily_log_path,
                search_depth=args.search_depth,
                manufacturers=manufacturers,
            )
            all_curated.append(curated_dict)
            for r in rules:
                all_rules.append((r, reference))
                preview = r[:80] + "..." if len(r) > 80 else r
                print(f"  -> {preview}")
        except Exception as e:
            print(f"  Error: {e}")
            continue

    # Save curated values JSON
    if all_curated:
        save_curated_values(all_curated, curated_output_path)
        print(f"\nSaved curated values for {len(all_curated)} attributes to: {curated_output_path}")

    # Save rules
    if args.output.suffix.lower() == ".xlsx":
        write_rules_to_excel(all_rules, args.output)
    else:
        write_rules_to_text(all_rules, args.output)
    print(f"Wrote {len(all_rules)} rules to {args.output}")


if __name__ == "__main__":
    main()
