"""Loader for cross-tab ontology data."""

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src.utils.exceptions import ConfigurationError

logger = logging.getLogger(__name__)


class CrosstabLoader:
    """
    Load and process cross-tab data mapping priority attributes to core properties.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the cross-tab loader.

        Args:
            config: Configuration dictionary with data paths.
        """
        self.config = config or {}
        data_config = self.config.get("data", {}).get("input", {})
        self.crosstab_dir = Path(data_config.get("crosstab", "./data/input/crosstab"))

    def load(self, file_path: str | Path | None = None) -> pd.DataFrame:
        """
        Load cross-tab data from file.

        Args:
            file_path: Optional specific file path. If not provided,
                      loads from configured directory.

        Returns:
            DataFrame with cross-tab data.

        Raises:
            ConfigurationError: If file not found or invalid.
        """
        if file_path:
            path = Path(file_path)
        else:
            # Find first CSV or Excel file in directory
            path = self._find_crosstab_file()

        if not path or not path.exists():
            raise ConfigurationError(
                f"Cross-tab file not found: {path}",
                details={"path": str(path)},
            )

        logger.info(f"Loading cross-tab from: {path}")

        try:
            if path.suffix.lower() == ".csv":
                df = pd.read_csv(path)
            elif path.suffix.lower() in [".xlsx", ".xls"]:
                df = pd.read_excel(path)
            else:
                raise ConfigurationError(
                    f"Unsupported file format: {path.suffix}",
                    details={"path": str(path)},
                )

            logger.info(f"Loaded cross-tab with {len(df)} rows and {len(df.columns)} columns")
            return df

        except Exception as e:
            raise ConfigurationError(
                f"Failed to load cross-tab: {e}",
                details={"path": str(path), "error": str(e)},
            )

    def _find_crosstab_file(self) -> Path | None:
        """Find the first cross-tab file in the configured directory."""
        if not self.crosstab_dir.exists():
            return None

        for ext in ["*.csv", "*.xlsx", "*.xls"]:
            files = list(self.crosstab_dir.glob(ext))
            if files:
                return files[0]

        return None

    def get_attributes(self, df: pd.DataFrame | None = None) -> list[str]:
        """
        Get list of priority attributes from cross-tab.

        Args:
            df: Optional DataFrame. If not provided, loads from file.

        Returns:
            List of attribute names.
        """
        if df is None:
            df = self.load()

        # Try common column names for attributes
        attr_columns = [
            "priority_attribute",
            "attribute",
            "attribute_name",
            "Priority Attribute",
            "Attribute",
        ]

        for col in attr_columns:
            if col in df.columns:
                return df[col].dropna().unique().tolist()

        # Fallback to first column
        if len(df.columns) > 0:
            return df.iloc[:, 0].dropna().unique().tolist()

        return []

    def get_attribute_mapping(self, df: pd.DataFrame | None = None) -> dict[str, dict]:
        """
        Get mapping of attributes to their core properties.

        Args:
            df: Optional DataFrame. If not provided, loads from file.

        Returns:
            Dictionary mapping attribute names to their properties.
        """
        if df is None:
            df = self.load()

        mapping = {}

        # Try to identify attribute and property columns
        attr_col = None
        prop_col = None

        for col in df.columns:
            col_lower = col.lower()
            if "attribute" in col_lower and attr_col is None:
                attr_col = col
            elif "property" in col_lower or "core" in col_lower:
                prop_col = col

        if attr_col is None and len(df.columns) >= 1:
            attr_col = df.columns[0]
        if prop_col is None and len(df.columns) >= 2:
            prop_col = df.columns[1]

        if attr_col and prop_col:
            for _, row in df.iterrows():
                attr_name = row[attr_col]
                if pd.notna(attr_name):
                    mapping[str(attr_name)] = {
                        "core_property": row.get(prop_col),
                        "row_data": row.to_dict(),
                    }

        return mapping

    def format_for_prompt(self, df: pd.DataFrame | None = None) -> str:
        """
        Format cross-tab data for inclusion in LLM prompt.

        Args:
            df: Optional DataFrame.

        Returns:
            Formatted string representation.
        """
        if df is None:
            df = self.load()

        lines = ["Cross-Tab Priority Attributes:"]
        lines.append("-" * 40)

        for i, row in df.iterrows():
            row_str = " | ".join(f"{k}: {v}" for k, v in row.items() if pd.notna(v))
            lines.append(row_str)

        return "\n".join(lines)
