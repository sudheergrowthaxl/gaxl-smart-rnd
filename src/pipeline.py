"""Main pipeline orchestrator for data quality rules derivation."""

import logging
from pathlib import Path
from typing import Any

import yaml

from src.ingestion import PDFProcessor
from src.chunking import SemanticChunker, ChunkEnricher
from src.embedding import Embedder, BatchProcessor
from src.vectordb import ChromaClient, CollectionManager
from src.retrieval import Retriever
from src.data_sources import CrosstabLoader, ProfilingLoader, WikipediaScraper
from src.matching import AttributeMatcher
from src.rules import RuleGenerator, RuleSet, ShapeConstraintEngine
from src.exporters import JSONExporter, ExcelExporter
from src.utils.helpers import load_config, setup_logging, get_logger

logger = get_logger(__name__)


class Pipeline:
    """
    Main pipeline orchestrator that coordinates all stages of
    data quality rules derivation.
    """

    def __init__(self, config_path: str | Path = "config/config.yaml"):
        """
        Initialize the pipeline.

        Args:
            config_path: Path to configuration file.
        """
        self.config = load_config(config_path)
        setup_logging()

        logger.info("Initializing Data Quality Rules Pipeline")

        # Load shape constraints configuration
        self.shape_constraints_config = self._load_shape_constraints_config()

        # Initialize components
        self.pdf_processor = PDFProcessor(self.config)
        self.chunker = SemanticChunker(self.config)
        self.chunk_enricher = ChunkEnricher(self.config)
        self.embedder = Embedder(self.config)
        self.batch_processor = BatchProcessor(self.embedder)

        self.chroma_client = ChromaClient(self.config)
        self.collection_manager = CollectionManager(self.chroma_client)
        self.collection_manager.initialize_collections()

        self.retriever = Retriever(
            self.embedder, self.collection_manager, self.config
        )

        self.crosstab_loader = CrosstabLoader(self.config)
        self.profiling_loader = ProfilingLoader(self.config)
        self.wikipedia_scraper = WikipediaScraper(self.config)

        self.attribute_matcher = AttributeMatcher(self.config)
        self.rule_generator = RuleGenerator(self.config)

        # Initialize Shape Constraint Engine for deterministic rule derivation
        self.shape_engine = ShapeConstraintEngine(
            config=self.shape_constraints_config,
            wikipedia_scraper=self.wikipedia_scraper,
        )

        self.json_exporter = JSONExporter(self.config)
        self.excel_exporter = ExcelExporter(self.config)

    def _load_shape_constraints_config(self) -> dict[str, Any]:
        """
        Load shape constraints configuration from YAML file.

        Returns:
            Dictionary containing shape constraints configuration.
        """
        config_path = Path("config/shape_constraints.yaml")

        if not config_path.exists():
            logger.warning(
                f"Shape constraints config not found at {config_path}. "
                "Using default thresholds."
            )
            return {
                "shape_constraints": {
                    "completeness": {
                        "mandatory_threshold": 5.0,
                        "expected_threshold": 20.0,
                        "conditional_threshold": 70.0,
                        "optional_above": 70.0,
                        "dead_field_threshold": 100.0,
                    },
                    "validity": {
                        "scrape_wikipedia": True,
                        "fallback_to_profiling": True,
                    },
                    "severity": {
                        "mandatory": "ERROR",
                        "expected": "WARNING",
                        "conditional": "INFO",
                        "validity_violation": "ERROR",
                    },
                }
            }

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            logger.info(f"Loaded shape constraints from {config_path}")
            return config
        except Exception as e:
            logger.error(f"Failed to load shape constraints config: {e}")
            return {}

    def ingest_pdfs(self, pdf_dir: str | Path | None = None) -> int:
        """
        Ingest PDFs into the vector database.

        Args:
            pdf_dir: Directory containing PDF files.

        Returns:
            Number of chunks indexed.
        """
        if pdf_dir is None:
            pdf_dir = self.config.get("data", {}).get("input", {}).get(
                "pdfs", "./data/input/pdfs"
            )

        pdf_dir = Path(pdf_dir)
        logger.info(f"Ingesting PDFs from {pdf_dir}")

        if not pdf_dir.exists():
            logger.warning(f"PDF directory not found: {pdf_dir}")
            return 0

        total_chunks = 0

        for pdf_path in pdf_dir.glob("*.pdf"):
            try:
                # Process PDF
                document = self.pdf_processor.process(pdf_path)

                # Chunk document
                chunks = self.chunker.chunk_document(document)

                # Enrich chunks
                chunks = self.chunk_enricher.enrich_chunks(chunks)

                # Generate embeddings
                chunks = self.batch_processor.process_chunks(chunks)

                # Add to vector database
                counts = self.collection_manager.add_chunks_by_category(chunks)
                chunk_count = sum(counts.values())
                total_chunks += chunk_count

                logger.info(f"Indexed {chunk_count} chunks from {pdf_path.name}")

            except Exception as e:
                logger.error(f"Failed to process {pdf_path}: {e}")
                continue

        logger.info(f"Total chunks indexed: {total_chunks}")
        return total_chunks

    def run(
        self,
        attributes: list[str] | None = None,
        output_format: str = "both",
    ) -> dict[str, Any]:
        """
        Run the full pipeline.

        Args:
            attributes: Optional list of specific attributes to process.
            output_format: Output format - "json", "excel", or "both".

        Returns:
            Dictionary with pipeline results.
        """
        logger.info("Starting full pipeline run")

        results = {
            "matching_report": None,
            "rule_set": None,
            "output_files": [],
        }

        # 1. Load data sources
        logger.info("Loading data sources...")

        try:
            crosstab_df = self.crosstab_loader.load()
            crosstab_attributes = self.crosstab_loader.get_attributes(crosstab_df)
        except Exception as e:
            logger.warning(f"Failed to load cross-tab: {e}")
            crosstab_df = None
            crosstab_attributes = attributes or []

        profiling_data = self.profiling_loader.load()

        # 2. Get RAG specifications for attributes
        logger.info("Retrieving RAG specifications...")

        all_rag_chunks = []
        for attr in crosstab_attributes:
            chunks = self.retriever.retrieve_for_attribute(
                attr, synonyms=self.config.get("abb_mapping", {}).get(attr, [])
            )
            all_rag_chunks.extend(chunks)

        # 3. Extract RAG attributes
        rag_attributes = self.attribute_matcher.extract_attributes_from_chunks(
            all_rag_chunks
        )

        # 4. Match attributes
        logger.info("Matching attributes...")

        matching_result = self.attribute_matcher.match_attributes(
            crosstab_attributes, rag_attributes
        )
        results["matching_report"] = matching_result

        # Print matching report
        report = self.attribute_matcher.create_matching_report(matching_result)
        logger.info(f"\n{report}")

        # 5. Generate rules for matched attributes
        logger.info("Generating data quality rules...")

        # Get RAG terms (canonical ABB attribute names like rated_current, coil_voltage)
        matched_rag_terms = list(set(m["rag_term"] for m in matching_result["matched"]))
        # Also get cross-tab terms for reference
        matched_crosstab_terms = [m["canonical"] for m in matching_result["matched"]]

        if not matched_rag_terms:
            logger.warning("No matched attributes found. No rules will be generated.")
            return results

        logger.info(f"Matched RAG terms: {matched_rag_terms}")

        # Prepare data for prompt
        crosstab_formatted = self.crosstab_loader.format_for_prompt(crosstab_df)
        profiling_formatted = self.profiling_loader.format_for_prompt(
            profiling_data, matched_crosstab_terms
        )

        # 5a. Scrape Wikipedia definitions at runtime for MATCHED attributes only
        logger.info(f"Scraping Wikipedia definitions for {len(matched_rag_terms)} matched RAG terms...")
        wikipedia_formatted = self.wikipedia_scraper.scrape_for_matched_attributes(matched_rag_terms)

        rag_formatted = self.rule_generator.prompt_builder.format_rag_specs(
            all_rag_chunks
        )

        # Generate rules (pass RAG terms as the canonical attribute names)
        rule_set = self.rule_generator.generate_rules(
            crosstab_data=crosstab_formatted,
            profiling_stats=profiling_formatted,
            wikipedia_defs=wikipedia_formatted,
            rag_specs=rag_formatted,
            matched_attributes=matched_rag_terms,
        )

        results["rule_set"] = rule_set

        # 6. Export results
        logger.info("Exporting results...")

        if output_format in ["json", "both"]:
            json_path = self.json_exporter.export(rule_set)
            results["output_files"].append(str(json_path))

            # Also export matching report
            report_path = self.json_exporter.export_matching_report(matching_result)
            results["output_files"].append(str(report_path))

        if output_format in ["excel", "both"]:
            excel_path = self.excel_exporter.export(rule_set, matching_result)
            results["output_files"].append(str(excel_path))

        logger.info(f"Pipeline completed. Generated {len(rule_set.rules)} rules.")
        logger.info(f"Output files: {results['output_files']}")

        return results

    def generate_for_attributes(
        self, attributes: list[str]
    ) -> RuleSet:
        """
        Generate rules for specific attributes.

        Args:
            attributes: List of attribute names.

        Returns:
            RuleSet with generated rules.
        """
        logger.info(f"Generating rules for {len(attributes)} attributes")

        rule_set = RuleSet()

        for attr in attributes:
            # Get RAG specs
            chunks = self.retriever.retrieve_for_attribute(attr)
            rag_specs = self.rule_generator.prompt_builder.format_rag_specs(chunks)

            # Get profiling stats
            profiling_data = self.profiling_loader.load()
            profiling_formatted = self.profiling_loader.format_for_prompt(
                profiling_data, [attr]
            )

            # Get crosstab info
            try:
                crosstab_df = self.crosstab_loader.load()
                crosstab_info = self.crosstab_loader.format_for_prompt(crosstab_df)
            except Exception:
                crosstab_info = f"Attribute: {attr}"

            # Generate rules
            rules = self.rule_generator.generate_rules_for_attribute(
                attribute=attr,
                crosstab_info=crosstab_info,
                rag_specs=rag_specs,
                profiling_stats=profiling_formatted,
            )

            for rule in rules:
                rule_set.add_rule(rule)

        return rule_set

    def get_statistics(self) -> dict[str, Any]:
        """
        Get pipeline statistics.

        Returns:
            Dictionary with statistics.
        """
        return {
            "vectordb": self.collection_manager.get_statistics(),
            "collections": self.chroma_client.list_collections(),
        }

    def run_from_profiling(
        self,
        output_format: str = "both",
        include_abb_specs: bool = True,
    ) -> dict[str, Any]:
        """
        Generate data quality rules based on Python Profiling data.

        Uses:
        - Python Profiling statistics (primary source for attributes)
        - Cross-Tab data (for context)
        - Wikipedia definitions (for domain knowledge)
        - ABB specifications (optional, for technical validation)

        Args:
            output_format: Output format - "json", "excel", or "both".
            include_abb_specs: Whether to include ABB PDF specs for context.

        Returns:
            Dictionary with pipeline results.
        """
        logger.info("Starting Profiling-based pipeline run")

        results = {
            "profiling_attributes": [],
            "rule_set": None,
            "output_files": [],
        }

        # 1. Load profiling data and extract attributes
        logger.info("Loading Python Profiling data...")
        profiling_data = self.profiling_loader.load()

        if not profiling_data:
            logger.error("No profiling data found. Check data/input/profiling/ directory.")
            return results

        profiling_attributes = list(profiling_data.keys())
        results["profiling_attributes"] = profiling_attributes
        logger.info(f"Found {len(profiling_attributes)} attributes in profiling data")

        # 2. Load cross-tab data for context
        logger.info("Loading Cross-Tab data for context...")
        try:
            crosstab_df = self.crosstab_loader.load()
            crosstab_formatted = self.crosstab_loader.format_for_prompt(crosstab_df)
        except Exception as e:
            logger.warning(f"Failed to load cross-tab: {e}")
            crosstab_formatted = "Cross-Tab data not available."

        # 3. Format profiling statistics
        logger.info("Formatting profiling statistics...")
        profiling_formatted = self._format_profiling_for_rules(profiling_data)

        # 4. Scrape Wikipedia for profiling attributes
        logger.info(f"Scraping Wikipedia definitions for {len(profiling_attributes)} profiling attributes...")
        # Extract human-readable terms from profiling attributes
        wiki_terms = self._extract_wiki_terms_from_profiling(profiling_attributes)
        wikipedia_formatted = self.wikipedia_scraper.scrape_for_matched_attributes(wiki_terms)

        # 5. Optionally retrieve ABB specs for relevant attributes
        abb_specs_formatted = ""
        if include_abb_specs:
            logger.info("Retrieving relevant ABB specifications...")
            abb_specs_formatted = self._retrieve_abb_specs_for_profiling(profiling_attributes)

        # 6. Generate rules using profiling-focused prompt
        logger.info("Generating data quality rules from profiling data...")
        rule_set = self._generate_rules_from_profiling(
            profiling_data=profiling_data,
            profiling_formatted=profiling_formatted,
            crosstab_formatted=crosstab_formatted,
            wikipedia_formatted=wikipedia_formatted,
            abb_specs_formatted=abb_specs_formatted,
        )

        results["rule_set"] = rule_set

        # 7. Export results
        logger.info("Exporting results...")

        if output_format in ["json", "both"]:
            json_path = self.json_exporter.export(rule_set)
            results["output_files"].append(str(json_path))

        if output_format in ["excel", "both"]:
            matching_report = {
                "matched": [{"canonical": attr, "rag_term": attr, "match_type": "profiling", "confidence": 1.0}
                           for attr in profiling_attributes[:50]],  # Limit for display
                "crosstab_only": [],
                "rag_only": [],
                "statistics": {
                    "total_profiling": len(profiling_attributes),
                    "rules_generated": len(rule_set.rules),
                }
            }
            excel_path = self.excel_exporter.export(rule_set, matching_report)
            results["output_files"].append(str(excel_path))

        logger.info(f"Pipeline completed. Generated {len(rule_set.rules)} rules.")
        logger.info(f"Output files: {results['output_files']}")

        return results

    def _format_profiling_for_rules(self, profiling_data: dict) -> str:
        """
        Format profiling data with detailed statistics for rule generation.

        Args:
            profiling_data: Raw profiling statistics.

        Returns:
            Formatted string for prompt.
        """
        lines = ["=" * 60]
        lines.append("PYTHON PROFILING STATISTICS")
        lines.append("=" * 60)

        for attr, stats in profiling_data.items():
            if not isinstance(stats, dict):
                continue

            lines.append(f"\n### {attr}")
            lines.append(f"  Data Type: {stats.get('datatype', 'Unknown')}")

            # Range information
            range_val = stats.get('range')
            if range_val and isinstance(range_val, list) and len(range_val) == 2:
                if range_val[0] is not None and range_val[1] is not None:
                    lines.append(f"  Range: {range_val[0]} to {range_val[1]}")

            # Missing/Null percentage
            missing = stats.get('missing_percentage', 0)
            lines.append(f"  Missing %: {missing}%")

            # Cardinality
            cardinality = stats.get('cardinality', 'N/A')
            lines.append(f"  Cardinality: {cardinality}")

            # Top values
            top_values = stats.get('top_values', [])
            if top_values:
                lines.append(f"  Top Values:")
                for tv in top_values[:3]:
                    if isinstance(tv, dict):
                        lines.append(f"    - {tv.get('value', 'N/A')}: {tv.get('count', 0)} occurrences")

            # Sparsity
            sparsity = stats.get('sparsity', 'N/A')
            lines.append(f"  Sparsity: {sparsity}")

            # Imbalance
            imbalance = stats.get('imbalance', 'N/A')
            lines.append(f"  Imbalance: {imbalance}")

        return "\n".join(lines)

    def _extract_wiki_terms_from_profiling(self, attributes: list[str]) -> list[str]:
        """
        Extract Wikipedia-searchable terms from profiling attribute names.

        Args:
            attributes: List of profiling attribute names.

        Returns:
            List of terms to search on Wikipedia.
        """
        wiki_terms = set()

        # Electrical/contactor-related keywords to look for
        electrical_keywords = {
            "voltage", "current", "power", "frequency", "temperature",
            "contact", "coil", "relay", "contactor", "rating", "ip",
            "phase", "pole", "terminal", "mounting", "enclosure"
        }

        for attr in attributes:
            # Clean attribute name
            clean_attr = attr.lower()
            for prefix in ["zz_", "dr_", "xx_"]:
                if clean_attr.startswith(prefix):
                    clean_attr = clean_attr[len(prefix):]
                    break

            # Replace underscores and check for electrical terms
            clean_attr = clean_attr.replace("_", " ")

            # Check if it contains electrical keywords
            for keyword in electrical_keywords:
                if keyword in clean_attr:
                    wiki_terms.add(clean_attr)
                    wiki_terms.add(keyword)
                    break

        # Add common electrical terms for context
        wiki_terms.update([
            "contactor", "relay", "IEC 60947",
            "rated current", "rated voltage",
            "utilization category", "electrical durability"
        ])

        return list(wiki_terms)[:30]  # Limit to 30 terms

    def _retrieve_abb_specs_for_profiling(self, attributes: list[str]) -> str:
        """
        Retrieve relevant ABB specifications for profiling attributes.

        Args:
            attributes: List of profiling attribute names.

        Returns:
            Formatted ABB specifications string.
        """
        # Build queries from electrical-related attributes
        electrical_attrs = []
        for attr in attributes:
            clean = attr.lower()
            for prefix in ["zz_", "dr_", "xx_"]:
                if clean.startswith(prefix):
                    clean = clean[len(prefix):]
                    break

            # Check if electrical-related
            if any(kw in clean for kw in ["voltage", "current", "power", "rating",
                                          "contact", "coil", "frequency", "temperature"]):
                electrical_attrs.append(clean.replace("_", " "))

        if not electrical_attrs:
            return "No electrical attributes found for ABB specification lookup."

        # Retrieve specs for electrical attributes
        all_chunks = []
        for attr in electrical_attrs[:10]:  # Limit queries
            try:
                chunks = self.retriever.retrieve(
                    query=f"ABB {attr} specification",
                    n_results=5,
                    use_expansion=True,
                    use_reranking=False,
                )
                all_chunks.extend(chunks)
            except Exception as e:
                logger.debug(f"Failed to retrieve specs for '{attr}': {e}")

        # Deduplicate
        seen = set()
        unique_chunks = []
        for chunk in all_chunks:
            content_hash = hash(chunk.get("content", "")[:100])
            if content_hash not in seen:
                seen.add(content_hash)
                unique_chunks.append(chunk)

        if not unique_chunks:
            return "No ABB specifications found in vector database."

        # Format for prompt
        return self.rule_generator.prompt_builder.format_rag_specs(unique_chunks[:15])

    def run_from_crosstab(
        self,
        output_format: str = "both",
        use_shape_constraints: bool = True,
    ) -> dict[str, Any]:
        """
        Generate data quality rules for attributes in Cross-Tab.

        Uses a descriptive + industry-standard approach:
        - COMPLETENESS rules: Based on actual data patterns (profiling)
        - VALIDITY rules: Based on Wikipedia/industry standards

        Data Sources:
        - Cross-Tab attributes (PRIMARY - defines which attributes to generate rules for)
        - Python Profiling statistics (for COMPLETENESS rules - descriptive)
        - Wikipedia definitions (for VALIDITY rules - prescriptive)
        - ABB PDF specs (from vector DB, optional enrichment)

        Args:
            output_format: Output format - "json", "excel", or "both".
            use_shape_constraints: If True, use deterministic shape constraints.
                                  If False, use GPT-4o generation (legacy).

        Returns:
            Dictionary with pipeline results.
        """
        logger.info("Starting Cross-Tab based pipeline run")
        logger.info(f"Mode: {'Shape Constraints (Deterministic)' if use_shape_constraints else 'GPT-4o (Legacy)'}")

        results = {
            "crosstab_attributes": [],
            "attributes_with_profiling": [],
            "attributes_with_abb_specs": [],
            "rule_derivation_summary": {},
            "rule_set": None,
            "output_files": [],
        }

        # 1. Load Cross-Tab and extract attributes
        logger.info("Loading Cross-Tab data...")
        try:
            crosstab_df = self.crosstab_loader.load()
            crosstab_attributes = self.crosstab_loader.get_attributes(crosstab_df)
            crosstab_formatted = self.crosstab_loader.format_for_prompt(crosstab_df)
        except Exception as e:
            logger.error(f"Failed to load cross-tab: {e}")
            return results

        results["crosstab_attributes"] = crosstab_attributes
        logger.info(f"Found {len(crosstab_attributes)} attributes in Cross-Tab")

        # 2. Load Profiling data and match with cross-tab attributes
        logger.info("Loading Python Profiling data...")
        profiling_data = self.profiling_loader.load()

        # Find profiling stats for cross-tab attributes
        profiling_for_crosstab = {}
        for attr in crosstab_attributes:
            # Try direct match
            stats = self.profiling_loader.get_attribute_stats(attr, profiling_data)
            if stats:
                profiling_for_crosstab[attr] = stats
                continue

            # Try without prefix
            clean_attr = attr
            for prefix in ["zz_", "dr_", "xx_"]:
                if attr.lower().startswith(prefix):
                    clean_attr = attr[len(prefix):]
                    break

            stats = self.profiling_loader.get_attribute_stats(clean_attr, profiling_data)
            if stats:
                profiling_for_crosstab[attr] = stats

        results["attributes_with_profiling"] = list(profiling_for_crosstab.keys())
        logger.info(f"Found profiling data for {len(profiling_for_crosstab)} cross-tab attributes")

        # 3. Format profiling statistics for matched attributes
        profiling_formatted = self._format_crosstab_profiling(crosstab_attributes, profiling_for_crosstab)

        # 4. Scrape Wikipedia at RUNTIME for cross-tab attributes
        logger.info(f"Scraping Wikipedia definitions for {len(crosstab_attributes)} cross-tab attributes...")
        # Extract human-readable terms from cross-tab attributes
        wiki_terms = []
        for attr in crosstab_attributes:
            clean = attr
            for prefix in ["zz_", "dr_", "xx_"]:
                if attr.lower().startswith(prefix):
                    clean = attr[len(prefix):]
                    break
            wiki_terms.append(clean.replace("_", " "))

        wikipedia_formatted = self.wikipedia_scraper.scrape_for_matched_attributes(wiki_terms[:30])

        # 5. Retrieve ABB specs from vector DB (if available)
        logger.info("Checking vector DB for ABB specifications...")
        abb_specs_formatted, attrs_with_specs = self._retrieve_abb_specs_for_crosstab(crosstab_attributes)
        results["attributes_with_abb_specs"] = attrs_with_specs

        if attrs_with_specs:
            logger.info(f"Found ABB specs for {len(attrs_with_specs)} attributes")
        else:
            logger.info("No ABB specs found in vector DB - proceeding without")

        # 6. Generate rules using shape constraints (deterministic) or GPT-4o (legacy)
        if use_shape_constraints:
            logger.info("Generating rules using Shape Constraint Engine (deterministic)...")
            rule_set, derivation_summary = self._generate_rules_with_shape_constraints(
                crosstab_attributes=crosstab_attributes,
                profiling_for_crosstab=profiling_for_crosstab,
            )
            results["rule_derivation_summary"] = derivation_summary
        else:
            logger.info("Generating rules using GPT-4o (legacy mode)...")
            rule_set = self._generate_rules_from_crosstab_legacy(
                crosstab_attributes=crosstab_attributes,
                crosstab_formatted=crosstab_formatted,
                profiling_for_crosstab=profiling_for_crosstab,
                profiling_formatted=profiling_formatted,
                wikipedia_formatted=wikipedia_formatted,
                abb_specs_formatted=abb_specs_formatted,
            )

        results["rule_set"] = rule_set

        # 7. Export results
        logger.info("Exporting results...")

        if output_format in ["json", "both"]:
            json_path = self.json_exporter.export(rule_set)
            results["output_files"].append(str(json_path))

        if output_format in ["excel", "both"]:
            matching_report = {
                "matched": [
                    {
                        "canonical": attr,
                        "rag_term": attr,
                        "match_type": "crosstab",
                        "confidence": 1.0,
                        "has_profiling": attr in profiling_for_crosstab,
                        "has_abb_spec": attr in attrs_with_specs,
                    }
                    for attr in crosstab_attributes[:50]
                ],
                "crosstab_only": [],
                "rag_only": [],
                "statistics": {
                    "total_crosstab": len(crosstab_attributes),
                    "with_profiling": len(profiling_for_crosstab),
                    "with_abb_specs": len(attrs_with_specs),
                    "rules_generated": len(rule_set.rules),
                },
                "derivation_summary": results.get("rule_derivation_summary", {}),
            }
            excel_path = self.excel_exporter.export(rule_set, matching_report)
            results["output_files"].append(str(excel_path))

        logger.info(f"Pipeline completed. Generated {len(rule_set.rules)} rules.")
        logger.info(f"Output files: {results['output_files']}")

        return results

    def _generate_rules_with_shape_constraints(
        self,
        crosstab_attributes: list[str],
        profiling_for_crosstab: dict[str, Any],
    ) -> tuple[RuleSet, dict[str, Any]]:
        """
        Generate rules using the Shape Constraint Engine (deterministic approach).

        COMPLETENESS: Descriptive - based on actual data patterns
        - < 5% missing → Mandatory (ERROR)
        - 5-20% missing → Expected (WARNING)
        - 20-70% missing → Conditional (INFO)
        - > 70% missing → NO completeness rule (optional)

        VALIDITY: Prescriptive - based on industry standards
        - Uses Wikipedia for standard values/ranges
        - Falls back to profiling statistics

        Args:
            crosstab_attributes: List of attributes from Cross-Tab.
            profiling_for_crosstab: Profiling statistics for each attribute.

        Returns:
            Tuple of (RuleSet, derivation_summary dict).
        """
        from src.rules.rule_models import RuleSet

        rule_set = RuleSet()
        self.shape_engine.reset_rule_counter()

        # Track derivation statistics
        derivation_summary = {
            "total_attributes": len(crosstab_attributes),
            "attributes_with_profiling": len(profiling_for_crosstab),
            "completeness_rules": {
                "mandatory": 0,
                "expected": 0,
                "conditional": 0,
                "optional_skipped": 0,
                "dead_field": 0,
            },
            "validity_rules": {
                "enumeration": 0,
                "range_check": 0,
                "format_pattern": 0,
                "data_type": 0,
            },
            "attributes_by_category": {
                "mandatory": [],
                "expected": [],
                "conditional": [],
                "optional": [],
                "dead_field": [],
            },
        }

        logger.info("=" * 60)
        logger.info("SHAPE CONSTRAINT RULE DERIVATION")
        logger.info("=" * 60)

        for attr in crosstab_attributes:
            stats = profiling_for_crosstab.get(attr, {})
            missing_pct = stats.get("missing_percentage", 0) if isinstance(stats, dict) else 0

            # Handle string percentages
            if isinstance(missing_pct, str):
                try:
                    missing_pct = float(missing_pct.replace("%", "").strip())
                except ValueError:
                    missing_pct = 0

            # Categorize attribute
            if missing_pct >= 100:
                derivation_summary["attributes_by_category"]["dead_field"].append(attr)
            elif missing_pct > 70:
                derivation_summary["attributes_by_category"]["optional"].append(attr)
            elif missing_pct > 20:
                derivation_summary["attributes_by_category"]["conditional"].append(attr)
            elif missing_pct > 5:
                derivation_summary["attributes_by_category"]["expected"].append(attr)
            else:
                derivation_summary["attributes_by_category"]["mandatory"].append(attr)

            # Derive COMPLETENESS rule (descriptive)
            completeness_rule = self.shape_engine.derive_completeness_rule(attr, stats)

            if completeness_rule:
                rule_set.add_rule(completeness_rule)

                # Track rule type
                subtype = completeness_rule.subtype
                if subtype == "mandatory_field":
                    derivation_summary["completeness_rules"]["mandatory"] += 1
                elif subtype == "threshold":
                    if missing_pct >= 100:
                        derivation_summary["completeness_rules"]["dead_field"] += 1
                    else:
                        derivation_summary["completeness_rules"]["expected"] += 1
                elif subtype == "conditional_mandatory":
                    derivation_summary["completeness_rules"]["conditional"] += 1
            else:
                # No rule = optional field
                derivation_summary["completeness_rules"]["optional_skipped"] += 1

            # Derive VALIDITY rules (prescriptive from standards)
            validity_rules = self.shape_engine.derive_validity_rules(attr, stats)

            for rule in validity_rules:
                rule_set.add_rule(rule)

                # Track rule type
                subtype = rule.subtype
                if subtype == "enumeration":
                    derivation_summary["validity_rules"]["enumeration"] += 1
                elif subtype == "range_check":
                    derivation_summary["validity_rules"]["range_check"] += 1
                elif subtype == "format_pattern":
                    derivation_summary["validity_rules"]["format_pattern"] += 1
                elif subtype == "data_type":
                    derivation_summary["validity_rules"]["data_type"] += 1

        # Log summary
        logger.info("-" * 60)
        logger.info("DERIVATION SUMMARY:")
        logger.info(f"  Total attributes processed: {len(crosstab_attributes)}")
        logger.info(f"  Attributes with profiling: {len(profiling_for_crosstab)}")
        logger.info("")
        logger.info("  COMPLETENESS Rules (Descriptive):")
        logger.info(f"    Mandatory (<5% missing): {derivation_summary['completeness_rules']['mandatory']}")
        logger.info(f"    Expected (5-20% missing): {derivation_summary['completeness_rules']['expected']}")
        logger.info(f"    Conditional (20-70% missing): {derivation_summary['completeness_rules']['conditional']}")
        logger.info(f"    Optional/Skipped (>70% missing): {derivation_summary['completeness_rules']['optional_skipped']}")
        logger.info(f"    Dead Fields (100% missing): {derivation_summary['completeness_rules']['dead_field']}")
        logger.info("")
        logger.info("  VALIDITY Rules (Prescriptive):")
        logger.info(f"    Enumeration: {derivation_summary['validity_rules']['enumeration']}")
        logger.info(f"    Range Check: {derivation_summary['validity_rules']['range_check']}")
        logger.info(f"    Format Pattern: {derivation_summary['validity_rules']['format_pattern']}")
        logger.info(f"    Data Type: {derivation_summary['validity_rules']['data_type']}")
        logger.info("-" * 60)
        logger.info(f"  TOTAL RULES GENERATED: {len(rule_set.rules)}")
        logger.info("=" * 60)

        # Log attribute categorization
        logger.info("\nATTRIBUTE CATEGORIZATION:")
        for category, attrs in derivation_summary["attributes_by_category"].items():
            if attrs:
                logger.info(f"\n  {category.upper()} ({len(attrs)} attributes):")
                for attr in attrs[:5]:  # Show first 5
                    logger.info(f"    - {attr}")
                if len(attrs) > 5:
                    logger.info(f"    ... and {len(attrs) - 5} more")

        return rule_set, derivation_summary

    def _format_crosstab_profiling(
        self,
        crosstab_attributes: list[str],
        profiling_for_crosstab: dict,
    ) -> str:
        """
        Format profiling statistics for cross-tab attributes.

        Args:
            crosstab_attributes: List of cross-tab attribute names.
            profiling_for_crosstab: Dict mapping attributes to their profiling stats.

        Returns:
            Formatted string for prompt.
        """
        lines = ["=" * 60]
        lines.append("PROFILING STATISTICS FOR CROSS-TAB ATTRIBUTES")
        lines.append("=" * 60)

        for attr in crosstab_attributes:
            stats = profiling_for_crosstab.get(attr)

            lines.append(f"\n### {attr}")

            if not stats:
                lines.append("  [No profiling data available]")
                continue

            if not isinstance(stats, dict):
                lines.append(f"  Value: {stats}")
                continue

            lines.append(f"  Data Type: {stats.get('datatype', 'Unknown')}")

            # Range
            range_val = stats.get('range')
            if range_val and isinstance(range_val, list) and len(range_val) == 2:
                if range_val[0] is not None and range_val[1] is not None:
                    lines.append(f"  Range: {range_val[0]} to {range_val[1]}")

            # Missing percentage
            missing = stats.get('missing_percentage', 0)
            lines.append(f"  Missing %: {missing}%")

            # Cardinality
            cardinality = stats.get('cardinality', 'N/A')
            lines.append(f"  Cardinality: {cardinality}")

            # Top values
            top_values = stats.get('top_values', [])
            if top_values:
                lines.append("  Top Values:")
                for tv in top_values[:3]:
                    if isinstance(tv, dict):
                        lines.append(f"    - {tv.get('value', 'N/A')}: {tv.get('count', 0)}")

            # Sparsity & Imbalance
            lines.append(f"  Sparsity: {stats.get('sparsity', 'N/A')}")
            lines.append(f"  Imbalance: {stats.get('imbalance', 'N/A')}")

        return "\n".join(lines)

    def _retrieve_abb_specs_for_crosstab(
        self,
        crosstab_attributes: list[str],
    ) -> tuple[str, list[str]]:
        """
        Retrieve ABB specs from vector DB for cross-tab attributes.

        Args:
            crosstab_attributes: List of cross-tab attribute names.

        Returns:
            Tuple of (formatted specs string, list of attributes with specs found).
        """
        attrs_with_specs = []
        all_chunks = []

        # Query for electrical-related attributes
        for attr in crosstab_attributes:
            clean = attr
            for prefix in ["zz_", "dr_", "xx_"]:
                if attr.lower().startswith(prefix):
                    clean = attr[len(prefix):]
                    break

            clean = clean.replace("_", " ").lower()

            # Only query for electrical-related terms
            if any(kw in clean for kw in [
                "voltage", "current", "power", "rating", "contact", "coil",
                "frequency", "temperature", "phase", "pole", "ip", "category"
            ]):
                try:
                    chunks = self.retriever.retrieve(
                        query=f"{clean} specification",
                        n_results=3,
                        use_expansion=False,
                        use_reranking=False,
                    )
                    if chunks:
                        all_chunks.extend(chunks)
                        attrs_with_specs.append(attr)
                except Exception as e:
                    logger.debug(f"No ABB specs for '{attr}': {e}")

        if not all_chunks:
            return "No ABB specifications found in vector database.", []

        # Deduplicate chunks
        seen = set()
        unique_chunks = []
        for chunk in all_chunks:
            content_hash = hash(chunk.get("content", "")[:100])
            if content_hash not in seen:
                seen.add(content_hash)
                unique_chunks.append(chunk)

        formatted = self.rule_generator.prompt_builder.format_rag_specs(unique_chunks[:15])
        return formatted, list(set(attrs_with_specs))

    def _generate_rules_from_crosstab_legacy(
        self,
        crosstab_attributes: list[str],
        crosstab_formatted: str,
        profiling_for_crosstab: dict,
        profiling_formatted: str,
        wikipedia_formatted: str,
        abb_specs_formatted: str,
    ) -> RuleSet:
        """
        Generate rules for cross-tab attributes using GPT-4o (legacy mode).

        This is the original implementation that uses GPT-4o for rule generation.
        It may produce incorrect rules (e.g., mandatory rules for attributes with >70% missing).

        Use the shape constraint engine for deterministic, correct rule derivation.

        Args:
            crosstab_attributes: List of cross-tab attribute names.
            crosstab_formatted: Formatted cross-tab data.
            profiling_for_crosstab: Profiling stats for cross-tab attributes.
            profiling_formatted: Formatted profiling string.
            wikipedia_formatted: Formatted Wikipedia definitions.
            abb_specs_formatted: Formatted ABB specs (may be empty).

        Returns:
            RuleSet with generated rules.
        """
        from src.rules.rule_models import RuleSet
        import json
        from openai import OpenAI
        import os

        system_prompt = """You are an expert Data Quality Architect generating rules for manufacturers' contactor and relay data.

Your task is to derive data quality rules for attributes defined in the Cross-Tab ontology.

DATA SOURCES (in order of priority):
1. CROSS-TAB ONTOLOGY (PRIMARY) - Defines which attributes need rules
2. PYTHON PROFILING (DATA INSIGHTS) - Provides actual data statistics for those attributes
3. WIKIPEDIA DEFINITIONS (DOMAIN KNOWLEDGE) - Standard definitions for electrical terms
4. ABB SPECIFICATIONS (TECHNICAL REFERENCE) - If available, use for validation values

RULE GENERATION GUIDELINES:
- Generate rules for CROSS-TAB attributes
- Use PROFILING statistics to determine:
  - If missing_percentage > 0: Create COMPLETENESS rule
  - If has numeric range: Create RANGE_CHECK rule
  - If has enumerated values: Create ENUMERATION rule
  - If datatype specified: Create DATA_TYPE rule
- Use Wikipedia for domain context
- Use ABB specs for specific technical values (if available)
- Mark attributes without profiling data as needing data collection

Return response as valid JSON only."""

        # Build attribute list with profiling status
        attrs_info = []
        for attr in crosstab_attributes[:40]:  # Limit to avoid token overflow
            has_profiling = attr in profiling_for_crosstab
            attrs_info.append(f"- {attr} {'[HAS PROFILING]' if has_profiling else '[NO PROFILING]'}")

        attrs_list = "\n".join(attrs_info)

        user_prompt = f"""
Generate data quality rules for the following Cross-Tab attributes.

## CROSS-TAB ATTRIBUTES (Generate rules for these)
{attrs_list}

## CROSS-TAB ONTOLOGY CONTEXT
{crosstab_formatted[:4000]}

## PROFILING STATISTICS (Use these for rule parameters)
{profiling_formatted[:6000]}

## WIKIPEDIA DEFINITIONS (Domain knowledge)
{wikipedia_formatted[:3000]}

## ABB TECHNICAL SPECIFICATIONS (Reference if available)
{abb_specs_formatted[:3000]}

For EACH Cross-Tab attribute, generate appropriate rules:

1. **If attribute has profiling data:**
   - COMPLETENESS: If missing_percentage > 0
   - VALIDITY/RANGE: If numeric with range
   - VALIDITY/ENUMERATION: If categorical with top_values
   - VALIDITY/DATA_TYPE: Based on datatype field

2. **If attribute has NO profiling data:**
   - Generate a COMPLETENESS rule marking it as "data collection required"
   - If it's electrical (voltage, current, etc.), reference Wikipedia/ABB specs for expected values

Return JSON:
{{
    "rules": [
        {{
            "rule_id": "DQR_001",
            "attribute": "exact_crosstab_attribute_name",
            "category": "COMPLETENESS|VALIDITY|CONSISTENCY|ACCURACY",
            "subtype": "mandatory_field|range_check|enumeration|data_type|cross_field",
            "description": "Clear rule description",
            "validation_logic": {{
                "expression": "Python validation expression",
                "parameters": {{"from": "profiling or ABB specs"}},
                "error_message": "Specific error",
                "severity": "ERROR|WARNING"
            }},
            "source_evidence": [
                {{
                    "source_type": "profiling|wikipedia|abb_spec|crosstab",
                    "source_reference": "Source name",
                    "excerpt": "Relevant excerpt",
                    "confidence": 0.95
                }}
            ],
            "business_impact": "Impact description",
            "implementation_notes": "Implementation guidance"
        }}
    ]
}}

Generate at least 20-25 comprehensive rules covering different attributes.
"""

        api_key = os.environ.get("OPENAI_API_KEY")
        client = OpenAI(api_key=api_key)

        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=8192,
            )

            content = response.choices[0].message.content
            if not content:
                logger.error("Empty response from GPT-4o")
                return RuleSet()

            result = json.loads(content)
            rule_set = self.rule_generator._parse_rules(result)

            return rule_set

        except Exception as e:
            logger.error(f"Rule generation failed: {e}")
            import traceback
            traceback.print_exc()
            return RuleSet()

    def _generate_rules_from_profiling(
        self,
        profiling_data: dict,
        profiling_formatted: str,
        crosstab_formatted: str,
        wikipedia_formatted: str,
        abb_specs_formatted: str,
    ) -> RuleSet:
        """
        Generate rules based on profiling data.

        Args:
            profiling_data: Raw profiling statistics dict.
            profiling_formatted: Formatted profiling string.
            crosstab_formatted: Formatted cross-tab string.
            wikipedia_formatted: Formatted Wikipedia definitions.
            abb_specs_formatted: Formatted ABB specifications.

        Returns:
            RuleSet with generated rules.
        """
        from src.rules.rule_models import RuleSet
        import json
        from openai import OpenAI
        import os

        system_prompt = """You are an expert Data Quality Architect analyzing profiling statistics for manufacturers' contactor and relay data.

Your task is to derive comprehensive data quality rules based on:
1. Python Profiling Statistics (PRIMARY SOURCE) - Contains data type, range, missing %, cardinality, top values
2. Cross-Tab Ontology (CONTEXT) - Shows attribute relationships and mappings
3. Wikipedia Definitions (DOMAIN KNOWLEDGE) - Standard electrical engineering definitions
4. ABB Specifications (TECHNICAL REFERENCE) - If relevant, use for validation ranges

RULE GENERATION GUIDELINES:
- Generate rules based on ACTUAL profiling statistics (not assumptions)
- Use the exact ranges, data types, and patterns found in profiling
- If an attribute has high missing %, create a COMPLETENESS rule
- If an attribute has enumerated values (top_values), create ENUMERATION rules
- If an attribute has numeric range, create RANGE_CHECK rules
- Reference ABB specs when the attribute is electrical-related

Return your response as valid JSON only."""

        # Get important attributes (electrical-related or with quality issues)
        important_attrs = []
        for attr, stats in profiling_data.items():
            if not isinstance(stats, dict):
                continue

            # Include if electrical-related
            attr_lower = attr.lower()
            is_electrical = any(kw in attr_lower for kw in [
                "voltage", "current", "power", "rating", "contact", "coil",
                "frequency", "temperature", "phase", "pole", "ip"
            ])

            # Include if has quality issues
            missing = stats.get('missing_percentage', 0)
            has_quality_issue = missing > 0 or stats.get('datatype') == 'Empty'

            if is_electrical or has_quality_issue:
                important_attrs.append(attr)

        attrs_list = "\n".join(f"- {attr}" for attr in important_attrs[:30])

        user_prompt = f"""
Analyze the following data sources and generate comprehensive data quality rules.

## PYTHON PROFILING STATISTICS (Primary Source)
{profiling_formatted[:8000]}

## CROSS-TAB ONTOLOGY (Context)
{crosstab_formatted[:3000]}

## WIKIPEDIA DEFINITIONS (Domain Knowledge)
{wikipedia_formatted[:3000]}

## ABB TECHNICAL SPECIFICATIONS (Reference)
{abb_specs_formatted[:4000]}

## PRIORITY ATTRIBUTES FOR RULE GENERATION
Focus on these {len(important_attrs)} attributes:
{attrs_list}

For EACH priority attribute, generate appropriate rules based on its profiling statistics:

1. **COMPLETENESS rules** if missing_percentage > 0
   - Example: If missing_percentage is 73%, rule should flag records missing this value

2. **VALIDITY rules** based on datatype:
   - Numeric: Create range_check using the profiling range
   - Categorical/Text: Create enumeration rules from top_values
   - Empty: Flag as potential data quality issue

3. **CONSISTENCY rules** for related attributes
   - Example: If Voltage and Current are both present, they should be consistent

4. **ACCURACY rules** for numerical precision

Return JSON with this structure:
{{
    "rules": [
        {{
            "rule_id": "DQR_001",
            "attribute": "exact_attribute_name_from_profiling",
            "category": "COMPLETENESS|VALIDITY|CONSISTENCY|ACCURACY",
            "subtype": "mandatory_field|range_check|enumeration|data_type|cross_field",
            "description": "Clear description based on profiling stats",
            "validation_logic": {{
                "expression": "Python-like validation expression",
                "parameters": {{"derived": "from profiling stats"}},
                "error_message": "Specific error message",
                "severity": "ERROR|WARNING"
            }},
            "source_evidence": [
                {{
                    "source_type": "profiling",
                    "source_reference": "Python Profiling Statistics",
                    "excerpt": "Actual values from profiling data",
                    "confidence": 0.95
                }}
            ],
            "business_impact": "Impact of rule violations",
            "implementation_notes": "How to implement this rule"
        }}
    ]
}}

Generate at least 15-20 rules covering different attributes and categories.
"""

        api_key = os.environ.get("OPENAI_API_KEY")
        client = OpenAI(api_key=api_key)

        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=8192,
            )

            content = response.choices[0].message.content
            if not content:
                logger.error("Empty response from GPT-4o")
                return RuleSet()

            result = json.loads(content)
            rule_set = self.rule_generator._parse_rules(result)

            return rule_set

        except Exception as e:
            logger.error(f"Rule generation failed: {e}")
            import traceback
            traceback.print_exc()
            return RuleSet()

    def run_from_pdf_only(
        self,
        output_format: str = "both",
    ) -> dict[str, Any]:
        """
        Generate data quality rules by analyzing only the vectorized PDF data.

        This method bypasses cross-tab matching and directly extracts attributes
        and generates rules from the ingested PDF specifications.

        Args:
            output_format: Output format - "json", "excel", or "both".

        Returns:
            Dictionary with pipeline results.
        """
        logger.info("Starting PDF-only pipeline run")

        results = {
            "extracted_attributes": [],
            "rule_set": None,
            "output_files": [],
        }

        # 1. Retrieve all documents from vectordb
        logger.info("Retrieving all specifications from vector database...")

        # Query with common electrical terms to get relevant chunks
        query_terms = [
            "rated current contactor",
            "rated voltage electrical",
            "coil voltage control",
            "utilization category AC",
            "mechanical durability life",
            "electrical durability operations",
            "auxiliary contact",
            "power rating specifications",
            "operating temperature range",
            "IP rating protection",
            "frequency Hz",
            "contactor specifications",
            "relay specifications",
        ]

        all_chunks = []
        for term in query_terms:
            try:
                chunks = self.retriever.retrieve(
                    query=term,
                    n_results=20,
                    use_expansion=True,
                    use_reranking=False,
                )
                all_chunks.extend(chunks)
            except Exception as e:
                logger.debug(f"Query failed for '{term}': {e}")

        # Deduplicate chunks by content
        seen_content = set()
        unique_chunks = []
        for chunk in all_chunks:
            content_hash = hash(chunk.get("content", "")[:200])
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                unique_chunks.append(chunk)

        logger.info(f"Retrieved {len(unique_chunks)} unique specification chunks")

        if not unique_chunks:
            logger.warning("No chunks found in vector database. Run ingest first.")
            return results

        # 2. Extract attributes from PDF content
        logger.info("Extracting attributes from PDF specifications...")

        extracted_attrs = self._extract_attributes_from_content(unique_chunks)
        results["extracted_attributes"] = extracted_attrs
        logger.info(f"Extracted {len(extracted_attrs)} attributes from PDFs")

        # 3. Format RAG specs for the prompt
        rag_formatted = self.rule_generator.prompt_builder.format_rag_specs(unique_chunks)

        # 4. Fetch Wikipedia definitions for extracted attributes
        logger.info(f"Fetching Wikipedia definitions for {len(extracted_attrs)} attributes...")
        wikipedia_formatted = self.wikipedia_scraper.scrape_for_matched_attributes(extracted_attrs)

        # 5. Generate rules using a specialized prompt
        logger.info("Generating data quality rules from PDF specifications...")

        rule_set = self._generate_rules_from_pdf_specs(
            rag_specs=rag_formatted,
            wikipedia_defs=wikipedia_formatted,
            extracted_attributes=extracted_attrs,
        )

        results["rule_set"] = rule_set

        # 6. Export results
        logger.info("Exporting results...")

        if output_format in ["json", "both"]:
            json_path = self.json_exporter.export(rule_set)
            results["output_files"].append(str(json_path))

        if output_format in ["excel", "both"]:
            # Create a minimal matching report for Excel export
            matching_report = {
                "matched": [{"canonical": attr, "rag_term": attr, "match_type": "pdf_extracted", "confidence": 1.0} for attr in extracted_attrs],
                "crosstab_only": [],
                "rag_only": [],
                "statistics": {
                    "total_crosstab": 0,
                    "total_rag": len(extracted_attrs),
                    "matched_count": len(extracted_attrs),
                    "match_rate": 1.0,
                }
            }
            excel_path = self.excel_exporter.export(rule_set, matching_report)
            results["output_files"].append(str(excel_path))

        logger.info(f"Pipeline completed. Generated {len(rule_set.rules)} rules.")
        logger.info(f"Output files: {results['output_files']}")

        return results

    def _extract_attributes_from_content(self, chunks: list[dict]) -> list[str]:
        """
        Extract attribute names from PDF content.

        Args:
            chunks: List of chunk dictionaries from vector database.

        Returns:
            List of extracted attribute names.
        """
        # Known electrical attributes to look for in content
        attribute_patterns = {
            "rated_current": ["rated current", "Ie", "rated operational current", "current rating", "load current"],
            "rated_voltage": ["rated voltage", "Ue", "rated operational voltage", "voltage rating", "operating voltage"],
            "coil_voltage": ["coil voltage", "control circuit voltage", "control voltage"],
            "utilization_category": ["utilization category", "AC-1", "AC-3", "AC-4", "DC-1"],
            "mechanical_durability": ["mechanical durability", "mechanical life", "mechanical endurance", "operations"],
            "electrical_durability": ["electrical durability", "electrical life", "electrical endurance"],
            "auxiliary_contact": ["auxiliary contact", "auxiliary contacts", "NO contact", "NC contact"],
            "power_rating": ["power rating", "rated power", "kW rating"],
            "frequency": ["frequency", "Hz", "50Hz", "60Hz"],
            "ip_rating": ["IP rating", "IP code", "protection degree", "IP20", "IP54", "IP65"],
            "ambient_temperature": ["ambient temperature", "operating temperature", "temperature range"],
            "mounting_type": ["mounting", "DIN rail", "panel mount", "screw mounting"],
            "terminal_type": ["terminal", "screw terminal", "spring terminal", "ring terminal"],
            "contact_material": ["contact material", "silver", "AgNi", "AgCdO"],
            "enclosure": ["enclosure", "housing", "IP protection"],
        }

        found_attributes = set()
        all_content = " ".join(chunk.get("content", "").lower() for chunk in chunks)

        for canonical, patterns in attribute_patterns.items():
            for pattern in patterns:
                if pattern.lower() in all_content:
                    found_attributes.add(canonical)
                    break

        return sorted(list(found_attributes))

    def _generate_rules_from_pdf_specs(
        self,
        rag_specs: str,
        wikipedia_defs: str,
        extracted_attributes: list[str],
    ) -> RuleSet:
        """
        Generate rules from PDF specifications only.

        Args:
            rag_specs: Formatted RAG specifications.
            wikipedia_defs: Wikipedia definitions.
            extracted_attributes: List of extracted attributes.

        Returns:
            RuleSet with generated rules.
        """
        from src.rules.rule_models import RuleSet

        # Build a specialized prompt for PDF-only analysis
        system_prompt = """You are an expert Data Quality Architect specializing in electrical equipment specifications.

Your task is to analyze ABB contactor and relay technical specifications and derive comprehensive data quality rules.

IMPORTANT:
1. Base rules ONLY on the specifications provided from the PDF documentation
2. Each rule must reference specific values, ranges, or constraints found in the specs
3. Include practical validation logic that can be implemented in code
4. Focus on electrical safety and compliance requirements (IEC 60947)

Return your response as valid JSON only."""

        attrs_list = "\n".join(f"- {attr}" for attr in extracted_attributes)

        user_prompt = f"""
Analyze the following ABB technical specifications and generate comprehensive data quality rules.

## Technical Specifications from ABB PDF Documentation
{rag_specs}

## Wikipedia Definitions for Context
{wikipedia_defs}

## Extracted Attributes to Generate Rules For
{attrs_list}

For EACH attribute listed above, generate 2-4 data quality rules covering:
- VALIDITY: Valid ranges, data types, enumerated values based on the specs
- COMPLETENESS: Whether the field is mandatory
- CONSISTENCY: Relationships with other fields
- ACCURACY: Required precision for numerical values

CRITICAL: Use specific values from the specifications (e.g., "9A to 2050A" for current ranges).

Return JSON in this format:
{{
    "rules": [
        {{
            "rule_id": "DQR_001",
            "attribute": "rated_current",
            "category": "VALIDITY",
            "subtype": "range_check",
            "description": "Rated current must be within ABB AF contactor range (9A to 2050A)",
            "validation_logic": {{
                "expression": "value >= 9 and value <= 2050",
                "parameters": {{"min": 9, "max": 2050, "unit": "A"}},
                "error_message": "Rated current must be between 9A and 2050A for AF series",
                "severity": "ERROR"
            }},
            "source_evidence": [
                {{
                    "source_type": "rag",
                    "source_reference": "ABB_Contactor_Relays.pdf",
                    "excerpt": "AF contactors range from 9A to 2050A",
                    "confidence": 0.95
                }}
            ],
            "business_impact": "Incorrect current rating may cause equipment damage or safety hazards",
            "implementation_notes": "Validate against AC-3 utilization category"
        }}
    ]
}}
"""

        import json
        from openai import OpenAI
        import os

        api_key = os.environ.get("OPENAI_API_KEY")
        client = OpenAI(api_key=api_key)

        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=4096,
            )

            content = response.choices[0].message.content
            if not content:
                logger.error("Empty response from GPT-4o")
                return RuleSet()

            result = json.loads(content)
            rule_set = self.rule_generator._parse_rules(result)

            return rule_set

        except Exception as e:
            logger.error(f"Rule generation failed: {e}")
            return RuleSet()
