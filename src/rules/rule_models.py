"""Pydantic models for data quality rules."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RuleCategory(str, Enum):
    """Data quality rule categories."""

    COMPLETENESS = "COMPLETENESS"
    VALIDITY = "VALIDITY"
    CONSISTENCY = "CONSISTENCY"
    ACCURACY = "ACCURACY"
    UNIQUENESS = "UNIQUENESS"
    TIMELINESS = "TIMELINESS"


class RuleSubtype(str, Enum):
    """Rule subtypes within categories."""

    # Completeness
    MANDATORY_FIELD = "mandatory_field"
    CONDITIONAL_MANDATORY = "conditional_mandatory"
    THRESHOLD = "threshold"

    # Validity
    DATA_TYPE = "data_type"
    RANGE_CHECK = "range_check"
    ENUMERATION = "enumeration"
    FORMAT_PATTERN = "format_pattern"

    # Consistency
    CROSS_FIELD = "cross_field"
    REFERENTIAL_INTEGRITY = "referential_integrity"
    TEMPORAL = "temporal"

    # Accuracy
    PRECISION = "precision"
    TOLERANCE = "tolerance"
    OUTLIER_DETECTION = "outlier_detection"

    # Uniqueness
    PRIMARY_KEY = "primary_key"
    COMPOSITE_KEY = "composite_key"

    # Timeliness
    FRESHNESS = "freshness"
    DATE_VALIDITY = "date_validity"


class ValidationLogic(BaseModel):
    """Validation logic specification."""

    expression: str = Field(description="Validation expression or formula")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Parameters for the validation"
    )
    error_message: str = Field(description="Error message when validation fails")
    severity: str = Field(default="ERROR", description="ERROR, WARNING, or INFO")


class SourceEvidence(BaseModel):
    """Evidence from source documents."""

    source_type: str = Field(description="Type of source (crosstab, rag, profiling, wikipedia)")
    source_reference: str = Field(description="Reference to source document")
    excerpt: str = Field(description="Relevant excerpt from source")
    confidence: float = Field(ge=0, le=1, description="Confidence score")


class DataQualityRule(BaseModel):
    """A single data quality rule."""

    rule_id: str = Field(description="Unique rule identifier (e.g., DQR_001)")
    attribute: str = Field(description="Attribute this rule applies to")
    category: RuleCategory = Field(description="Rule category")
    subtype: RuleSubtype = Field(description="Rule subtype")
    description: str = Field(description="Human-readable rule description")
    validation_logic: ValidationLogic = Field(description="Validation logic specification")
    source_evidence: list[SourceEvidence] = Field(
        default_factory=list, description="Evidence supporting this rule"
    )
    business_impact: str = Field(default="", description="Business impact of violations")
    implementation_notes: str = Field(default="", description="Notes for implementation")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True


class AttributeMatchingReport(BaseModel):
    """Report on attribute matching results."""

    matched_attributes: list[dict[str, Any]] = Field(
        default_factory=list, description="Attributes matched between sources"
    )
    crosstab_only_attributes: list[str] = Field(
        default_factory=list, description="Attributes only in cross-tab"
    )
    rag_only_attributes: list[str] = Field(
        default_factory=list, description="Attributes only in RAG specs"
    )
    statistics: dict[str, Any] = Field(
        default_factory=dict, description="Matching statistics"
    )


class RuleSetMetadata(BaseModel):
    """Metadata for a rule set."""

    generated_at: datetime = Field(default_factory=datetime.utcnow)
    generator_version: str = Field(default="1.0.0")
    data_sources: list[str] = Field(default_factory=list)
    total_rules: int = Field(default=0)
    rules_by_category: dict[str, int] = Field(default_factory=dict)


class RuleSummary(BaseModel):
    """Summary statistics for generated rules."""

    total_rules: int = 0
    by_category: dict[str, int] = Field(default_factory=dict)
    by_attribute: dict[str, int] = Field(default_factory=dict)
    coverage_rate: float = 0.0


class RuleSet(BaseModel):
    """Complete set of data quality rules."""

    metadata: RuleSetMetadata = Field(default_factory=RuleSetMetadata)
    attribute_matching_report: AttributeMatchingReport = Field(
        default_factory=AttributeMatchingReport
    )
    rules: list[DataQualityRule] = Field(default_factory=list)
    summary: RuleSummary = Field(default_factory=RuleSummary)

    def add_rule(self, rule: DataQualityRule) -> None:
        """Add a rule to the set."""
        self.rules.append(rule)
        self._update_summary()

    def _update_summary(self) -> None:
        """Update summary statistics."""
        self.summary.total_rules = len(self.rules)

        # Count by category
        by_category: dict[str, int] = {}
        by_attribute: dict[str, int] = {}

        for rule in self.rules:
            cat = rule.category
            by_category[cat] = by_category.get(cat, 0) + 1

            attr = rule.attribute
            by_attribute[attr] = by_attribute.get(attr, 0) + 1

        self.summary.by_category = by_category
        self.summary.by_attribute = by_attribute

        # Update metadata
        self.metadata.total_rules = len(self.rules)
        self.metadata.rules_by_category = by_category

    def get_rules_for_attribute(self, attribute: str) -> list[DataQualityRule]:
        """Get all rules for a specific attribute."""
        return [r for r in self.rules if r.attribute == attribute]

    def get_rules_by_category(self, category: RuleCategory) -> list[DataQualityRule]:
        """Get all rules in a specific category."""
        return [r for r in self.rules if r.category == category]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON export."""
        return self.model_dump(mode="json")
