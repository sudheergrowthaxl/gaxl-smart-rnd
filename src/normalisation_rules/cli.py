"""CLI entrypoint for the full pipeline.

New workflow: load dataset -> auto-detect category -> strip prefixes ->
auto-run attribute resolution -> user chooses normalisation/hierarchy.
"""

import argparse
import json
from pathlib import Path

from normalisation_rules.config import (
    DEFAULT_FEW_SHOT_PATH,
    OUTPUT_RULES_FILE,
    DATA_DIR,
    get_tavily_log_path_for_run,
    get_curated_values_path_for_run,
    get_manufacturers_for_category,
    ensure_api_keys,
    HIERARCHY_OUTPUT_CSV,
    HIERARCHY_CRAWLED_PATHS_JSON,
    HIERARCHY_RECOMMENDED_JSON,
    ATTRIBUTE_RESOLVER_OUTPUT_JSON,
    ATTRIBUTE_RESOLVER_OUTPUT_CSV,
    PROJECT_ROOT,
)
from normalisation_rules.data_loader import (
    load_profiling_json,
    extract_attributes_for_rules,
    load_dataset_as_dataframe,
    profile_and_save,
    find_latest_profiling,
)
from normalisation_rules.export import write_rules_to_excel, write_rules_to_text
from normalisation_rules.graph import run_for_attribute
from normalisation_rules.curate_values import save_curated_values
from normalisation_rules.models import get_llm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ask_yes_no(prompt: str) -> bool:
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
# Category detection
# ---------------------------------------------------------------------------

def _detect_category(args: argparse.Namespace) -> str:
    """Auto-detect or use the CLI-provided category."""
    if args.category:
        print(f"  Category (from CLI): {args.category}")
        return args.category

    if args.dataset and Path(args.dataset).exists():
        import pandas as pd
        from normalisation_rules.category_detector import detect_category

        ext = Path(args.dataset).suffix.lower()
        if ext == ".csv":
            df = pd.read_csv(args.dataset)
        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(args.dataset)
        elif ext == ".json":
            df = pd.read_json(args.dataset)
        else:
            df = pd.read_excel(args.dataset)

        result = detect_category(df, Path(args.dataset).name)
        category = result.get("category", "Unknown")
        confidence = result.get("confidence", 0)
        reasoning = result.get("reasoning", "")
        print(f"  Auto-detected category: {category} (confidence: {confidence:.2f})")
        if reasoning:
            print(f"  Reasoning: {reasoning[:200]}...")

        override = input(f"  Use '{category}' or type a different category [Enter to accept]: ").strip()
        if override:
            category = override
            print(f"  Category overridden to: {category}")
        return category

    category = input("  Enter product category: ").strip()
    return category or "Unknown"


# ---------------------------------------------------------------------------
# Step runners
# ---------------------------------------------------------------------------

