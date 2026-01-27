"""Main entry point for the Data Quality Rules Derivation Pipeline."""

import argparse
import logging
import sys
from pathlib import Path

from src.pipeline import Pipeline
from src.utils.helpers import setup_logging


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Data Quality Rules Derivation for ABB Contactors and Relays",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full pipeline
  python main.py run --config config/config.yaml

  # Ingest PDFs only
  python main.py ingest --pdf-path data/input/pdfs/

  # Generate rules for specific attributes
  python main.py generate --attributes rated_current,rated_voltage

  # Export existing rules to Excel
  python main.py export --format excel --output data/output/rules.xlsx
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run the full pipeline")
    run_parser.add_argument(
        "--config",
        type=str,
        default="config/config.yaml",
        help="Path to configuration file",
    )
    run_parser.add_argument(
        "--output-format",
        type=str,
        choices=["json", "excel", "both"],
        default="both",
        help="Output format",
    )
    run_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )

    # Ingest command
    ingest_parser = subparsers.add_parser("ingest", help="Ingest PDFs into vector DB")
    ingest_parser.add_argument(
        "--pdf-path",
        type=str,
        required=True,
        help="Path to PDF file or directory",
    )
    ingest_parser.add_argument(
        "--config",
        type=str,
        default="config/config.yaml",
        help="Path to configuration file",
    )

    # Generate command
    gen_parser = subparsers.add_parser(
        "generate", help="Generate rules for specific attributes"
    )
    gen_parser.add_argument(
        "--attributes",
        type=str,
        required=True,
        help="Comma-separated list of attributes",
    )
    gen_parser.add_argument(
        "--config",
        type=str,
        default="config/config.yaml",
        help="Path to configuration file",
    )
    gen_parser.add_argument(
        "--output",
        type=str,
        help="Output file path",
    )

    # Export command
    export_parser = subparsers.add_parser("export", help="Export rules to file")
    export_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "excel"],
        required=True,
        help="Export format",
    )
    export_parser.add_argument(
        "--input",
        type=str,
        help="Input JSON file with rules",
    )
    export_parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output file path",
    )
    export_parser.add_argument(
        "--config",
        type=str,
        default="config/config.yaml",
        help="Path to configuration file",
    )

    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show pipeline statistics")
    stats_parser.add_argument(
        "--config",
        type=str,
        default="config/config.yaml",
        help="Path to configuration file",
    )

    # PDF-only command
    pdf_parser = subparsers.add_parser(
        "pdf-only",
        help="Generate rules from vectorized PDF data only (no cross-tab matching)"
    )
    pdf_parser.add_argument(
        "--config",
        type=str,
        default="config/config.yaml",
        help="Path to configuration file",
    )
    pdf_parser.add_argument(
        "--output-format",
        type=str,
        choices=["json", "excel", "both"],
        default="both",
        help="Output format",
    )
    pdf_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )

    # Profiling-based command
    profiling_parser = subparsers.add_parser(
        "profiling",
        help="Generate rules from Python Profiling data (with Cross-Tab, Wikipedia, and optional ABB specs)"
    )
    profiling_parser.add_argument(
        "--config",
        type=str,
        default="config/config.yaml",
        help="Path to configuration file",
    )
    profiling_parser.add_argument(
        "--output-format",
        type=str,
        choices=["json", "excel", "both"],
        default="both",
        help="Output format",
    )
    profiling_parser.add_argument(
        "--no-abb-specs",
        action="store_true",
        help="Skip ABB specification lookup",
    )
    profiling_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )

    # Cross-Tab based command (NEW - as per user request)
    crosstab_parser = subparsers.add_parser(
        "crosstab",
        help="Generate rules for Cross-Tab attributes using Profiling, Wikipedia, and ABB specs"
    )
    crosstab_parser.add_argument(
        "--config",
        type=str,
        default="config/config.yaml",
        help="Path to configuration file",
    )
    crosstab_parser.add_argument(
        "--output-format",
        type=str,
        choices=["json", "excel", "both"],
        default="both",
        help="Output format",
    )
    crosstab_parser.add_argument(
        "--legacy",
        action="store_true",
        help="Use legacy GPT-4o generation instead of deterministic shape constraints",
    )
    crosstab_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Setup logging
    log_level = logging.DEBUG if getattr(args, "verbose", False) else logging.INFO
    setup_logging(default_level=log_level)
    logger = logging.getLogger(__name__)

    try:
        if args.command == "run":
            logger.info("Starting full pipeline run...")
            pipeline = Pipeline(args.config)
            results = pipeline.run(output_format=args.output_format)

            print("\n" + "=" * 60)
            print("PIPELINE COMPLETED")
            print("=" * 60)

            if results["rule_set"]:
                print(f"Total rules generated: {len(results['rule_set'].rules)}")

            print(f"Output files:")
            for f in results["output_files"]:
                print(f"  - {f}")

        elif args.command == "ingest":
            logger.info(f"Ingesting PDFs from {args.pdf_path}...")
            pipeline = Pipeline(args.config)

            pdf_path = Path(args.pdf_path)
            if pdf_path.is_file():
                # Single file
                document = pipeline.pdf_processor.process(pdf_path)
                chunks = pipeline.chunker.chunk_document(document)
                chunks = pipeline.chunk_enricher.enrich_chunks(chunks)
                chunks = pipeline.batch_processor.process_chunks(chunks)
                counts = pipeline.collection_manager.add_chunks_by_category(chunks)
                total = sum(counts.values())
                print(f"Indexed {total} chunks from {pdf_path.name}")
            else:
                # Directory
                total = pipeline.ingest_pdfs(pdf_path)
                print(f"Total chunks indexed: {total}")

        elif args.command == "generate":
            attributes = [a.strip() for a in args.attributes.split(",")]
            logger.info(f"Generating rules for: {attributes}")

            pipeline = Pipeline(args.config)
            rule_set = pipeline.generate_for_attributes(attributes)

            print(f"Generated {len(rule_set.rules)} rules")

            if args.output:
                output_path = Path(args.output)
                if output_path.suffix == ".xlsx":
                    pipeline.excel_exporter.export(rule_set, output_path=output_path)
                else:
                    pipeline.json_exporter.export(rule_set, output_path=output_path)
                print(f"Exported to: {output_path}")

        elif args.command == "export":
            logger.info(f"Exporting to {args.format}...")
            pipeline = Pipeline(args.config)

            if args.input:
                rule_set = pipeline.json_exporter.load(args.input)
            else:
                # Run pipeline to generate rules
                results = pipeline.run(output_format="json")
                rule_set = results["rule_set"]

            if args.format == "excel":
                pipeline.excel_exporter.export(rule_set, output_path=args.output)
            else:
                pipeline.json_exporter.export(rule_set, output_path=args.output)

            print(f"Exported to: {args.output}")

        elif args.command == "stats":
            pipeline = Pipeline(args.config)
            stats = pipeline.get_statistics()

            print("\n" + "=" * 60)
            print("PIPELINE STATISTICS")
            print("=" * 60)

            print("\nVector Database:")
            for key, value in stats["vectordb"].items():
                print(f"  {key}: {value}")

            print(f"\nCollections: {stats['collections']}")

        elif args.command == "pdf-only":
            logger.info("Generating rules from PDF data only...")
            pipeline = Pipeline(args.config)
            results = pipeline.run_from_pdf_only(output_format=args.output_format)

            print("\n" + "=" * 60)
            print("PDF-ONLY PIPELINE COMPLETED")
            print("=" * 60)

            print(f"\nExtracted attributes from PDFs:")
            for attr in results["extracted_attributes"]:
                print(f"  - {attr}")

            if results["rule_set"]:
                print(f"\nTotal rules generated: {len(results['rule_set'].rules)}")

                # Show rules by category
                rule_set = results["rule_set"]
                if rule_set.summary.by_category:
                    print("\nRules by category:")
                    for cat, count in rule_set.summary.by_category.items():
                        print(f"  {cat}: {count}")

                # Show rules by attribute
                if rule_set.summary.by_attribute:
                    print("\nRules by attribute:")
                    for attr, count in rule_set.summary.by_attribute.items():
                        print(f"  {attr}: {count}")

            print(f"\nOutput files:")
            for f in results["output_files"]:
                print(f"  - {f}")

        elif args.command == "profiling":
            logger.info("Generating rules from Python Profiling data...")
            pipeline = Pipeline(args.config)

            include_abb = not getattr(args, "no_abb_specs", False)
            results = pipeline.run_from_profiling(
                output_format=args.output_format,
                include_abb_specs=include_abb,
            )

            print("\n" + "=" * 60)
            print("PROFILING-BASED PIPELINE COMPLETED")
            print("=" * 60)

            print(f"\nTotal attributes in profiling data: {len(results['profiling_attributes'])}")

            if results["rule_set"]:
                print(f"\nTotal rules generated: {len(results['rule_set'].rules)}")

                # Show rules by category
                rule_set = results["rule_set"]
                if rule_set.summary.by_category:
                    print("\nRules by category:")
                    for cat, count in rule_set.summary.by_category.items():
                        print(f"  {cat}: {count}")

                # Show rules by attribute (limit to 20)
                if rule_set.summary.by_attribute:
                    print("\nRules by attribute (showing up to 20):")
                    for i, (attr, count) in enumerate(rule_set.summary.by_attribute.items()):
                        if i >= 20:
                            remaining = len(rule_set.summary.by_attribute) - 20
                            print(f"  ... and {remaining} more attributes")
                            break
                        print(f"  {attr}: {count}")

            print(f"\nOutput files:")
            for f in results["output_files"]:
                print(f"  - {f}")

        elif args.command == "crosstab":
            use_shape_constraints = not getattr(args, "legacy", False)
            mode_str = "Shape Constraints (Deterministic)" if use_shape_constraints else "GPT-4o (Legacy)"
            logger.info(f"Generating rules for Cross-Tab attributes using {mode_str}...")

            pipeline = Pipeline(args.config)

            results = pipeline.run_from_crosstab(
                output_format=args.output_format,
                use_shape_constraints=use_shape_constraints,
            )

            print("\n" + "=" * 60)
            print("CROSS-TAB BASED PIPELINE COMPLETED")
            print(f"Mode: {mode_str}")
            print("=" * 60)

            print(f"\nCross-Tab attributes: {len(results['crosstab_attributes'])}")
            print(f"Attributes with profiling data: {len(results['attributes_with_profiling'])}")
            print(f"Attributes with ABB specs: {len(results['attributes_with_abb_specs'])}")

            # Display derivation summary for shape constraints mode
            if use_shape_constraints and results.get("rule_derivation_summary"):
                summary = results["rule_derivation_summary"]
                print("\n" + "-" * 40)
                print("RULE DERIVATION SUMMARY")
                print("-" * 40)

                print("\nCOMPLETENESS Rules (Descriptive - based on profiling):")
                comp_rules = summary.get("completeness_rules", {})
                print(f"  Mandatory (<5% missing):    {comp_rules.get('mandatory', 0)}")
                print(f"  Expected (5-20% missing):   {comp_rules.get('expected', 0)}")
                print(f"  Conditional (20-70% miss):  {comp_rules.get('conditional', 0)}")
                print(f"  Optional/Skipped (>70%):    {comp_rules.get('optional_skipped', 0)}")
                print(f"  Dead Fields (100%):         {comp_rules.get('dead_field', 0)}")

                print("\nVALIDITY Rules (Prescriptive - based on standards):")
                val_rules = summary.get("validity_rules", {})
                print(f"  Enumeration:     {val_rules.get('enumeration', 0)}")
                print(f"  Range Check:     {val_rules.get('range_check', 0)}")
                print(f"  Format Pattern:  {val_rules.get('format_pattern', 0)}")
                print(f"  Data Type:       {val_rules.get('data_type', 0)}")

                # Show attribute categorization
                attrs_by_cat = summary.get("attributes_by_category", {})
                if attrs_by_cat:
                    print("\nAttribute Categorization:")
                    for category in ["mandatory", "expected", "conditional", "optional", "dead_field"]:
                        attrs = attrs_by_cat.get(category, [])
                        if attrs:
                            print(f"\n  {category.upper()} ({len(attrs)}):")
                            for attr in attrs[:3]:
                                print(f"    - {attr}")
                            if len(attrs) > 3:
                                print(f"    ... and {len(attrs) - 3} more")

            if results["rule_set"]:
                print(f"\nTotal rules generated: {len(results['rule_set'].rules)}")

                rule_set = results["rule_set"]
                if rule_set.summary.by_category:
                    print("\nRules by category:")
                    for cat, count in rule_set.summary.by_category.items():
                        print(f"  {cat}: {count}")

                if rule_set.summary.by_attribute:
                    print("\nRules by attribute (showing up to 20):")
                    for i, (attr, count) in enumerate(rule_set.summary.by_attribute.items()):
                        if i >= 20:
                            remaining = len(rule_set.summary.by_attribute) - 20
                            print(f"  ... and {remaining} more attributes")
                            break
                        print(f"  {attr}: {count}")

            print(f"\nOutput files:")
            for f in results["output_files"]:
                print(f"  - {f}")

    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        if getattr(args, "verbose", False):
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
