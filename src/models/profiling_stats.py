"""Pydantic models for profiling statistics."""

from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field


class TopValue(BaseModel):
    """Represents a top value with its count."""
    value: str
    count: int


class ProfilingResult(BaseModel):
    """Profiling statistics for a single attribute."""

    attribute_name: str = Field(
        ...,
        description="Name of the attribute"
    )
    datatype: str = Field(
        ...,
        description="Detected data type (Categorical, Numeric, Text, ID, Constant, Empty)"
    )
    missing_percentage: float = Field(
        default=0.0,
        ge=0,
        le=100,
        description="Percentage of missing values"
    )
    cardinality: str = Field(
        default="0%",
        description="Percentage of unique values"
    )
    top_values: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Most frequent values with counts"
    )
    distinct_values: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="All distinct values with counts (complete list from profiling)"
    )
    total_distinct_count: int = Field(
        default=0,
        description="Total number of distinct values"
    )
    range: Optional[List[Optional[float]]] = Field(
        default=None,
        description="Min and max values for numeric types"
    )
    imbalance: Optional[Union[str, Dict[str, Any]]] = Field(
        default=None,
        description="Imbalance indicator (string or dict)"
    )
    sparsity: Optional[str] = Field(
        default=None,
        description="Sparsity percentage"
    )
    outliers: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Outlier detection results"
    )

    @property
    def is_empty(self) -> bool:
        """Check if attribute is completely empty."""
        return self.datatype == "Empty" or self.missing_percentage >= 100

    @property
    def cardinality_float(self) -> float:
        """Get cardinality as a float percentage."""
        try:
            return float(self.cardinality.replace('%', ''))
        except (ValueError, AttributeError):
            return 0.0

    @property
    def is_high_cardinality(self) -> bool:
        """Check if attribute has high cardinality (>90%)."""
        return self.cardinality_float > 90

    @property
    def is_low_missing(self) -> bool:
        """Check if attribute has low missing percentage (<5%)."""
        return self.missing_percentage < 5

    @property
    def top_value(self) -> Optional[str]:
        """Get the most frequent value."""
        if self.top_values and len(self.top_values) > 0:
            return str(self.top_values[0].get('value', ''))
        return None

    @property
    def top_value_count(self) -> int:
        """Get the count of the most frequent value."""
        if self.top_values and len(self.top_values) > 0:
            return int(self.top_values[0].get('count', 0))
        return 0

    def get_value_list(self, limit: int = 10) -> List[str]:
        """Get list of top values."""
        return [str(tv.get('value', '')) for tv in self.top_values[:limit]]

    def get_numeric_range(self) -> Optional[tuple]:
        """Get min/max range for numeric attributes."""
        if self.range and len(self.range) == 2:
            min_val, max_val = self.range
            if min_val is not None and max_val is not None:
                return (min_val, max_val)
        return None

    @classmethod
    def _normalize_datatype(cls, stats: Dict[str, Any]) -> str:
        """
        Normalize datatype from profiling output to internal categories.

        Handles two profiling formats:
        - Old: datatype is already normalized (Categorical, Numeric, ID, etc.)
        - New: datatype is raw python type (string, integer, float, etc.)
              with semantic_type providing the category
        """
        # Prefer semantic_type if present (new profiling format)
        semantic_type = stats.get('semantic_type', '')
        raw_datatype = stats.get('datatype', 'Unknown')

        # If semantic_type is a known category, use it directly
        known_categories = {'Categorical', 'Numeric', 'Text', 'ID', 'Constant', 'Empty', 'Unknown'}
        if semantic_type in known_categories:
            return semantic_type

        # Map raw python datatypes to internal categories
        datatype_map = {
            'string': 'Categorical',
            'str': 'Categorical',
            'integer': 'Numeric',
            'int': 'Numeric',
            'float': 'Numeric',
            'decimal': 'Numeric',
            'number': 'Numeric',
            'boolean': 'Categorical',
            'bool': 'Categorical',
            'date': 'Text',
            'datetime': 'Text',
            'object': 'Categorical',
        }

        # Check if raw_datatype is already a known category
        if raw_datatype in known_categories:
            return raw_datatype

        return datatype_map.get(raw_datatype.lower(), 'Categorical')

    @classmethod
    def from_profiling_dict(
        cls,
        attr_name: str,
        stats: Dict[str, Any]
    ) -> "ProfilingResult":
        """Create ProfilingResult from raw profiling dictionary.

        Handles both old and new profiling JSON formats.
        When distinct_values is available, uses it as the primary value list
        (complete set) instead of the truncated top_values.
        """
        # Normalize datatype
        datatype = cls._normalize_datatype(stats)

        # Handle missing_percentage being 100% as Empty
        missing_pct = stats.get('missing_percentage', 0.0)
        if missing_pct >= 100:
            datatype = 'Empty'

        # Use distinct_values as primary source when available (complete list)
        # Fall back to top_values (truncated top N) if distinct_values is absent
        raw_distinct = stats.get('distinct_values') or []
        raw_top = stats.get('top_values', [])

        # If distinct_values has more data, use it as top_values for the system
        if len(raw_distinct) > len(raw_top):
            effective_top_values = raw_distinct
        else:
            effective_top_values = raw_top

        total_distinct = len(raw_distinct) if raw_distinct else len(raw_top)

        return cls(
            attribute_name=attr_name,
            datatype=datatype,
            missing_percentage=missing_pct,
            cardinality=stats.get('cardinality', '0%'),
            top_values=effective_top_values,
            distinct_values=raw_distinct,
            total_distinct_count=total_distinct,
            range=stats.get('range'),
            imbalance=stats.get('imbalance'),
            sparsity=stats.get('sparsity'),
            outliers=stats.get('outliers'),
        )


class DatasetProfile(BaseModel):
    """Complete profiling results for a dataset."""

    attributes: Dict[str, ProfilingResult] = Field(
        default_factory=dict,
        description="Profiling results keyed by attribute name"
    )
    total_attributes: int = Field(
        default=0,
        description="Total number of attributes"
    )
    non_empty_attributes: int = Field(
        default=0,
        description="Number of non-empty attributes"
    )

    def add_attribute(self, result: ProfilingResult) -> None:
        """Add a profiling result for an attribute."""
        self.attributes[result.attribute_name] = result
        self.total_attributes = len(self.attributes)
        self.non_empty_attributes = len([
            r for r in self.attributes.values() if not r.is_empty
        ])

    def get_attribute(self, name: str) -> Optional[ProfilingResult]:
        """Get profiling result for a specific attribute."""
        return self.attributes.get(name)

    def get_non_empty_attributes(self) -> List[ProfilingResult]:
        """Get all non-empty attributes."""
        return [r for r in self.attributes.values() if not r.is_empty]

    def get_low_missing_attributes(
        self,
        threshold: float = 50.0
    ) -> List[ProfilingResult]:
        """Get attributes with missing percentage below threshold."""
        return [
            r for r in self.attributes.values()
            if r.missing_percentage < threshold
        ]

    @classmethod
    def from_json(cls, profiling_data: Dict[str, Any]) -> "DatasetProfile":
        """Create DatasetProfile from raw JSON profiling data."""
        profile = cls()
        for attr_name, stats in profiling_data.items():
            result = ProfilingResult.from_profiling_dict(attr_name, stats)
            profile.add_attribute(result)
        return profile
