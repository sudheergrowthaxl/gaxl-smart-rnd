"""Excel exporter for data quality rules."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.rules.rule_models import RuleSet
from src.utils.exceptions import ExportError

logger = logging.getLogger(__name__)


class ExcelExporter:
    """Export data quality rules to Excel format with multiple sheets."""

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the Excel exporter.

        Args:
            config: Configuration dictionary with output paths.
        """
        self.config = config or {}
        data_config = self.config.get("data", {})
        self.output_dir = Path(data_config.get("output", "./data/output"))
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(
        self,
        rule_set: RuleSet,
        matching_result: dict[str, Any] | None = None,
        output_path: str | Path | None = None,
    ) -> Path:
        """
        Export rule set to Excel file with multiple sheets.

        Args:
            rule_set: RuleSet to export.
            matching_result: Optional attribute matching result.
            output_path: Optional output path.

        Returns:
            Path to the exported file.

        Raises:
            ExportError: If export fails.
        """
        if output_path:
            path = Path(output_path)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = self.output_dir / f"data_quality_rules_{timestamp}.xlsx"

        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                # Sheet 1: Rules Master
                self._write_rules_master(writer, rule_set)

                # Sheet 2: Attribute Mapping
                if matching_result:
                    self._write_attribute_mapping(writer, matching_result)

                # Sheet 3: Unmatched Attributes
                if matching_result:
                    self._write_unmatched_attributes(writer, matching_result)

                # Sheet 4: By Category
                self._write_by_category(writer, rule_set)

                # Sheet 5: Source Traceability
                self._write_source_traceability(writer, rule_set)

                # Sheet 6: Implementation Checklist
                self._write_implementation_checklist(writer, rule_set)

            logger.info(f"Exported {len(rule_set.rules)} rules to {path}")
            return path

        except Exception as e:
            raise ExportError(
                f"Failed to export rules to Excel: {e}",
                details={"path": str(path), "error": str(e)},
            )

    def _write_rules_master(
        self, writer: pd.ExcelWriter, rule_set: RuleSet
    ) -> None:
        """Write Rules_Master sheet."""
        data = []

        for rule in rule_set.rules:
            data.append({
                "Rule ID": rule.rule_id,
                "Attribute": rule.attribute,
                "Category": rule.category,
                "Subtype": rule.subtype,
                "Description": rule.description,
                "Validation Expression": rule.validation_logic.expression,
                "Error Message": rule.validation_logic.error_message,
                "Severity": rule.validation_logic.severity,
                "Business Impact": rule.business_impact,
                "Implementation Notes": rule.implementation_notes,
            })

        df = pd.DataFrame(data)
        df.to_excel(writer, sheet_name="Rules_Master", index=False)

    def _write_attribute_mapping(
        self, writer: pd.ExcelWriter, matching_result: dict[str, Any]
    ) -> None:
        """Write Attribute_Mapping sheet."""
        data = []

        for match in matching_result.get("matched", []):
            data.append({
                "Canonical Name": match.get("canonical"),
                "RAG Term": match.get("rag_term"),
                "Match Type": match.get("match_type"),
                "Confidence": match.get("confidence"),
            })

        df = pd.DataFrame(data)
        df.to_excel(writer, sheet_name="Attribute_Mapping", index=False)

    def _write_unmatched_attributes(
        self, writer: pd.ExcelWriter, matching_result: dict[str, Any]
    ) -> None:
        """Write Unmatched_Attributes sheet."""
        crosstab_only = [
            {"Attribute": attr, "Source": "Cross-Tab Only"}
            for attr in matching_result.get("crosstab_only", [])
        ]

        rag_only = [
            {"Attribute": attr, "Source": "RAG Only"}
            for attr in matching_result.get("rag_only", [])
        ]

        df = pd.DataFrame(crosstab_only + rag_only)
        df.to_excel(writer, sheet_name="Unmatched_Attributes", index=False)

    def _write_by_category(
        self, writer: pd.ExcelWriter, rule_set: RuleSet
    ) -> None:
        """Write By_Category sheet with rules grouped by category."""
        data = []

        for rule in sorted(rule_set.rules, key=lambda r: (r.category, r.attribute)):
            data.append({
                "Category": rule.category,
                "Attribute": rule.attribute,
                "Rule ID": rule.rule_id,
                "Description": rule.description,
                "Severity": rule.validation_logic.severity,
            })

        df = pd.DataFrame(data)
        df.to_excel(writer, sheet_name="By_Category", index=False)

    def _write_source_traceability(
        self, writer: pd.ExcelWriter, rule_set: RuleSet
    ) -> None:
        """Write Source_Traceability sheet."""
        data = []

        for rule in rule_set.rules:
            for evidence in rule.source_evidence:
                data.append({
                    "Rule ID": rule.rule_id,
                    "Attribute": rule.attribute,
                    "Source Type": evidence.source_type,
                    "Source Reference": evidence.source_reference,
                    "Excerpt": evidence.excerpt[:200] + "..."
                    if len(evidence.excerpt) > 200
                    else evidence.excerpt,
                    "Confidence": evidence.confidence,
                })

        df = pd.DataFrame(data)
        df.to_excel(writer, sheet_name="Source_Traceability", index=False)

    def _write_implementation_checklist(
        self, writer: pd.ExcelWriter, rule_set: RuleSet
    ) -> None:
        """Write Implementation_Checklist sheet."""
        data = []

        for rule in rule_set.rules:
            data.append({
                "Rule ID": rule.rule_id,
                "Attribute": rule.attribute,
                "Category": rule.category,
                "Implemented": False,
                "Tested": False,
                "In Production": False,
                "Notes": "",
            })

        df = pd.DataFrame(data)
        df.to_excel(writer, sheet_name="Implementation_Checklist", index=False)
