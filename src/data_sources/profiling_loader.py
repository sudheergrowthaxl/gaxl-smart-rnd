"""Loader for profiling statistics data."""

import json
import logging
from pathlib import Path
from typing import Any

from src.utils.exceptions import ConfigurationError

logger = logging.getLogger(__name__)


class ProfilingLoader:
    """
    Load and process profiling statistics for data quality analysis.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the profiling loader.

        Args:
            config: Configuration dictionary with data paths.
        """
        self.config = config or {}
        data_config = self.config.get("data", {}).get("input", {})
        self.profiling_dir = Path(
            data_config.get("profiling", "./data/input/profiling")
        )

    def load(self, file_path: str | Path | None = None) -> dict[str, Any]:
        """
        Load profiling statistics from JSON file.

        Args:
            file_path: Optional specific file path.

        Returns:
            Dictionary with profiling statistics.

        Raises:
            ConfigurationError: If file not found or invalid.
        """
        if file_path:
            path = Path(file_path)
        else:
            path = self._find_profiling_file()

        if not path or not path.exists():
            logger.warning(f"Profiling file not found: {path}")
            return {}

        logger.info(f"Loading profiling data from: {path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            logger.info(f"Loaded profiling data with {len(data)} entries")
            return data

        except json.JSONDecodeError as e:
            raise ConfigurationError(
                f"Invalid JSON in profiling file: {e}",
                details={"path": str(path), "error": str(e)},
            )

    def _find_profiling_file(self) -> Path | None:
        """Find the first profiling file in the configured directory."""
        if not self.profiling_dir.exists():
            return None

        files = list(self.profiling_dir.glob("*.json"))
        return files[0] if files else None

    def get_attribute_stats(
        self, attribute_name: str, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Get statistics for a specific attribute.

        Args:
            attribute_name: Name of the attribute.
            data: Optional profiling data. If not provided, loads from file.

        Returns:
            Dictionary with attribute statistics.
        """
        if data is None:
            data = self.load()

        # Try direct lookup
        if attribute_name in data:
            return data[attribute_name]

        # Try case-insensitive lookup
        for key, value in data.items():
            if key.lower() == attribute_name.lower():
                return value

        # Try with underscores replaced
        normalized = attribute_name.replace("_", " ").lower()
        for key, value in data.items():
            if key.replace("_", " ").lower() == normalized:
                return value

        return {}

    def get_all_attributes(self, data: dict[str, Any] | None = None) -> list[str]:
        """
        Get list of all attributes in profiling data.

        Args:
            data: Optional profiling data.

        Returns:
            List of attribute names.
        """
        if data is None:
            data = self.load()

        return list(data.keys())

    def format_for_prompt(
        self, data: dict[str, Any] | None = None, attributes: list[str] | None = None
    ) -> str:
        """
        Format profiling statistics for inclusion in LLM prompt.

        Args:
            data: Optional profiling data.
            attributes: Optional list of attributes to include.

        Returns:
            Formatted string representation.
        """
        if data is None:
            data = self.load()

        lines = ["Profiling Statistics:"]
        lines.append("-" * 40)

        attrs_to_include = attributes or list(data.keys())

        for attr in attrs_to_include:
            if attr in data:
                stats = data[attr]
                lines.append(f"\n{attr}:")

                if isinstance(stats, dict):
                    for key, value in stats.items():
                        lines.append(f"  {key}: {value}")
                else:
                    lines.append(f"  Value: {stats}")

        return "\n".join(lines)

    def extract_data_quality_hints(
        self, data: dict[str, Any] | None = None
    ) -> dict[str, list[str]]:
        """
        Extract data quality hints from profiling statistics.

        Args:
            data: Optional profiling data.

        Returns:
            Dictionary mapping attributes to quality hints.
        """
        if data is None:
            data = self.load()

        hints = {}

        for attr, stats in data.items():
            if not isinstance(stats, dict):
                continue

            attr_hints = []

            # Check completeness
            null_pct = stats.get("null_percentage", stats.get("missing_percentage", 0))
            if null_pct > 0:
                attr_hints.append(f"Has {null_pct}% null values")

            # Check for unique values
            unique_count = stats.get("unique_count", stats.get("distinct_count"))
            if unique_count:
                attr_hints.append(f"Has {unique_count} unique values")

            # Check data type
            dtype = stats.get("dtype", stats.get("data_type"))
            if dtype:
                attr_hints.append(f"Data type: {dtype}")

            # Check range
            min_val = stats.get("min")
            max_val = stats.get("max")
            if min_val is not None and max_val is not None:
                attr_hints.append(f"Range: {min_val} to {max_val}")

            if attr_hints:
                hints[attr] = attr_hints

        return hints
