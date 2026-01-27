"""JSON exporter for data quality rules."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from src.rules.rule_models import RuleSet
from src.utils.exceptions import ExportError

logger = logging.getLogger(__name__)


class JSONExporter:
    """Export data quality rules to JSON format."""

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the JSON exporter.

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
        output_path: str | Path | None = None,
        pretty: bool = True,
    ) -> Path:
        """
        Export rule set to JSON file.

        Args:
            rule_set: RuleSet to export.
            output_path: Optional output path. Uses default if not provided.
            pretty: Whether to format JSON with indentation.

        Returns:
            Path to the exported file.

        Raises:
            ExportError: If export fails.
        """
        if output_path:
            path = Path(output_path)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = self.output_dir / f"data_quality_rules_{timestamp}.json"

        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            data = rule_set.to_dict()

            with open(path, "w", encoding="utf-8") as f:
                if pretty:
                    json.dump(data, f, indent=2, default=str)
                else:
                    json.dump(data, f, default=str)

            logger.info(f"Exported {len(rule_set.rules)} rules to {path}")
            return path

        except Exception as e:
            raise ExportError(
                f"Failed to export rules to JSON: {e}",
                details={"path": str(path), "error": str(e)},
            )

    def export_matching_report(
        self,
        matching_result: dict[str, Any],
        output_path: str | Path | None = None,
    ) -> Path:
        """
        Export attribute matching report to JSON.

        Args:
            matching_result: Matching result dictionary.
            output_path: Optional output path.

        Returns:
            Path to the exported file.
        """
        if output_path:
            path = Path(output_path)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = self.output_dir / f"attribute_matching_report_{timestamp}.json"

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(matching_result, f, indent=2, default=str)

            logger.info(f"Exported matching report to {path}")
            return path

        except Exception as e:
            raise ExportError(
                f"Failed to export matching report: {e}",
                details={"path": str(path), "error": str(e)},
            )

    def load(self, input_path: str | Path) -> RuleSet:
        """
        Load rule set from JSON file.

        Args:
            input_path: Path to JSON file.

        Returns:
            Loaded RuleSet.
        """
        path = Path(input_path)

        if not path.exists():
            raise ExportError(
                f"JSON file not found: {path}",
                details={"path": str(path)},
            )

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            return RuleSet(**data)

        except Exception as e:
            raise ExportError(
                f"Failed to load rules from JSON: {e}",
                details={"path": str(path), "error": str(e)},
            )
