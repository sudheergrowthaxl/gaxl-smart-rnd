"""Pydantic models for Data Quality Rules."""

from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


class RuleCategory(str, Enum):
    """DQ Rule dimension categories."""
    # DAMA Framework 6 Core Dimensions
    COMPLETENESS = "Completeness"
    VALIDITY = "Validity"
    ACCURACY = "Accuracy"
    CONSISTENCY = "Consistency"
    UNIQUENESS = "Uniqueness"
    TIMELINESS = "Timeliness"
    # Additional Rule Categories (Beyond DAMA Core)
    NORMALIZATION = "Normalization"
    COMPUTATION = "Computation"
    DEFAULT = "Default"


class RuleType(str, Enum):
    """Specific rule types within categories."""
    # Completeness
    NOT_NULL = "NOT_NULL"
    NOT_EMPTY = "NOT_EMPTY"
    NOT_WHITESPACE = "NOT_WHITESPACE"
    CONDITIONAL_REQUIRED = "CONDITIONAL_REQUIRED"

    # Validity
    DATA_TYPE = "DATA_TYPE"
    FORMAT_PATTERN = "FORMAT_PATTERN"
    VALUE_SET = "VALUE_SET"
    RANGE = "RANGE"
    LENGTH = "LENGTH"
    SEMANTIC_TYPE = "SEMANTIC_TYPE"

    # Accuracy
    PRECISION = "PRECISION"
    STATISTICAL_BOUNDS = "STATISTICAL_BOUNDS"
    CROSS_FIELD_VALIDATION = "CROSS_FIELD_VALIDATION"

    # Consistency
    FORMAT_CONSISTENCY = "FORMAT_CONSISTENCY"
    CASE_CONSISTENCY = "CASE_CONSISTENCY"
    REFERENTIAL_INTEGRITY = "REFERENTIAL_INTEGRITY"
    BUSINESS_RULE = "BUSINESS_RULE"

    # Uniqueness
    PRIMARY_KEY = "PRIMARY_KEY"
    COMPOSITE_KEY = "COMPOSITE_KEY"
    NEAR_DUPLICATE = "NEAR_DUPLICATE"

    # Timeliness
    DATE_RANGE = "DATE_RANGE"
    DATE_SEQUENCE = "DATE_SEQUENCE"
    FRESHNESS = "FRESHNESS"

    # Normalization (Transform to standard formats)
    NORMALIZATION = "NORMALIZATION"
    VALUE_STANDARDIZATION = "VALUE_STANDARDIZATION"
    UNIT_CONVERSION = "UNIT_CONVERSION"
    FORMAT_STANDARDIZATION = "FORMAT_STANDARDIZATION"

    # Computation (Cross-field validation and conditional logic)
    COMPUTATION = "COMPUTATION"
    CONDITIONAL_VALIDATION = "CONDITIONAL_VALIDATION"
    DERIVED_VALUE = "DERIVED_VALUE"
    CROSS_ATTRIBUTE_CHECK = "CROSS_ATTRIBUTE_CHECK"

    # Default (Set default values based on conditions)
    DEFAULT_VALUE = "DEFAULT_VALUE"
    CONDITIONAL_DEFAULT = "CONDITIONAL_DEFAULT"
    FALLBACK_VALUE = "FALLBACK_VALUE"




