"""DataProfilerAgent - Loads and analyzes profiling statistics."""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd

from ..models.profiling_stats import ProfilingResult, DatasetProfile
from ..config.attribute_config import (
    PRIORITY_ATTRIBUTES,
    DATATYPE_RULE_MAPPING,
    MISSING_SEVERITY_THRESHOLDS,
)


class DataProfilerAgent:
    """
    Agent responsible for loading and analyzing profiling statistics.

    This agent:
    - Loads profiling JSON from the data pipeline
    - Loads sample data from Excel for validation
    - Parses statistics into structured objects
    - Recommends rule types based on data characteristics
    """

    def __init__(
        self,
        profiling_path: str,
        raw_data_path: Optional[str] = None,
    ):
        """
        Initialize the DataProfilerAgent.

        Args:
            profiling_path: Path to the profiling JSON file
            raw_data_path: Optional path to raw Excel data for sample extraction
        """
        self.profiling_path = Path(profiling_path)
        self.raw_data_path = Path(raw_data_path) if raw_data_path else None
        self.profiling_stats: Dict[str, ProfilingResult] = {}
        self.sample_data: List[Dict[str, Any]] = []
        self.raw_profiling: Dict[str, Any] = {}

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
                        return max(estimated, 25000)  # Minimum based on known data
        return 0 

    def get_priority_attributes(self) -> List[str]:
        """
        Return the list of priority attributes that exist in the profiling data.

        Returns:
            List of attribute names to process
        """
        return [
            attr for attr in PRIORITY_ATTRIBUTES
            if attr in self.profiling_stats
        ]

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

    def get_dataset_context(self) -> Dict[str, Any]:
        """
        Get overall dataset context for rule derivation.

        Returns:
            Dictionary with dataset metadata
        """
        return {
            "dataset_name": "Contactors_Product_Data",
            "domain": "Product",
            "total_records": self.get_total_records(),
            "total_attributes": len(self.profiling_stats),
            "non_empty_attributes": len(self.get_all_non_empty_attributes()),
            "priority_attributes": self.get_priority_attributes(),
        }
