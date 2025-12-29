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
    range: Optional[List[Optional[float]]] = Field(
        default=None,
        description="Min and max values for numeric types"
    )
    imbalance: Optional[str] = Field(
        default=None,
        description="Imbalance indicator"
    )
    sparsity: Optional[str] = Field(
        default=None,
        description="Sparsity percentage"
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
    def from_profiling_dict(
        cls,
        attr_name: str,
        stats: Dict[str, Any]
    ) -> "ProfilingResult":
        """Create ProfilingResult from raw profiling dictionary."""
        return cls(
            attribute_name=attr_name,
            datatype=stats.get('datatype', 'Unknown'),
            missing_percentage=stats.get('missing_percentage', 0.0),
            cardinality=stats.get('cardinality', '0%'),
            top_values=stats.get('top_values', []),
            range=stats.get('range'),
            imbalance=stats.get('imbalance'),
            sparsity=stats.get('sparsity'),
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
