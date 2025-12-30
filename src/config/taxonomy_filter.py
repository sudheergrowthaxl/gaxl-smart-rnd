"""
Taxonomy-based attribute filtering for priority attribute selection.

This module provides efficient data structures and methods for filtering
raw dataset attributes against the Taxonomy Model schema to identify
priority attributes for DQ rule derivation.
"""

import pandas as pd
from pathlib import Path
from typing import Set, List, Dict, Any, Optional, FrozenSet
from functools import lru_cache
import warnings

warnings.filterwarnings('ignore', category=UserWarning)


class TaxonomyAttributeFilter:
    """
    Efficient filter for matching raw dataset attributes against Taxonomy Model.

    Uses a frozenset for O(1) lookup performance when checking if an attribute
    is a priority attribute defined in the taxonomy schema.
    """

    # Default sheet name containing attribute definitions
    ATTRIBUTES_SHEET = "ATTRIBUTES"

    # Column name containing display names to match against
    DISPLAY_NAME_COLUMN = "DISPLAY NAME"

    def __init__(self, schema_path: Optional[str] = None):
        """
        Initialize the TaxonomyAttributeFilter.

        Args:
            schema_path: Path to the schema folder or Excel file.
                         If folder, looks for first .xlsx file.
                         If None, uses default 'data/schema' path.
        """
        self._schema_path = schema_path
        self._taxonomy_attributes: FrozenSet[str] = frozenset()
        self._taxonomy_attributes_lower: FrozenSet[str] = frozenset()
        self._loaded = False

    @property
    def schema_file_path(self) -> Optional[Path]:
        """Get the resolved path to the taxonomy schema Excel file."""
        if self._schema_path is None:
            # Default path
            schema_dir = Path("data/schema")
        else:
            schema_dir = Path(self._schema_path)

        if schema_dir.is_file() and schema_dir.suffix == '.xlsx':
            return schema_dir

        if schema_dir.is_dir():
            xlsx_files = list(schema_dir.glob("*.xlsx"))
            if xlsx_files:
                return xlsx_files[0]

        return None

    def load_taxonomy_attributes(self) -> FrozenSet[str]:
        """
        Load priority attribute names from the Taxonomy Model Excel file.

        Reads the ATTRIBUTES sheet and extracts unique DISPLAY NAME values.
        Uses frozenset for O(1) lookup performance.

        Returns:
            FrozenSet of attribute display names from taxonomy
        """
        if self._loaded:
            return self._taxonomy_attributes

        schema_file = self.schema_file_path
        if schema_file is None or not schema_file.exists():
            print(f"Warning: Taxonomy schema file not found at {self._schema_path}")
            self._taxonomy_attributes = frozenset()
            self._taxonomy_attributes_lower = frozenset()
            self._loaded = True
            return self._taxonomy_attributes

        try:
            # Read the ATTRIBUTES sheet
            df = pd.read_excel(
                schema_file,
                sheet_name=self.ATTRIBUTES_SHEET,
                usecols=[self.DISPLAY_NAME_COLUMN],
                engine='openpyxl'
            )

            # Extract unique non-null display names
            display_names = df[self.DISPLAY_NAME_COLUMN].dropna().unique()

            # Clean and normalize names
            cleaned_names = set()
            for name in display_names:
                name_str = str(name).strip()
                if name_str and name_str.lower() != 'nan':
                    cleaned_names.add(name_str)

            self._taxonomy_attributes = frozenset(cleaned_names)
            self._taxonomy_attributes_lower = frozenset(n.lower() for n in cleaned_names)
            self._loaded = True

            print(f"Loaded {len(self._taxonomy_attributes)} priority attributes from taxonomy schema")

        except Exception as e:
            print(f"Error loading taxonomy attributes: {e}")
            self._taxonomy_attributes = frozenset()
            self._taxonomy_attributes_lower = frozenset()
            self._loaded = True

        return self._taxonomy_attributes

    def is_priority_attribute(self, attribute_name: str, case_sensitive: bool = True) -> bool:
        """
        Check if an attribute is a priority attribute (exists in taxonomy).

        O(1) lookup performance using frozenset.

        Args:
            attribute_name: The attribute name to check
            case_sensitive: Whether to match case-sensitively (default: True)

        Returns:
            True if attribute is in taxonomy, False otherwise
        """
        if not self._loaded:
            self.load_taxonomy_attributes()

        if case_sensitive:
            return attribute_name in self._taxonomy_attributes
        else:
            return attribute_name.lower() in self._taxonomy_attributes_lower

    def filter_priority_attributes(
        self,
        raw_attributes: List[str],
        case_sensitive: bool = True,
        preserve_order: bool = True,
    ) -> List[str]:
        """
        Filter raw dataset attributes to only include priority attributes from taxonomy.

        Args:
            raw_attributes: List of attribute names from raw dataset
            case_sensitive: Whether to match case-sensitively (default: True)
            preserve_order: Whether to preserve original order (default: True)

        Returns:
            List of filtered priority attributes
        """
        if not self._loaded:
            self.load_taxonomy_attributes()

        if not self._taxonomy_attributes:
            # No taxonomy loaded - return empty list
            return []

        filtered = []
        for attr in raw_attributes:
            if self.is_priority_attribute(attr, case_sensitive):
                filtered.append(attr)

        return filtered

    def get_matching_info(
        self,
        raw_attributes: List[str],
        case_sensitive: bool = True,
    ) -> Dict[str, Any]:
        """
        Get detailed matching information for debugging/analysis.

        Args:
            raw_attributes: List of attribute names from raw dataset
            case_sensitive: Whether to match case-sensitively

        Returns:
            Dictionary with matching statistics and details
        """
        if not self._loaded:
            self.load_taxonomy_attributes()

        matched = []
        unmatched = []

        for attr in raw_attributes:
            if self.is_priority_attribute(attr, case_sensitive):
                matched.append(attr)
            else:
                unmatched.append(attr)

        return {
            "total_raw_attributes": len(raw_attributes),
            "total_taxonomy_attributes": len(self._taxonomy_attributes),
            "matched_count": len(matched),
            "unmatched_count": len(unmatched),
            "match_percentage": (len(matched) / len(raw_attributes) * 100) if raw_attributes else 0,
            "matched_attributes": matched,
            "unmatched_attributes": unmatched[:20],  # First 20 for brevity
        }

    @property
    def taxonomy_attributes(self) -> FrozenSet[str]:
        """Get the loaded taxonomy attributes."""
        if not self._loaded:
            self.load_taxonomy_attributes()
        return self._taxonomy_attributes

    def __len__(self) -> int:
        """Return the number of taxonomy attributes."""
        if not self._loaded:
            self.load_taxonomy_attributes()
        return len(self._taxonomy_attributes)


