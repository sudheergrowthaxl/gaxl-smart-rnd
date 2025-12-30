"""DataProfilerAgent - Loads and analyzes profiling statistics dynamically."""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd

from ..models.profiling_stats import ProfilingResult, DatasetProfile
from ..config.attribute_config import (
    DEFAULT_ATTRIBUTE_COUNT,
    DEFAULT_SCHEMA_PATH,
    DATATYPE_RULE_MAPPING,
    MISSING_SEVERITY_THRESHOLDS,
    get_parent_class_from_profiling,
    derive_dataset_name_from_path,
    find_parent_class_attribute,
)
from ..config.taxonomy_filter import TaxonomyAttributeFilter, get_taxonomy_filter


class DataProfilerAgent:
    """
    Agent responsible for loading and analyzing profiling statistics.

    This agent:
    - Loads profiling JSON from the data pipeline
    - Loads sample data from Excel for validation
    - Parses statistics into structured objects
    - Filters priority attributes using Taxonomy Model schema
    - Derives parent class/category from the data
    - Recommends rule types based on data characteristics
    """

    def __init__(
        self,
        profiling_path: str,
        raw_data_path: Optional[str] = None,
        schema_path: Optional[str] = None,
        attribute_count: int = DEFAULT_ATTRIBUTE_COUNT,
    ):
        """
        Initialize the DataProfilerAgent.

        Args:
            profiling_path: Path to the profiling JSON file
            raw_data_path: Optional path to raw Excel data for sample extraction
            schema_path: Optional path to taxonomy schema folder/file for attribute filtering
            attribute_count: Fallback number of attributes if no taxonomy matches (default: 15)
        """
        self.profiling_path = Path(profiling_path)
        self.raw_data_path = Path(raw_data_path) if raw_data_path else None
        self.schema_path = schema_path or DEFAULT_SCHEMA_PATH
        self.attribute_count = attribute_count
        self.profiling_stats: Dict[str, ProfilingResult] = {}
        self.sample_data: List[Dict[str, Any]] = []
        self.raw_profiling: Dict[str, Any] = {}
        self._parent_class: Optional[str] = None
        self._dataset_name: Optional[str] = None
        self._taxonomy_filter: Optional[TaxonomyAttributeFilter] = None
        self._taxonomy_filtered_attributes: Optional[List[str]] = None

    def load_profiling_json(self) -> Dict[str, Any]:
        """
        Load the existing profiling statistics from JSON.

        Returns:
            Raw profiling data as dictionary
        """
        with open(self.profiling_path, 'r', encoding='utf-8') as f:
            self.raw_profiling = json.load(f)
        return self.raw_profiling

    def parse_profiling_stats(
        self,
        raw_profiling: Optional[Dict[str, Any]] = None
    ) -> Dict[str, ProfilingResult]:
        """
        Parse raw profiling JSON into structured ProfilingResult objects.

        Args:
            raw_profiling: Optional raw profiling data (uses loaded data if not provided)

        Returns:
            Dictionary mapping attribute names to ProfilingResult objects
        """
        if raw_profiling is None:
            raw_profiling = self.raw_profiling

        for attr_name, stats in raw_profiling.items():
            self.profiling_stats[attr_name] = ProfilingResult.from_profiling_dict(
                attr_name, stats
            )

        return self.profiling_stats

    def load_sample_data(self, sample_size: int = 1000) -> pd.DataFrame:
        """
        Load sample data from Excel for validation.

        Args:
            sample_size: Number of rows to load

        Returns:
            DataFrame with sample data
        """
        if self.raw_data_path is None or not self.raw_data_path.exists():
            return pd.DataFrame()

        df = pd.read_excel(self.raw_data_path, nrows=sample_size)
        self.sample_data = df.head(100).to_dict('records')
        return df

    def get_total_records(self) -> int:
        """
        Estimate total records from profiling data.

        Uses the count of records from a non-empty column to estimate total.

        Returns:
            Estimated total number of records
        """
        # Find an attribute with low missing percentage
        for attr_name, stats in self.profiling_stats.items():
            if stats.missing_percentage < 1:
                # Calculate from top values count
                if stats.top_values:
                    total = sum(tv.get('count', 0) for tv in stats.top_values)
                    # Adjust for cardinality
                    cardinality = stats.cardinality_float
                    if cardinality > 0:
                        estimated = int(total / (cardinality / 100)) if cardinality < 100 else total
                        return max(estimated, total)
        return 0

    def get_dynamic_priority_attributes(self) -> List[str]:
        """
        Dynamically select the first N non-empty attributes from the profiling data.

        This is a FALLBACK method used only when taxonomy filtering returns no matches.
        Primary attribute selection should use get_taxonomy_filtered_attributes().

        Returns:
            List of attribute names to process (up to attribute_count)
        """
        selected_attrs = []

        for attr_name, stats in self.profiling_stats.items():
            # Skip completely empty attributes
            if stats.is_empty:
                continue

            # Skip attributes with 100% missing
            if stats.missing_percentage >= 100:
                continue

            selected_attrs.append(attr_name)

            # Stop when we have enough attributes
            if len(selected_attrs) >= self.attribute_count:
                break

        return selected_attrs

    def get_taxonomy_filter(self) -> TaxonomyAttributeFilter:
        """
        Get or create the TaxonomyAttributeFilter instance.

        Returns:
            TaxonomyAttributeFilter instance configured with schema path
        """
        if self._taxonomy_filter is None:
            self._taxonomy_filter = TaxonomyAttributeFilter(self.schema_path)
            self._taxonomy_filter.load_taxonomy_attributes()
        return self._taxonomy_filter

    def get_taxonomy_filtered_attributes(self, case_sensitive: bool = False, limit: int = None) -> List[str]:
        """
        Filter raw dataset attributes against the Taxonomy Model schema.

        This is the PRIMARY method for selecting priority attributes.
        It matches raw dataset attribute names against DISPLAY NAME values
        from the ATTRIBUTES sheet in the Taxonomy Model Excel file.

        Uses FrozenSet for O(1) lookup performance.

        Args:
            case_sensitive: Whether to match case-sensitively (default: False for flexibility)
            limit: Maximum number of attributes to return. If None, uses self.attribute_count.
                   Set to 0 or negative to return ALL matched attributes.

        Returns:
            List of attribute names that exist in both raw data and taxonomy schema.
            Returns fallback (first N non-empty) if taxonomy has no matches.
        """
        if self._taxonomy_filtered_attributes is not None:
            return self._taxonomy_filtered_attributes

        # Determine the limit
        max_attrs = limit if limit is not None else self.attribute_count

        # Get all raw attribute names from profiling data
        raw_attributes = list(self.profiling_stats.keys())

        # Get taxonomy filter and filter attributes
        taxonomy_filter = self.get_taxonomy_filter()
        matching_info = taxonomy_filter.get_matching_info(raw_attributes, case_sensitive)

        # Get matched attributes
        matched_attributes = matching_info.get('matched_attributes', [])

        # Filter out empty attributes from matched list
        filtered_matched = []
        for attr_name in matched_attributes:
            if attr_name in self.profiling_stats:
                stats = self.profiling_stats[attr_name]
                # Skip empty attributes
                if not stats.is_empty and stats.missing_percentage < 100:
                    filtered_matched.append(attr_name)
                    # Apply limit if specified (positive value)
                    if max_attrs > 0 and len(filtered_matched) >= max_attrs:
                        break

        if filtered_matched:
            total_matches = matching_info.get('matched_count', len(filtered_matched))
            if max_attrs > 0:
                print(f"Taxonomy filtering: Selected {len(filtered_matched)} priority attributes (limit: {max_attrs}) from {total_matches} total matches")
            else:
                print(f"Taxonomy filtering: {len(filtered_matched)} priority attributes matched out of {len(raw_attributes)} raw attributes")
            self._taxonomy_filtered_attributes = filtered_matched
        else:
            # Fallback to first N non-empty attributes if no taxonomy matches
            print(f"Warning: No taxonomy matches found. Using fallback (first {self.attribute_count} non-empty attributes)")
            self._taxonomy_filtered_attributes = self.get_dynamic_priority_attributes()

        return self._taxonomy_filtered_attributes

    def get_priority_attributes(self, use_taxonomy: bool = True, case_sensitive: bool = False) -> List[str]:
        """
        Get priority attributes for rule derivation.

        This is the MAIN entry point for getting attributes to process.
        By default, uses taxonomy-based filtering for accurate attribute selection.

        Args:
            use_taxonomy: Whether to use taxonomy filtering (default: True)
            case_sensitive: Whether taxonomy matching is case-sensitive (default: False)

        Returns:
            List of priority attribute names
        """
        if use_taxonomy:
            return self.get_taxonomy_filtered_attributes(case_sensitive)
        else:
            return self.get_dynamic_priority_attributes()

    def get_taxonomy_matching_info(self, case_sensitive: bool = False) -> Dict[str, Any]:
        """
        Get detailed information about taxonomy attribute matching.

        Useful for debugging and reporting purposes.

        Args:
            case_sensitive: Whether to match case-sensitively

        Returns:
            Dictionary with matching statistics and details
        """
        raw_attributes = list(self.profiling_stats.keys())
        taxonomy_filter = self.get_taxonomy_filter()
        return taxonomy_filter.get_matching_info(raw_attributes, case_sensitive)

    def get_all_non_empty_attributes(self) -> List[str]:
        """
        Get all attributes that are not completely empty.

        Returns:
            List of non-empty attribute names
        """
        return [
            attr for attr, stats in self.profiling_stats.items()
            if not stats.is_empty
        ]

    def get_parent_class(self) -> str:
        """
        Get the parent class/category derived from the profiling data.

        Returns:
            Parent class string
        """
        if self._parent_class is None:
            self._parent_class = get_parent_class_from_profiling(self.profiling_stats)
        return self._parent_class

    def get_dataset_name(self) -> str:
        """
        Get the dataset name derived from the file path.

        Returns:
            Dataset name string
        """
        if self._dataset_name is None:
            # Try to derive from raw data path first, then profiling path
            if self.raw_data_path:
                self._dataset_name = derive_dataset_name_from_path(str(self.raw_data_path))
            else:
                self._dataset_name = derive_dataset_name_from_path(str(self.profiling_path))

            # If we have a parent class, include it in the name
            parent_class = self.get_parent_class()
            if parent_class and parent_class != "Unknown":
                # Clean the parent class for use in dataset name
                clean_parent = parent_class.replace(" ", "_").replace("&", "and")
                if clean_parent.lower() not in self._dataset_name.lower():
                    self._dataset_name = f"{clean_parent}_Data"

        return self._dataset_name

    def recommend_rule_types(self, stats: ProfilingResult) -> List[str]:
        """
        Recommend applicable rule types based on profiling statistics.

        Args:
            stats: ProfilingResult for the attribute

        Returns:
            List of recommended rule type strings
        """
        recommendations = []

        # Get base recommendations from datatype
        datatype_rules = DATATYPE_RULE_MAPPING.get(stats.datatype, [])
        recommendations.extend(datatype_rules)

        # Add completeness rule if there's missing data but not 100%
        if 0 < stats.missing_percentage < 100:
            # Determine severity based on missing percentage
            for severity, (low, high) in MISSING_SEVERITY_THRESHOLDS.items():
                if low <= stats.missing_percentage < high:
                    recommendations.append(f"NOT_NULL:{severity}")
                    break

        # Add uniqueness rule for high cardinality
        if stats.is_high_cardinality:
            if "PRIMARY_KEY" not in recommendations:
                recommendations.append("PRIMARY_KEY")
        elif stats.cardinality_float > 80:
            recommendations.append("NEAR_DUPLICATE")

        # Add consistency rules for categorical with multiple format variations
        if stats.datatype == "Categorical":
            # Check for case inconsistency in top values
            if stats.top_values and len(stats.top_values) > 1:
                values = [str(tv.get('value', '')) for tv in stats.top_values[:10]]
                # Check if same value appears with different cases
                lower_values = [v.lower() for v in values]
                if len(lower_values) != len(set(lower_values)):
                    recommendations.append("CASE_CONSISTENCY")

        return list(set(recommendations))  # Remove duplicates

    def recommend_severity(self, stats: ProfilingResult) -> str:
        """
        Recommend severity level based on attribute characteristics.

        Args:
            stats: ProfilingResult for the attribute

        Returns:
            Recommended severity string
        """
        # High cardinality suggests important identifier
        if stats.is_high_cardinality:
            return "Critical"

        # Low missing data suggests important field
        if stats.missing_percentage < 5:
            return "High"
        elif stats.missing_percentage < 20:
            return "Medium"
        else:
            return "Low"

    def analyze_attribute(self, attr_name: str) -> Dict[str, Any]:
        """
        Analyze a specific attribute and prepare context for rule derivation.

        Args:
            attr_name: Name of the attribute to analyze

        Returns:
            Dictionary with analysis results
        """
        if attr_name not in self.profiling_stats:
            raise ValueError(f"Attribute '{attr_name}' not found in profiling stats")

        stats = self.profiling_stats[attr_name]

        analysis = {
            "attribute_name": attr_name,
            "datatype": stats.datatype,
            "missing_percentage": stats.missing_percentage,
            "cardinality": stats.cardinality,
            "top_values": stats.top_values[:10],  # Top 10 for context
            "range": stats.range,
            "is_empty": stats.is_empty,
            "is_high_cardinality": stats.is_high_cardinality,
            "recommended_rules": self.recommend_rule_types(stats),
            "recommended_severity": self.recommend_severity(stats),
        }

        # Add numeric range info if applicable
        if stats.datatype == "Numeric" and stats.range:
            numeric_range = stats.get_numeric_range()
            if numeric_range:
                analysis["min_value"] = numeric_range[0]
                analysis["max_value"] = numeric_range[1]

        return analysis

    def get_dataset_context(self, use_taxonomy: bool = True) -> Dict[str, Any]:
        """
        Get overall dataset context for rule derivation.
        All values are derived dynamically - no hardcoded values.

        Args:
            use_taxonomy: Whether to use taxonomy filtering for priority attributes (default: True)

        Returns:
            Dictionary with dataset metadata
        """
        # Get parent class attribute name for reference
        parent_class_attr = find_parent_class_attribute(self.profiling_stats)

        # Get priority attributes - taxonomy filtered by default
        priority_attrs = self.get_priority_attributes(use_taxonomy=use_taxonomy)

        # Get taxonomy matching info for reporting
        taxonomy_info = self.get_taxonomy_matching_info() if use_taxonomy else {}

        return {
            "dataset_name": self.get_dataset_name(),
            "parent_class": self.get_parent_class(),
            "parent_class_attribute": parent_class_attr,
            "total_records": self.get_total_records(),
            "total_attributes": len(self.profiling_stats),
            "non_empty_attributes": len(self.get_all_non_empty_attributes()),
            "priority_attributes": priority_attrs,
            "taxonomy_match_count": taxonomy_info.get('matched_count', 0),
            "taxonomy_total_attributes": taxonomy_info.get('total_taxonomy_attributes', 0),
        }