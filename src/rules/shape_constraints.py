"""
Shape Constraint Engine for deterministic rule derivation.

This module implements a descriptive + industry-standard approach:
- COMPLETENESS rules: Descriptive (based on actual profiling data patterns)
- VALIDITY rules: Prescriptive (based on Wikipedia/industry standards)
"""

import logging
import re
from datetime import datetime
from typing import Any, Optional

from src.rules.rule_models import (
    DataQualityRule,
    RuleCategory,
    RuleSubtype,
    SourceEvidence,
    ValidationLogic,
)

logger = logging.getLogger(__name__)


class ShapeConstraintEngine:
    """
    Deterministic rule derivation based on shape constraints.

    Implements two approaches:
    1. COMPLETENESS: Descriptive - rules based on actual data patterns
    2. VALIDITY: Prescriptive - rules based on industry standards
    """

    def __init__(
        self,
        config: dict[str, Any],
        wikipedia_scraper: Optional[Any] = None,
    ):
        """
        Initialize the shape constraint engine.

        Args:
            config: Configuration dictionary with shape_constraints section.
            wikipedia_scraper: Optional WikipediaScraper instance for fetching standards.
        """
        self.config = config.get("shape_constraints", {})
        self.completeness_config = self.config.get("completeness", {})
        self.validity_config = self.config.get("validity", {})
        self.wikipedia_config = self.config.get("wikipedia", {})
        self.standard_values = self.config.get("standard_values", {})
        self.severity_config = self.config.get("severity", {})

        self.wikipedia_scraper = wikipedia_scraper
        self._rule_counter = 0

        # Thresholds for completeness rules
        self.mandatory_threshold = self.completeness_config.get("mandatory_threshold", 5.0)
        self.expected_threshold = self.completeness_config.get("expected_threshold", 20.0)
        self.conditional_threshold = self.completeness_config.get("conditional_threshold", 70.0)
        self.optional_above = self.completeness_config.get("optional_above", 70.0)
        self.dead_field_threshold = self.completeness_config.get("dead_field_threshold", 100.0)

        logger.info(
            f"ShapeConstraintEngine initialized with thresholds: "
            f"mandatory<{self.mandatory_threshold}%, expected<{self.expected_threshold}%, "
            f"conditional<{self.conditional_threshold}%, optional>{self.optional_above}%"
        )

    def _generate_rule_id(self) -> str:
        """Generate a unique rule ID."""
        self._rule_counter += 1
        return f"DQR_{self._rule_counter:03d}"

    def derive_completeness_rule(
        self,
        attribute: str,
        stats: dict[str, Any],
    ) -> Optional[DataQualityRule]:
        """
        Derive COMPLETENESS rule using DESCRIPTIVE approach.

        Only creates mandatory rules for fields with LOW missing %.
        Fields with >70% missing get NO completeness rule (optional).

        Args:
            attribute: Attribute name.
            stats: Profiling statistics for the attribute.

        Returns:
            DataQualityRule or None if attribute is optional.
        """
        if not stats or not isinstance(stats, dict):
            logger.debug(f"No stats for {attribute}, skipping completeness rule")
            return None

        missing_pct = stats.get("missing_percentage", 0)

        # Handle string percentages
        if isinstance(missing_pct, str):
            try:
                missing_pct = float(missing_pct.replace("%", "").strip())
            except ValueError:
                missing_pct = 0

        # 100% missing -> Dead field (flag for removal)
        if missing_pct >= self.dead_field_threshold:
            logger.info(f"{attribute}: 100% missing - flagged as dead field (no rule)")
            return self._create_dead_field_flag(attribute, missing_pct)

        # > 70% missing -> No completeness rule (field is optional)
        if missing_pct > self.optional_above:
            logger.info(
                f"{attribute}: {missing_pct}% missing > {self.optional_above}% threshold - "
                f"NO completeness rule (optional field)"
            )
            return None

        # < 5% missing -> Mandatory field
        if missing_pct < self.mandatory_threshold:
            return self._create_completeness_rule(
                attribute=attribute,
                missing_pct=missing_pct,
                subtype=RuleSubtype.MANDATORY_FIELD,
                severity=self.severity_config.get("mandatory", "ERROR"),
                description=f"{attribute} is mandatory (only {missing_pct:.1f}% missing in data)",
            )

        # 5-20% missing -> Expected field
        elif missing_pct < self.expected_threshold:
            return self._create_completeness_rule(
                attribute=attribute,
                missing_pct=missing_pct,
                subtype=RuleSubtype.THRESHOLD,
                severity=self.severity_config.get("expected", "WARNING"),
                description=f"{attribute} is expected ({missing_pct:.1f}% missing - threshold check)",
            )

        # 20-70% missing -> Conditional
        else:
            return self._create_completeness_rule(
                attribute=attribute,
                missing_pct=missing_pct,
                subtype=RuleSubtype.CONDITIONAL_MANDATORY,
                severity=self.severity_config.get("conditional", "INFO"),
                description=f"{attribute} is conditionally required ({missing_pct:.1f}% missing)",
            )

    def _create_completeness_rule(
        self,
        attribute: str,
        missing_pct: float,
        subtype: RuleSubtype,
        severity: str,
        description: str,
    ) -> DataQualityRule:
        """Create a completeness rule."""
        return DataQualityRule(
            rule_id=self._generate_rule_id(),
            attribute=attribute,
            category=RuleCategory.COMPLETENESS,
            subtype=subtype,
            description=description,
            validation_logic=ValidationLogic(
                expression=f"value is not None and value != ''",
                parameters={
                    "missing_percentage": missing_pct,
                    "threshold_type": subtype.value,
                },
                error_message=f"{attribute} is required but missing",
                severity=severity,
            ),
            source_evidence=[
                SourceEvidence(
                    source_type="profiling",
                    source_reference="Python Profiling Statistics",
                    excerpt=f"Missing percentage: {missing_pct:.1f}%",
                    confidence=0.95,
                )
            ],
            business_impact=self._get_completeness_impact(subtype),
            implementation_notes=f"Check for null/empty values. Current fill rate: {100 - missing_pct:.1f}%",
        )

    def _create_dead_field_flag(
        self,
        attribute: str,
        missing_pct: float,
    ) -> DataQualityRule:
        """Create a flag for dead fields (100% missing)."""
        return DataQualityRule(
            rule_id=self._generate_rule_id(),
            attribute=attribute,
            category=RuleCategory.COMPLETENESS,
            subtype=RuleSubtype.THRESHOLD,
            description=f"DEAD FIELD: {attribute} has {missing_pct:.1f}% missing - consider removing from schema",
            validation_logic=ValidationLogic(
                expression="SCHEMA_REVIEW_REQUIRED",
                parameters={"missing_percentage": missing_pct, "status": "dead_field"},
                error_message=f"{attribute} is never populated - review schema",
                severity="INFO",
            ),
            source_evidence=[
                SourceEvidence(
                    source_type="profiling",
                    source_reference="Python Profiling Statistics",
                    excerpt=f"Field is {missing_pct:.1f}% empty - never populated",
                    confidence=1.0,
                )
            ],
            business_impact="Field unused - consider removing to simplify data model",
            implementation_notes="Review with data stewards before removing from schema",
        )

    def _get_completeness_impact(self, subtype: RuleSubtype) -> str:
        """Get business impact description based on rule subtype."""
        impacts = {
            RuleSubtype.MANDATORY_FIELD: "Critical data missing - may cause process failures",
            RuleSubtype.THRESHOLD: "Expected data missing - may affect downstream analytics",
            RuleSubtype.CONDITIONAL_MANDATORY: "Optional data missing - limited impact",
        }
        return impacts.get(subtype, "Data quality issue")

    def derive_validity_rules(
        self,
        attribute: str,
        stats: dict[str, Any],
    ) -> list[DataQualityRule]:
        """
        Derive VALIDITY rules using Wikipedia industry standards.

        Falls back to profiling statistics if Wikipedia has no data.

        Args:
            attribute: Attribute name.
            stats: Profiling statistics for the attribute.

        Returns:
            List of DataQualityRule objects for validity checks.
        """
        rules = []

        # Normalize attribute name for lookup
        normalized_attr = self._normalize_attribute_name(attribute)

        # Try Wikipedia first for industry standards
        wiki_data = None
        if self.wikipedia_scraper and self.validity_config.get("scrape_wikipedia", True):
            wiki_data = self._get_wikipedia_standards(normalized_attr)

        if wiki_data and wiki_data.get("standard_values"):
            # Use Wikipedia standard values for enumeration
            rules.append(
                self._create_enumeration_rule(
                    attribute=attribute,
                    valid_values=wiki_data["standard_values"],
                    source="Wikipedia",
                    reference=wiki_data.get("reference_standard", ""),
                    source_url=wiki_data.get("source_url", ""),
                )
            )

        elif wiki_data and wiki_data.get("standard_range"):
            # Use Wikipedia standard range
            rules.append(
                self._create_range_rule(
                    attribute=attribute,
                    min_val=wiki_data["standard_range"]["min"],
                    max_val=wiki_data["standard_range"]["max"],
                    unit=wiki_data.get("unit", ""),
                    source="Wikipedia",
                    reference=wiki_data.get("reference_standard", ""),
                )
            )

        # Fall back to built-in standard values
        elif self.validity_config.get("fallback_to_profiling", True):
            standard_rule = self._create_rule_from_standard_values(attribute, normalized_attr)
            if standard_rule:
                rules.append(standard_rule)

        # If still no validity rule, try profiling statistics
        if not rules and stats:
            profiling_rules = self._create_rules_from_profiling(attribute, stats)
            rules.extend(profiling_rules)

        return rules

    def _normalize_attribute_name(self, attribute: str) -> str:
        """Normalize attribute name for lookup."""
        # Remove common prefixes
        normalized = attribute.lower()
        for prefix in ["zz_", "dr_", "xx_"]:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
                break

        # Convert spaces to underscores
        normalized = normalized.replace(" ", "_")
        return normalized

    def _get_wikipedia_standards(self, normalized_attr: str) -> Optional[dict[str, Any]]:
        """
        Get industry standards from Wikipedia for an attribute.

        Args:
            normalized_attr: Normalized attribute name.

        Returns:
            Dictionary with standard values/ranges or None.
        """
        if not self.wikipedia_scraper:
            return None

        # Check if we have a mapping for this attribute
        attr_mappings = self.wikipedia_config.get("attribute_mappings", {})

        # Try direct match first
        mapping = attr_mappings.get(normalized_attr)

        # Try partial match
        if not mapping:
            for key, value in attr_mappings.items():
                if key in normalized_attr or normalized_attr in key:
                    mapping = value
                    break

        if not mapping:
            return None

        # Fetch from Wikipedia using mapped terms
        search_terms = mapping.get("terms", [])
        if not search_terms:
            return None

        try:
            result = self.wikipedia_scraper.extract_standard_values(
                attribute=normalized_attr,
                search_terms=search_terms,
            )
            if result:
                result["expected_unit"] = mapping.get("expected_unit", "")
                result["reference_standard"] = mapping.get("standard_reference", "")
            return result
        except Exception as e:
            logger.debug(f"Wikipedia lookup failed for {normalized_attr}: {e}")
            return None

    def _create_rule_from_standard_values(
        self,
        attribute: str,
        normalized_attr: str,
    ) -> Optional[DataQualityRule]:
        """Create validity rule from built-in standard values."""
        # Determine which standard to use based on attribute name
        standard_key = None

        if "voltage" in normalized_attr:
            if "control" in normalized_attr or "coil" in normalized_attr:
                standard_key = "control_voltage"
            else:
                standard_key = "voltage"
        elif "current" in normalized_attr:
            standard_key = "current"
        elif "frequency" in normalized_attr:
            standard_key = "frequency"
        elif "ip" in normalized_attr and "rating" in normalized_attr:
            standard_key = "ip_rating"
        elif "temperature" in normalized_attr:
            standard_key = "temperature"
        elif "utilization" in normalized_attr or "category" in normalized_attr:
            standard_key = "utilization_category"
        elif "mechanical" in normalized_attr and "durability" in normalized_attr:
            standard_key = "mechanical_durability"
        elif "electrical" in normalized_attr and "durability" in normalized_attr:
            standard_key = "electrical_durability"

        if not standard_key:
            return None

        standard = self.standard_values.get(standard_key)
        if not standard:
            return None

        # Create enumeration rule if common_values exist
        if "common_values" in standard:
            return self._create_enumeration_rule(
                attribute=attribute,
                valid_values=standard["common_values"],
                source="IEC Standards",
                reference=f"Built-in standard values for {standard_key}",
                unit=standard.get("unit", ""),
            )

        # Create range rule if range exists
        if "range" in standard:
            return self._create_range_rule(
                attribute=attribute,
                min_val=standard["range"]["min"],
                max_val=standard["range"]["max"],
                unit=standard.get("unit", ""),
                source="IEC Standards",
                reference=f"Built-in standard range for {standard_key}",
            )

        # Create pattern rule if pattern exists
        if "pattern" in standard:
            return self._create_pattern_rule(
                attribute=attribute,
                pattern=standard["pattern"],
                source="IEC Standards",
                reference=f"Built-in pattern for {standard_key}",
            )

        return None

    def _create_rules_from_profiling(
        self,
        attribute: str,
        stats: dict[str, Any],
    ) -> list[DataQualityRule]:
        """Create validity rules from profiling statistics."""
        rules = []

        datatype = stats.get("datatype", "Unknown")

        # Range check for numeric types
        if datatype in ["Numeric", "Integer", "Float", "numeric", "integer", "float"]:
            range_val = stats.get("range")
            if range_val and isinstance(range_val, list) and len(range_val) == 2:
                min_val, max_val = range_val
                if min_val is not None and max_val is not None:
                    rules.append(
                        self._create_range_rule(
                            attribute=attribute,
                            min_val=min_val,
                            max_val=max_val,
                            source="Profiling Statistics",
                            reference="Observed data range",
                        )
                    )

        # Enumeration for categorical types
        elif datatype in ["Categorical", "String", "Text", "categorical", "string", "text"]:
            top_values = stats.get("top_values", [])
            cardinality = stats.get("cardinality", 0)

            # Convert cardinality to int if it's a string
            if isinstance(cardinality, str):
                try:
                    cardinality = int(cardinality)
                except ValueError:
                    cardinality = 0

            # Only create enumeration if low cardinality (<20 unique values)
            if top_values and cardinality and cardinality < 20:
                values = [
                    tv.get("value") for tv in top_values
                    if isinstance(tv, dict) and tv.get("value")
                ]
                if values:
                    rules.append(
                        self._create_enumeration_rule(
                            attribute=attribute,
                            valid_values=values,
                            source="Profiling Statistics",
                            reference="Observed values in data",
                        )
                    )

        # Data type rule
        if datatype and datatype not in ["Unknown", "Empty"]:
            rules.append(self._create_datatype_rule(attribute, datatype))

        return rules

    def _create_enumeration_rule(
        self,
        attribute: str,
        valid_values: list[Any],
        source: str,
        reference: str,
        source_url: str = "",
        unit: str = "",
    ) -> DataQualityRule:
        """Create an enumeration validity rule."""
        values_str = ", ".join(str(v) for v in valid_values[:10])
        if len(valid_values) > 10:
            values_str += f", ... ({len(valid_values)} total)"

        return DataQualityRule(
            rule_id=self._generate_rule_id(),
            attribute=attribute,
            category=RuleCategory.VALIDITY,
            subtype=RuleSubtype.ENUMERATION,
            description=f"{attribute} must be one of the standard values: {values_str}",
            validation_logic=ValidationLogic(
                expression=f"value in {valid_values}",
                parameters={
                    "valid_values": valid_values,
                    "unit": unit,
                    "standard_reference": reference,
                },
                error_message=f"{attribute} has invalid value. Must be one of: {values_str}",
                severity=self.severity_config.get("validity_violation", "ERROR"),
            ),
            source_evidence=[
                SourceEvidence(
                    source_type=source.lower().replace(" ", "_"),
                    source_reference=source_url if source_url else reference,
                    excerpt=f"Standard values: {values_str}",
                    confidence=0.9 if source == "Wikipedia" else 0.8,
                )
            ],
            business_impact="Non-standard values may cause compatibility or compliance issues",
            implementation_notes=f"Validate against allowed values list. Source: {source}",
        )

    def _create_range_rule(
        self,
        attribute: str,
        min_val: float,
        max_val: float,
        source: str,
        reference: str,
        unit: str = "",
    ) -> DataQualityRule:
        """Create a range check validity rule."""
        unit_str = f" {unit}" if unit else ""

        return DataQualityRule(
            rule_id=self._generate_rule_id(),
            attribute=attribute,
            category=RuleCategory.VALIDITY,
            subtype=RuleSubtype.RANGE_CHECK,
            description=f"{attribute} must be between {min_val}{unit_str} and {max_val}{unit_str}",
            validation_logic=ValidationLogic(
                expression=f"{min_val} <= value <= {max_val}",
                parameters={
                    "min": min_val,
                    "max": max_val,
                    "unit": unit,
                    "standard_reference": reference,
                },
                error_message=f"{attribute} out of range. Must be {min_val}-{max_val}{unit_str}",
                severity=self.severity_config.get("validity_violation", "ERROR"),
            ),
            source_evidence=[
                SourceEvidence(
                    source_type=source.lower().replace(" ", "_"),
                    source_reference=reference,
                    excerpt=f"Valid range: {min_val} to {max_val}{unit_str}",
                    confidence=0.9 if source == "Wikipedia" else 0.85,
                )
            ],
            business_impact="Values outside range may indicate data entry errors or equipment issues",
            implementation_notes=f"Numeric range validation. Source: {source}",
        )

    def _create_pattern_rule(
        self,
        attribute: str,
        pattern: str,
        source: str,
        reference: str,
    ) -> DataQualityRule:
        """Create a pattern/format validity rule."""
        return DataQualityRule(
            rule_id=self._generate_rule_id(),
            attribute=attribute,
            category=RuleCategory.VALIDITY,
            subtype=RuleSubtype.FORMAT_PATTERN,
            description=f"{attribute} must match pattern: {pattern}",
            validation_logic=ValidationLogic(
                expression=f"re.match(r'{pattern}', value)",
                parameters={"pattern": pattern, "standard_reference": reference},
                error_message=f"{attribute} does not match expected format: {pattern}",
                severity=self.severity_config.get("validity_violation", "ERROR"),
            ),
            source_evidence=[
                SourceEvidence(
                    source_type=source.lower().replace(" ", "_"),
                    source_reference=reference,
                    excerpt=f"Format pattern: {pattern}",
                    confidence=0.9,
                )
            ],
            business_impact="Invalid format may cause parsing errors in downstream systems",
            implementation_notes=f"Regex pattern validation. Source: {source}",
        )

    def _create_datatype_rule(
        self,
        attribute: str,
        datatype: str,
    ) -> DataQualityRule:
        """Create a data type validity rule."""
        type_map = {
            "Numeric": "number",
            "Integer": "integer",
            "Float": "float",
            "String": "string",
            "Text": "string",
            "Categorical": "string",
            "Date": "date",
            "Boolean": "boolean",
        }
        expected_type = type_map.get(datatype, datatype.lower())

        return DataQualityRule(
            rule_id=self._generate_rule_id(),
            attribute=attribute,
            category=RuleCategory.VALIDITY,
            subtype=RuleSubtype.DATA_TYPE,
            description=f"{attribute} must be of type {expected_type}",
            validation_logic=ValidationLogic(
                expression=f"isinstance(value, {expected_type})",
                parameters={"expected_type": expected_type, "profiled_type": datatype},
                error_message=f"{attribute} has incorrect data type. Expected: {expected_type}",
                severity="WARNING",
            ),
            source_evidence=[
                SourceEvidence(
                    source_type="profiling",
                    source_reference="Python Profiling Statistics",
                    excerpt=f"Observed data type: {datatype}",
                    confidence=0.9,
                )
            ],
            business_impact="Type mismatches may cause processing errors",
            implementation_notes="Type validation based on profiled data type",
        )

    def derive_all_rules(
        self,
        attribute: str,
        stats: dict[str, Any],
    ) -> list[DataQualityRule]:
        """
        Derive all applicable rules for an attribute.

        Args:
            attribute: Attribute name.
            stats: Profiling statistics for the attribute.

        Returns:
            List of all derived rules (completeness + validity).
        """
        rules = []

        # Completeness rule (descriptive)
        completeness_rule = self.derive_completeness_rule(attribute, stats)
        if completeness_rule:
            rules.append(completeness_rule)

        # Validity rules (prescriptive from standards + descriptive from profiling)
        validity_rules = self.derive_validity_rules(attribute, stats)
        rules.extend(validity_rules)

        return rules

    def reset_rule_counter(self) -> None:
        """Reset the rule counter (useful for batch processing)."""
        self._rule_counter = 0