# Module-level cached instance for efficiency
_default_filter: Optional[TaxonomyAttributeFilter] = None


def get_taxonomy_filter(schema_path: Optional[str] = None) -> TaxonomyAttributeFilter:
    """
    Get a TaxonomyAttributeFilter instance.

    Uses a cached default instance when schema_path is None for efficiency.

    Args:
        schema_path: Optional path to schema folder/file

    Returns:
        TaxonomyAttributeFilter instance
    """
    global _default_filter

    if schema_path is None:
        if _default_filter is None:
            _default_filter = TaxonomyAttributeFilter()
        return _default_filter

    return TaxonomyAttributeFilter(schema_path)


def filter_attributes_by_taxonomy(
    raw_attributes: List[str],
    schema_path: Optional[str] = None,
    case_sensitive: bool = True,
) -> List[str]:
    """
    Convenience function to filter attributes by taxonomy.

    Args:
        raw_attributes: List of attribute names from raw dataset
        schema_path: Optional path to schema folder/file
        case_sensitive: Whether to match case-sensitively

    Returns:
        List of filtered priority attributes
    """
    taxonomy_filter = get_taxonomy_filter(schema_path)
    return taxonomy_filter.filter_priority_attributes(
        raw_attributes,
        case_sensitive=case_sensitive,
    )