class DQRule(BaseModel):
    """Data Quality Rule following the XML schema specification."""

    
    attribute_name: str = Field(
        ...,
        description="Name of the attribute this rule applies to"
    )
    rule_category: str = Field(
        ...,
        description="DQ dimension category"
    )
    rule_type: str = Field(
        ...,
        description="Specific rule type within category"
    )
    rule_expression: str = Field(
        ...,
        description="Implementable rule logic"
    )
    rule_expression_sql: str = Field(
        ...,
        description="SQL implementation of the rule"
    )
    rule_expression_python: str = Field(
        ...,
        description="Python/pandas implementation"
    )
  
    description: str = Field(
        ...,
        description="Business-friendly rule description"
    )
  
    derived_from: str = Field(
        ...,
        description="Profiling statistic that led to this rule"
    )
    confidence_score: float = Field(
        ...,
        ge=0,
        le=1,
        description="Confidence in the derived rule (0.0 to 1.0)"
    )
    support: float = Field(
        default=0.0,
        ge=0,
        le=1,
        description="Proportion of data this rule applies to (0.0-1.0)"
    )
    confidence: float = Field(
        default=0.0,
        ge=0,
        le=1,
        description="Proportion of applicable data satisfying the rule (0.0-1.0)"
    )
    sample_valid_values: List[str] = Field(
        default_factory=list,
        description="Example values that pass the rule"
    )
    sample_invalid_values: List[str] = Field(
        default_factory=list,
        description="Example values that would fail the rule"
    )

   

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Note: Excludes rule_id, severity, and threshold_percent from output.
        """
        return {
            "attribute_name": self.attribute_name,
            "rule_category": self.rule_category,
            "rule_type": self.rule_type,
            "rule_expression": self.rule_expression,
            "rule_expression_sql": self.rule_expression_sql,
            "rule_expression_python": self.rule_expression_python,
            "description": self.description,
            "derived_from": self.derived_from,
            "confidence_score": self.confidence_score,
            "support": self.support,
            "confidence": self.confidence,
            "sample_valid_values": self.sample_valid_values,
            "sample_invalid_values": self.sample_invalid_values,
        }

    @property
    def unique_key(self) -> str:
        """Generate a unique key for this rule based on attribute, category, and type."""
        return f"{self.attribute_name}_{self.rule_category}_{self.rule_type}"


class DQRuleSet(BaseModel):
    """Collection of DQ rules for a dataset."""

    dataset_name: str = Field(
        ...,
        description="Name of the dataset being analyzed"
    )
    parent_class: str = Field(
        default="Unknown",
        description="Parent class/category derived from the data"
    )
    total_records: int = Field(
        ...,
        description="Total number of records in the dataset"
    )
    generated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Timestamp when rules were generated"
    )
    source_profiling: str = Field(
        ...,
        description="Path to source profiling data"
    )
    rules: List[DQRule] = Field(
        default_factory=list,
        description="List of derived DQ rules"
    )
    summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Summary statistics for the ruleset"
    )

    def add_rule(self, rule: DQRule) -> None:
        """Add a rule to the ruleset."""
        self.rules.append(rule)

    def get_rules_by_category(self, category: str) -> List[DQRule]:
        """Get all rules for a specific category."""
        return [r for r in self.rules if r.rule_category == category]

    def get_rules_by_attribute(self, attribute: str) -> List[DQRule]:
        """Get all rules for a specific attribute."""
        return [r for r in self.rules if r.attribute_name == attribute]

    def generate_summary(self) -> Dict[str, Any]:
        """Generate summary statistics for the ruleset."""
        # DAMA Framework 6 Core + Additional Categories
        categories = [
            "Completeness", "Validity", "Accuracy",
            "Consistency", "Uniqueness", "Timeliness",
            "Normalization", "Computation", "Default"
        ]

        self.summary = {
            "total_rules": len(self.rules),
            "rules_by_category": {
                cat: len(self.get_rules_by_category(cat))
                for cat in categories
            },
            "attributes_covered": list(set(r.attribute_name for r in self.rules)),
            "avg_confidence_score": (
                sum(r.confidence_score for r in self.rules) / len(self.rules)
                if self.rules else 0
            ),
        }
        return self.summary

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        if not self.summary:
            self.generate_summary()
        return {
            "dataset_name": self.dataset_name,
            "parent_class": self.parent_class,
            "total_records": self.total_records,
            "generated_at": self.generated_at,
            "source_profiling": self.source_profiling,
            "rules": [r.to_dict() for r in self.rules],
            "summary": self.summary,
        }