def _run_normalisation_rules(args: argparse.Namespace, category: str, profiling_path: Path | None = None) -> None:
    """Run the normalisation rules pipeline for the detected category.

    If *profiling_path* is provided, loads profiling from that file.
    Otherwise tries --profiling arg, then falls back to latest profiling
    in the data/ folder, then profiles the raw dataset on the fly.
    """
    use_tavily = not args.no_tavily
    manufacturers = get_manufacturers_for_category(category)

    missing = ensure_api_keys(
        use_openai=(args.provider == "openai"),
        use_groq=(args.provider == "groq"),
        use_tavily=use_tavily,
    )
    if missing:
        print("  Missing API keys:", ", ".join(missing))
        return

    few_shot_text = args.few_shot.read_text(encoding="utf-8") if args.few_shot.exists() else ""

    # Resolve profiling data: explicit path > --profiling flag > latest in data/ > profile from raw
    resolved_profiling_path = profiling_path or args.profiling
    if resolved_profiling_path and Path(resolved_profiling_path).exists():
        print(f"  Loading profiling from: {resolved_profiling_path}")
        profiling = load_profiling_json(resolved_profiling_path)
        attributes = extract_attributes_for_rules(profiling)
    else:
        latest = find_latest_profiling(Path(args.dataset).name if args.dataset else None)
        if latest:
            print(f"  Loading latest profiling from: {latest}")
            profiling = load_profiling_json(latest)
            attributes = extract_attributes_for_rules(profiling)
        elif args.dataset and Path(args.dataset).exists():
            from normalisation_rules.data_loader import load_generic_dataset
            print(f"  No profiling found; profiling raw dataset: {args.dataset}")
            profiling = load_generic_dataset(args.dataset)
            attributes = extract_attributes_for_rules(profiling)
        else:
            print("  No profiling data or dataset provided.")
            return

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

    all_rules: list[tuple[str, str]] = []
    all_curated: list[dict] = []
    reference = f"Profiling; Category: {category}"
    if use_tavily:
        reference += "; Standards (Tavily); Manufacturer catalogs (Tavily)"

    for i, attr in enumerate(attributes):
        name = attr.get("name", "?")
        print(f"\n  [{i + 1}/{len(attributes)}] Processing: {name}")
        try:
            rules, curated_dict = run_for_attribute(
                llm=llm,
                attribute=attr,
                few_shot_examples=few_shot_text,
                category=category,
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


def _run_hierarchy(category: str) -> None:
    """Run the hierarchy resolution pipeline for the detected category."""
    import pandas as pd
    from normalisation_rules.hierarchy.resolver import standardize_hierarchy

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


def _run_attribute_resolver(
    category: str,
    dataset_path: str | None = None,
    profiling_data: dict | None = None,
) -> None:
    """Run the attribute resolution pipeline for the detected category."""
    from normalisation_rules.attribute_resolver.resolver import standardize_attributes

    result, rows, run_log = standardize_attributes(
        category=category,
        dataset_path=dataset_path,
        profiling_data=profiling_data,
        output_dir=str(PROJECT_ROOT),
        output_json_path=str(ATTRIBUTE_RESOLVER_OUTPUT_JSON),
        output_csv_path=str(ATTRIBUTE_RESOLVER_OUTPUT_CSV),
    )

    backbone = result.get("backbone", [])
    lenses = result.get("lenses", {})
    reasoning_preview = (result.get("reasoning") or "")[:200]
    if reasoning_preview:
        print(f"  Reasoning  : {reasoning_preview}...")
    print(f"  Backbone attributes    : {len(backbone)}")
    print(f"  Supply chain view      : {len(lenses.get('supply_chain', []))} attributes")
    print(f"  Ecommerce view         : {len(lenses.get('ecommerce', []))} attributes")
    print(f"  Analytical view        : {len(lenses.get('analytical', []))} attributes")
    print(f"  Saved attributes JSON  : {ATTRIBUTE_RESOLVER_OUTPUT_JSON}")
    print(f"  Saved attributes CSV   : {ATTRIBUTE_RESOLVER_OUTPUT_CSV}")
    print(f"  Full run log           : {run_log}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Schema Builder pipeline: detect category -> attribute resolution -> "
                    "normalisation rules / hierarchy resolution."
    )
    parser.add_argument("--dataset", type=str, default=None,
                        help="Path to user's product data file (Excel, CSV, JSON)")
    parser.add_argument("--category", type=str, default=None,
                        help="Product category (auto-detected if not provided)")
    parser.add_argument("--profiling", type=Path, default=None,
                        help="Path to profiling JSON (legacy format)")
    parser.add_argument("--few-shot", type=Path, default=DEFAULT_FEW_SHOT_PATH)
    parser.add_argument("--output", "-o", type=Path, default=OUTPUT_RULES_FILE)
    parser.add_argument("--provider", choices=["openai", "groq"], default="openai")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-tavily", action="store_true")
    parser.add_argument("--search-depth", choices=["basic", "advanced"], default="basic")
    parser.add_argument("--curated-output", type=Path, default=None)
    args = parser.parse_args()

    # Step 0: Detect category
    _section("[Step 0] Category Detection")
    category = _detect_category(args)
    if category == "Unknown":
        print("  Could not determine category. Exiting.")
        return

    # Step 0.5: Profiling — profile dataset and save to data/ folder
    profiling_data = None
    profiling_path_saved: Path | None = None

    if args.dataset and Path(args.dataset).exists():
        _section("[Step 0.5] Dataset Profiling")
        df = load_dataset_as_dataframe(args.dataset)

        # Prefix stripping before profiling
        from normalisation_rules.prefix_stripper import strip_column_prefixes
        print("  Stripping column prefixes...")
        cleaned_df, mapping = strip_column_prefixes(df, category)
        changed = {k: v for k, v in mapping.items() if k != v}
        if changed:
            print(f"  Cleaned {len(changed)} column names:")
            for orig, clean in list(changed.items())[:5]:
                print(f"    {orig} -> {clean}")
            if len(changed) > 5:
                print(f"    ... and {len(changed) - 5} more")

        print("  Running profiling...")
        profiling_data, profiling_path_saved = profile_and_save(
            cleaned_df, Path(args.dataset).name, category,
        )
        print(f"  Profiling saved: {profiling_path_saved}")
        print(f"  Profiled {len(profiling_data)} columns")
    elif args.profiling and args.profiling.exists():
        _section("[Step 0.5] Loading Existing Profiling")
        profiling_data = load_profiling_json(args.profiling)
        profiling_path_saved = args.profiling
        print(f"  Loaded profiling from: {args.profiling} ({len(profiling_data)} columns)")
    else:
        latest = find_latest_profiling()
        if latest:
            _section("[Step 0.5] Loading Latest Profiling from data/")
            profiling_data = load_profiling_json(latest)
            profiling_path_saved = latest
            print(f"  Loaded: {latest} ({len(profiling_data)} columns)")
        else:
            print("\n  [Warning] No dataset or profiling provided. Pipelines will run without user data context.")

    # Step 1: Attribute resolution (always runs first, uses profiling)
    _section(f"[Step 1/3] Attribute Resolution for '{category}'")
    _run_attribute_resolver(category, dataset_path=args.dataset, profiling_data=profiling_data)
    print("\n[Step 1/3] Done.")

    # Step 2: Ask which additional steps to run
    run_norm = _ask_yes_no("\nWould you like to run normalisation rules?    [y/N]: ")
    run_hier = _ask_yes_no("Would you like to run hierarchy resolution?   [y/N]: ")

    if run_norm:
        _section(f"[Step 2/3] Normalisation Rules for '{category}'")
        _run_normalisation_rules(args, category, profiling_path=profiling_path_saved)
        print("\n[Step 2/3] Done.")
    else:
        print("\n[Step 2/3] Skipping normalisation rules.")

    if run_hier:
        _section(f"[Step 3/3] Hierarchy Resolution for '{category}'")
        _run_hierarchy(category)
        print("\n[Step 3/3] Done.")
    else:
        print("\n[Step 3/3] Skipping hierarchy resolution.")

    print()


if __name__ == "__main__":
    main()
