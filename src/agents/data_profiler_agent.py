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
    MAX_MISSING_THRESHOLD,
    CARDINALITY_THRESHOLDS,
    get_parent_class_from_profiling,
    derive_dataset_name_from_path,
    find_parent_class_attribute,
    should_skip_for_missing,
    meets_cardinality_threshold,
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

    def load_sample_data(self, sample_size: int = 10000) -> pd.DataFrame:
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
        self.sample_data = df.head(10000).to_dict('records')
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
                        estimated = int(total / (cardinality / 10000)) if cardinality < 10000 else total
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

        # Filter out empty attributes and high-missing attributes from matched list
        filtered_matched = []
        skipped_high_missing = []
        skipped_low_cardinality = []
        for attr_name in matched_attributes:
            if attr_name in self.profiling_stats:
                stats = self.profiling_stats[attr_name]
                # Skip empty attributes
                if stats.is_empty or stats.missing_percentage >= 100:
                    continue
                # Skip attributes with >70% missing values
                if should_skip_for_missing(stats.missing_percentage):
                    skipped_high_missing.append(attr_name)
                    continue
                # Skip attributes that don't meet cardinality threshold
                if not meets_cardinality_threshold(stats.datatype, stats.cardinality_float):
                    skipped_low_cardinality.append(attr_name)
                    continue
                filtered_matched.append(attr_name)
                # Apply limit if specified (positive value)
                if max_attrs > 0 and len(filtered_matched) >= max_attrs:
                    break

        # Log skipped attributes
        if skipped_high_missing:
            print(f"  Skipped {len(skipped_high_missing)} attributes with >70% missing: {skipped_high_missing[:5]}{'...' if len(skipped_high_missing) > 5 else ''}")
        if skipped_low_cardinality:
            print(f"  Skipped {len(skipped_low_cardinality)} attributes with low cardinality: {skipped_low_cardinality[:5]}{'...' if len(skipped_low_cardinality) > 5 else ''}")

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

        DATA-DRIVEN APPROACH:
        - For sparse fields (>95% missing): Only validity rules, NO completeness rules
        - For partially populated fields (>50% missing): Validity rules, optional completeness
        - For well-populated fields (<20% missing): Full rule set including completeness

        ADDITIONAL RULE TYPES (Beyond DAMA Core):
        - NORMALIZATION: When value variations exist for same semantic meaning
        - COMPUTATION: When cross-field relationships can be inferred
        - DEFAULT: When default values can be suggested for missing data

        Args:
            stats: ProfilingResult for the attribute

        Returns:
            List of recommended rule type strings
        """
        recommendations = []
        missing_pct = stats.missing_percentage

        # DATA-DRIVEN: Skip completeness rules for sparse fields
        if missing_pct >= 95:
            # SPARSE FIELD: Only recommend validity rules for the small % that has data
            # DO NOT recommend completeness rules
            if stats.datatype == "Categorical" and stats.top_values:
                recommendations.append("VALUE_SET:Low")
                # Check for normalization opportunities even in sparse fields
                if self._has_value_variations(stats.top_values):
                    recommendations.append("NORMALIZATION:Low")
            elif stats.datatype == "Numeric" and stats.range:
                recommendations.append("RANGE:Low")
            elif stats.datatype == "Text":
                recommendations.append("FORMAT_PATTERN:Low")
            # Mark as sparse field
            recommendations.append("SPARSE_FIELD")
            return list(set(recommendations))

        # Get base recommendations from datatype
        datatype_rules = DATATYPE_RULE_MAPPING.get(stats.datatype, [])
        recommendations.extend(datatype_rules)

        # DATA-DRIVEN: Completeness rules based on actual missing percentage
        if 0 < missing_pct < 100:
            if missing_pct < 5:
                # Required field - Critical severity
                recommendations.append(f"NOT_NULL:Critical")
            elif missing_pct < 20:
                # Well-populated - High severity
                recommendations.append(f"NOT_NULL:High")
            elif missing_pct < 50:
                # Moderately populated - Medium severity
                recommendations.append(f"NOT_NULL:Medium")
            elif missing_pct < 95:
                # Partially populated - Low severity (optional)
                recommendations.append(f"NOT_NULL:Low")
            # For >= 95%, no completeness rule (handled above)

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

        # =========================================================
        # ADDITIONAL RULE TYPES (Beyond DAMA Core)
        # =========================================================

        # NORMALIZATION: Recommend when value variations exist
        if stats.datatype == "Categorical" and stats.top_values:
            if self._has_value_variations(stats.top_values):
                recommendations.append("NORMALIZATION")
            if self._has_format_variations(stats.top_values):
                recommendations.append("FORMAT_STANDARDIZATION")
            if self._has_unit_variations(stats.top_values):
                recommendations.append("UNIT_CONVERSION")

        # COMPUTATION: Recommend for fields that likely have cross-field dependencies
        # Based on attribute name patterns suggesting relationships
        attr_lower = stats.attribute_name.lower()
        if any(kw in attr_lower for kw in ['current', 'voltage', 'frequency', 'type', 'rating']):
            recommendations.append("CONDITIONAL_VALIDATION")
        if any(kw in attr_lower for kw in ['derived', 'calculated', 'total', 'sum']):
            recommendations.append("DERIVED_VALUE")

        # DEFAULT: Recommend for partially populated fields where defaults make sense
        if 20 < missing_pct < 80:
            # Fields with moderate missing % might benefit from default values
            if stats.datatype == "Categorical" and stats.top_values:
                # If there's a dominant value, it could be a good default
                if len(stats.top_values) >= 1:
                    top_value_count = stats.top_values[0].get('count', 0)
                    total_populated = sum(tv.get('count', 0) for tv in stats.top_values)
                    if total_populated > 0 and (top_value_count / total_populated) > 0.5:
                        recommendations.append("CONDITIONAL_DEFAULT")

        return list(set(recommendations))  # Remove duplicates

    def _has_value_variations(self, top_values: List[Dict[str, Any]]) -> bool:
        """
        Check if top values contain variations of the same semantic value.

        Examples:
        - "3P", "3 Pole", "Three Pole" → same value, different representations
        - "1NO+1NC", "1 NO + 1 NC" → same value, different formats

        Args:
            top_values: List of top value dictionaries

        Returns:
            True if variations detected
        """
        if not top_values or len(top_values) < 2:
            return False

        values = [str(tv.get('value', '')).strip() for tv in top_values[:10] if tv.get('value')]

        # Check for common variation patterns
        for i, v1 in enumerate(values):
            for v2 in values[i + 1:]:
                # Remove spaces and compare
                v1_clean = v1.replace(' ', '').replace('+', '').lower()
                v2_clean = v2.replace(' ', '').replace('+', '').lower()

                # If cleaned versions are similar but originals differ, it's a variation
                if v1 != v2 and (v1_clean == v2_clean or v1_clean in v2_clean or v2_clean in v1_clean):
                    return True

                # Check for numeric with suffix variations (3P, 3 Pole, etc.)
                import re
                v1_num = re.sub(r'[^0-9]', '', v1)
                v2_num = re.sub(r'[^0-9]', '', v2)
                if v1_num and v2_num and v1_num == v2_num and v1 != v2:
                    # Same number, different format
                    if len(v1_num) < len(v1) / 2 and len(v2_num) < len(v2) / 2:
                        return True

        return False

    def _has_format_variations(self, top_values: List[Dict[str, Any]]) -> bool:
        """
        Check if top values have format variations (spacing, separators, etc.)

        Examples:
        - "24V DC" vs "24 V DC" vs "24VDC"
        - "50Hz" vs "50 Hz"

        Args:
            top_values: List of top value dictionaries

        Returns:
            True if format variations detected
        """
        if not top_values or len(top_values) < 2:
            return False

        values = [str(tv.get('value', '')).strip() for tv in top_values[:10] if tv.get('value')]
        import re

        # Look for unit patterns with different spacing
        unit_pattern = re.compile(r'(\d+)\s*([a-zA-Z]+)')

        formatted_values = []
        for v in values:
            match = unit_pattern.search(v)
            if match:
                formatted_values.append(f"{match.group(1)}_{match.group(2)}")

        # If we have multiple values that normalize to the same pattern, it's a format variation
        if len(formatted_values) > len(set(formatted_values)):
            return True

        return False

    def _has_unit_variations(self, top_values: List[Dict[str, Any]]) -> bool:
        """
        Check if top values contain unit variations that need conversion.

        Examples:
        - "V", "Volt", "Volts"
        - "A", "Amp", "Amps"
        - "Hz", "Hertz"

        Args:
            top_values: List of top value dictionaries

        Returns:
            True if unit variations detected
        """
        if not top_values or len(top_values) < 2:
            return False

        values = [str(tv.get('value', '')).lower() for tv in top_values[:10] if tv.get('value')]

        # Common unit variations
        unit_groups = [
            ['v', 'volt', 'volts'],
            ['a', 'amp', 'amps', 'ampere', 'amperes'],
            ['hz', 'hertz'],
            ['w', 'watt', 'watts'],
            ['ohm', 'ohms', 'ω'],
        ]

        for group in unit_groups:
            found_units = []
            for v in values:
                for unit in group:
                    if unit in v:
                        found_units.append(unit)
                        break
            # If we found multiple different unit representations, it's a variation
            if len(set(found_units)) > 1:
                return True

        return False

    def detect_numeric_pattern(self, top_values: List[Dict[str, Any]], numeric_range: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
        """
        Detect patterns in numeric top_values to generate generalized rules.

        Instead of listing specific values like [2.0, 3.0, 5.0, 7.5, 10.0],
        this method identifies the underlying pattern (e.g., values from 2.0 to 10.0 with 0.5 step).

        Args:
            top_values: List of top value dictionaries with 'value' and 'count'
            numeric_range: Optional (min, max) tuple from profiling

        Returns:
            Pattern dictionary with type, min, max, step, description, or None if no pattern found
        """
        if not top_values or len(top_values) < 2:
            return None

        # Extract numeric values
        numeric_vals = []
        total_count = 0
        for tv in top_values:
            try:
                val = float(tv.get('value', 0))
                count = int(tv.get('count', 0))
                numeric_vals.append(val)
                total_count += count
            except (ValueError, TypeError):
                continue

        if len(numeric_vals) < 2:
            return None

        # Sort values to analyze pattern
        numeric_vals = sorted(set(numeric_vals))

        if len(numeric_vals) < 2:
            return None

        # Calculate differences between consecutive values
        diffs = [round(numeric_vals[i+1] - numeric_vals[i], 6) for i in range(len(numeric_vals) - 1)]

        # Find the most common difference (GCD-like approach for step detection)
        from collections import Counter
        diff_counts = Counter(diffs)

        # Get observed min/max
        obs_min = min(numeric_vals)
        obs_max = max(numeric_vals)

        # Use range from profiling if available
        if numeric_range:
            range_min, range_max = numeric_range
        else:
            range_min, range_max = obs_min, obs_max

        # Check for arithmetic sequence pattern
        if len(diff_counts) > 0:
            most_common_diff, count = diff_counts.most_common(1)[0]

            # If >60% of differences match the most common difference, it's a sequence
            if count >= len(diffs) * 0.6 and most_common_diff > 0:
                # Try to find a cleaner step (round to common fractions)
                step = self._round_to_clean_step(most_common_diff)

                # Verify the step works for most values
                valid_values = 0
                for val in numeric_vals:
                    # Check if (val - min) is divisible by step
                    remainder = abs((val - range_min) % step)
                    if remainder < 0.0001 or abs(remainder - step) < 0.0001:
                        valid_values += 1

                if valid_values >= len(numeric_vals) * 0.7:
                    # Generate example invalid values
                    invalid_examples = self._generate_invalid_examples(range_min, range_max, step)

                    return {
                        "type": "arithmetic_sequence",
                        "min": range_min,
                        "max": range_max,
                        "step": step,
                        "observed_values_count": len(numeric_vals),
                        "description": f"Values should be between {range_min} and {range_max} with {step} increments",
                        "invalid_examples": invalid_examples,
                        "support": total_count,
                    }

        # Check for discrete value set (small number of specific values)
        if len(numeric_vals) <= 10:
            return {
                "type": "discrete_set",
                "min": range_min,
                "max": range_max,
                "step": None,
                "observed_values_count": len(numeric_vals),
                "description": f"Discrete numeric values between {range_min} and {range_max}",
                "invalid_examples": [],
                "support": total_count,
            }

        # Check for integer-only pattern
        all_integers = all(val == int(val) for val in numeric_vals)
        if all_integers:
            return {
                "type": "integer_only",
                "min": int(range_min),
                "max": int(range_max),
                "step": 1,
                "observed_values_count": len(numeric_vals),
                "description": f"Integer values between {int(range_min)} and {int(range_max)}",
                "invalid_examples": [f"{range_min + 0.5}", f"{range_max - 0.3}"],
                "support": total_count,
            }

        return None

    def _round_to_clean_step(self, diff: float) -> float:
        """
        Round a difference to a clean step value.

        Common steps: 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, etc.
        """
        clean_steps = [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 2.5, 5.0, 10.0, 25.0, 50.0, 100.0]

        # Find the closest clean step
        closest = min(clean_steps, key=lambda x: abs(x - diff))

        # Only use clean step if it's within 20% of the observed diff
        if abs(closest - diff) / diff < 0.2:
            return closest
        return round(diff, 2)

    def _generate_invalid_examples(self, min_val: float, max_val: float, step: float) -> List[str]:
        """
        Generate examples of invalid values based on the pattern.

        For a pattern with step 0.5, invalid values would be things like 2.3, 2.7, etc.
        """
        invalid = []

        # Generate values that don't match the step
        test_val = min_val + step / 3  # Offset from valid sequence
        if test_val <= max_val:
            invalid.append(str(round(test_val, 2)))

        test_val = min_val + step / 2 + step  # Another offset
        if test_val <= max_val and len(invalid) < 3:
            invalid.append(str(round(test_val, 2)))

        test_val = (min_val + max_val) / 2 + step / 4
        if test_val <= max_val and len(invalid) < 3:
            invalid.append(str(round(test_val, 2)))

        # Values outside range
        if min_val > 0:
            invalid.append(str(round(min_val - step, 2)))
        invalid.append(str(round(max_val + step, 2)))

        return invalid[:5]  # Return up to 5 examples

    def should_derive_rules(self, stats: ProfilingResult) -> bool:
        """
        Check if rules should be derived for this attribute based on filtering criteria.

        Filters:
        1. Missing percentage must be <= 70%
        2. Cardinality must meet threshold for the datatype

        Args:
            stats: ProfilingResult for the attribute

        Returns:
            True if rules should be derived
        """
        # Check missing percentage
        if should_skip_for_missing(stats.missing_percentage):
            return False

        # Check cardinality threshold
        if not meets_cardinality_threshold(stats.datatype, stats.cardinality_float):
            return False

        return True

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
            "should_derive_rules": self.should_derive_rules(stats),
        }

        # Add numeric range info if applicable
        if stats.datatype == "Numeric" and stats.range:
            numeric_range = stats.get_numeric_range()
            if numeric_range:
                analysis["min_value"] = numeric_range[0]
                analysis["max_value"] = numeric_range[1]

                # Detect numeric patterns for generalized rule generation
                pattern = self.detect_numeric_pattern(stats.top_values, numeric_range)
                if pattern:
                    analysis["numeric_pattern"] = pattern

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