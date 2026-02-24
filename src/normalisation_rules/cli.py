"""CLI entrypoint for the full pipeline: normalisation rules, hierarchy, attribute resolver."""

import argparse
import json
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
    HIERARCHY_OUTPUT_CSV,
    HIERARCHY_CRAWLED_PATHS_JSON,
    HIERARCHY_RECOMMENDED_JSON,
    ATTRIBUTE_RESOLVER_OUTPUT_JSON,
    ATTRIBUTE_RESOLVER_OUTPUT_CSV,
)
from normalisation_rules.data_loader import load_profiling_json, extract_attributes_for_rules
from normalisation_rules.export import write_rules_to_excel, write_rules_to_text
from normalisation_rules.graph import run_for_attribute
from normalisation_rules.curate_values import save_curated_values
from normalisation_rules.models import get_llm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ask_yes_no(prompt: str) -> bool:
    """Ask a yes/no question. Returns True for y/yes, False for n/no/Enter."""
    while True:
        ans = input(prompt).strip().lower()
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no", ""):
            return False
        print("  Please enter y or n.")


def _section(label: str) -> None:
    print()
    print("=" * 60)
    print(label)
    print("=" * 60)


# ---------------------------------------------------------------------------
# Step runners
# ---------------------------------------------------------------------------

def _run_normalisation_rules(args: argparse.Namespace) -> None:
    """Run the normalisation rules pipeline."""
    use_tavily = not args.no_tavily

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
        print("  Missing API keys:", ", ".join(missing))
        print("  Set them in .env or environment and re-run.")
        return

    if not args.profiling.exists():
        print(f"  Profiling file not found: {args.profiling}")
        return
    if not args.few_shot.exists():
        print(f"  Few-shot file not found: {args.few_shot}")
        return

    few_shot_text = args.few_shot.read_text(encoding="utf-8")
    profiling = load_profiling_json(args.profiling)
    attributes = extract_attributes_for_rules(profiling, only_priority=args.priority_only)
    if args.limit:
        attributes = attributes[: args.limit]

    if not attributes:
        print("  No attributes to process.")
        return

    tavily_log_path: str | None = None
    if use_tavily:
        tavily_log_path = str(get_tavily_log_path_for_run())
        print(f"  Tavily log: {tavily_log_path}")
        print(f"  Manufacturers: {', '.join(manufacturers)}")

    curated_output_path = args.curated_output or get_curated_values_path_for_run()
    print(f"  Curated values: {curated_output_path}")

    llm = get_llm(provider=args.provider, model=args.model)
    reference = "Profiling; Few-shot examples"
    if use_tavily:
        reference += "; Standards (Tavily); Manufacturer catalogs (Tavily)"

    all_rules: list[tuple[str, str]] = []
    all_curated: list[dict] = []

    for i, attr in enumerate(attributes):
        name = attr.get("name", "?")
        print(f"\n  [{i + 1}/{len(attributes)}] Processing: {name}")
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
                print(f"    -> {preview}")
        except Exception as e:
            print(f"    Error: {e}")
            continue

    if all_curated:
        save_curated_values(all_curated, curated_output_path)
        print(f"\n  Saved curated values for {len(all_curated)} attributes to: {curated_output_path}")

    if args.output.suffix.lower() == ".xlsx":
        write_rules_to_excel(all_rules, args.output)
    else:
        write_rules_to_text(all_rules, args.output)
    print(f"  Wrote {len(all_rules)} rules to {args.output}")


def _run_hierarchy() -> None:
    """Run the hierarchy resolution pipeline for Contactors."""
    import pandas as pd
    from normalisation_rules.hierarchy.resolver import standardize_hierarchy

    category = "contactors"
    df = pd.DataFrame({"category": [category]})
    print(f"  Resolving hierarchy for: {category}")

    standardized_df, json_records = standardize_hierarchy(
        df,
        "category",
        crawled_paths_output_path=str(HIERARCHY_CRAWLED_PATHS_JSON),
    )

    standardized_df.to_csv(HIERARCHY_OUTPUT_CSV, index=False)

    with open(HIERARCHY_RECOMMENDED_JSON, "w", encoding="utf-8") as f:
        json.dump(json_records, f, indent=2, ensure_ascii=False)

    print(f"  Saved hierarchy CSV         : {HIERARCHY_OUTPUT_CSV}")
    print(f"  Saved recommended hierarchies: {HIERARCHY_RECOMMENDED_JSON}")
    print(f"  Saved crawled paths          : {HIERARCHY_CRAWLED_PATHS_JSON}")


def _run_attribute_resolver() -> None:
    """Run the attribute resolution pipeline for Contactors."""
    from normalisation_rules.attribute_resolver.resolver import standardize_attributes

    result, rows = standardize_attributes(
        category="contactors",
        output_json_path=str(ATTRIBUTE_RESOLVER_OUTPUT_JSON),
        output_csv_path=str(ATTRIBUTE_RESOLVER_OUTPUT_CSV),
    )

    reasoning_preview = (result.get("reasoning") or "")[:200]
    if reasoning_preview:
        print(f"  Reasoning  : {reasoning_preview}...")
    print(f"  Supply chain attributes: {len(result.get('supply_chain_attributes', []))}")
    print(f"  Ecommerce attributes   : {len(result.get('ecommerce_attributes', []))}")
    print(f"  Saved attributes JSON  : {ATTRIBUTE_RESOLVER_OUTPUT_JSON}")
    print(f"  Saved attributes CSV   : {ATTRIBUTE_RESOLVER_OUTPUT_CSV}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline: normalisation rules → hierarchy resolution → attribute resolution."
    )
    # Normalisation rules options
    parser.add_argument("--profiling", type=Path, default=DEFAULT_PROFILING_JSON)
    parser.add_argument("--few-shot", type=Path, default=DEFAULT_FEW_SHOT_PATH)
    parser.add_argument("--output", "-o", type=Path, default=OUTPUT_RULES_FILE)
    parser.add_argument("--provider", choices=["openai", "groq"], default="openai")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--priority-only", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-tavily", action="store_true")
    parser.add_argument("--search-depth", choices=["basic", "advanced"], default="basic")
    parser.add_argument("--manufacturers", type=str, default=None)
    parser.add_argument("--curated-output", type=Path, default=None)
    args = parser.parse_args()

    # --- Ask which steps to run ---
    print()
    run_norm  = _ask_yes_no("Would you like to run normalisation rules?    [y/N]: ")
    run_hier  = _ask_yes_no("Would you like to run hierarchy resolution?   [y/N]: ")
    run_attr  = _ask_yes_no("Would you like to run attribute resolution?   [y/N]: ")

    if not any([run_norm, run_hier, run_attr]):
        print("\nNothing selected. Exiting.")
        return

    # --- Step 1: Normalisation rules ---
    if run_norm:
        _section("[Step 1/3] Running normalisation rules...")
        _run_normalisation_rules(args)
        print("\n[Step 1/3] Done.")
    else:
        print("\n[Step 1/3] Skipping normalisation rules.")

    # --- Step 2: Hierarchy ---
    if run_hier:
        _section("[Step 2/3] Running hierarchy resolution...")
        _run_hierarchy()
        print("\n[Step 2/3] Done.")
    else:
        print("\n[Step 2/3] Skipping hierarchy resolution.")

    # --- Step 3: Attribute resolver ---
    if run_attr:
        _section("[Step 3/3] Running attribute resolution...")
        _run_attribute_resolver()
        print("\n[Step 3/3] Done.")
    else:
        print("\n[Step 3/3] Skipping attribute resolution.")

    print()


if __name__ == "__main__":
    main()
