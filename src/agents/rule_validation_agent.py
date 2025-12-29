"""RuleValidationAgent - Validates derived rules against sample data."""

import re
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd

from ..models.dq_rule import DQRule
from ..models.agent_state import ValidationResult


class RuleValidationAgent:
    """
    Agent that validates derived rules against sample data.

    This agent:
    - Takes derived DQ rules and sample data
    - Executes Python validation expressions
    - Calculates pass/fail rates
    - Suggests threshold adjustments based on actual data
    """

    def __init__(self, sample_data: pd.DataFrame):
        """
        Initialize the RuleValidationAgent.

        Args:
            sample_data: DataFrame containing sample data for validation
        """
        self.sample_data = sample_data

    def validate_rule(self, rule: DQRule) -> ValidationResult:
        """
        Validate a single rule against the sample data.

        Args:
            rule: DQRule to validate

        Returns:
            ValidationResult with pass/fail counts and sample failures
        """
        try:
            # Execute Python expression
            failures = self._execute_python_rule(rule)

            # Handle case where attribute doesn't exist
            if failures is None:
                return ValidationResult(
                    rule_id=rule.rule_id,
                    pass_count=len(self.sample_data),
                    fail_count=0,
                    pass_rate=100.0,
                    sample_failures=[{"note": f"Attribute '{rule.attribute_name}' not found in sample data"}],
                )

            total_records = len(self.sample_data)
            fail_count = len(failures)
            pass_count = total_records - fail_count
            pass_rate = (pass_count / total_records * 100) if total_records > 0 else 0

            # Get sample of failing records (limit columns for readability)
            if len(failures) > 0:
                sample_cols = [rule.attribute_name] if rule.attribute_name in failures.columns else []
                if sample_cols:
                    sample_failures = failures[sample_cols].head(5).to_dict('records')
                else:
                    sample_failures = failures.head(5).to_dict('records')
            else:
                sample_failures = []

            return ValidationResult(
                rule_id=rule.rule_id,
                pass_count=pass_count,
                fail_count=fail_count,
                pass_rate=round(pass_rate, 2),
                sample_failures=sample_failures,
            )

        except Exception as e:
            # Return error result
            return ValidationResult(
                rule_id=rule.rule_id,
                pass_count=0,
                fail_count=0,
                pass_rate=0,
                sample_failures=[{"error": str(e)}],
            )

    def _execute_python_rule(self, rule: DQRule) -> Optional[pd.DataFrame]:
        """
        Execute the Python validation expression and return failing records.

        Args:
            rule: DQRule containing the validation expression

        Returns:
            DataFrame of records that failed validation, or None if attribute not found
        """
        df = self.sample_data.copy()
        attr = rule.attribute_name

        # Handle attribute not in dataframe
        if attr not in df.columns:
            return None

        # Execute based on rule type
        try:
            if rule.rule_type == "NOT_NULL":
                return df[df[attr].isna()]

            elif rule.rule_type == "NOT_EMPTY":
                return df[df[attr].isna() | (df[attr].astype(str).str.strip() == '')]

            elif rule.rule_type == "VALUE_SET":
                valid_values = self._extract_value_set(rule)
                if valid_values:
                    return df[~df[attr].isin(valid_values) & df[attr].notna()]
                return pd.DataFrame()

            elif rule.rule_type == "RANGE":
                min_val, max_val = self._extract_range(rule)
                if min_val is not None and max_val is not None:
                    numeric_col = pd.to_numeric(df[attr], errors='coerce')
                    return df[(numeric_col < min_val) | (numeric_col > max_val)]
                return pd.DataFrame()

            elif rule.rule_type == "PRIMARY_KEY":
                return df[df.duplicated(subset=[attr], keep=False)]

            elif rule.rule_type == "FORMAT_PATTERN":
                pattern = self._extract_pattern(rule)
                if pattern:
                    try:
                        return df[~df[attr].astype(str).str.match(pattern, na=False)]
                    except re.error:
                        return pd.DataFrame()
                return pd.DataFrame()

            elif rule.rule_type == "LENGTH":
                min_len, max_len = self._extract_length_bounds(rule)
                str_len = df[attr].astype(str).str.len()
                mask = pd.Series([False] * len(df))
                if min_len is not None:
                    mask |= (str_len < min_len)
                if max_len is not None:
                    mask |= (str_len > max_len)
                return df[mask & df[attr].notna()]

            elif rule.rule_type == "DATA_TYPE":
                # Check if values can be converted to expected type
                expected_type = self._extract_expected_type(rule)
                if expected_type == "numeric":
                    numeric_col = pd.to_numeric(df[attr], errors='coerce')
                    return df[numeric_col.isna() & df[attr].notna()]
                return pd.DataFrame()

            else:
                # For other rule types, try to execute the expression directly
                try:
                    # Create a safe evaluation context
                    local_vars = {"df": df, "pd": pd}
                    result = eval(rule.rule_expression_python, {"__builtins__": {}}, local_vars)
                    return result if isinstance(result, pd.DataFrame) else pd.DataFrame()
                except Exception:
                    return pd.DataFrame()

        except Exception as e:
            print(f"Error executing rule {rule.rule_id}: {e}")
            return pd.DataFrame()

    def _extract_value_set(self, rule: DQRule) -> List[Any]:
        """Extract valid values from rule expression or sample_valid_values."""
        if rule.sample_valid_values:
            return rule.sample_valid_values

        # Try to parse from expression
        match = re.search(r'IN\s*\(([^)]+)\)', rule.rule_expression, re.IGNORECASE)
        if match:
            values_str = match.group(1)
            # Parse quoted values
            values = re.findall(r"'([^']*)'|\"([^\"]*)\"|(\d+)", values_str)
            return [v[0] or v[1] or v[2] for v in values if any(v)]

        return []

    def _extract_range(self, rule: DQRule) -> Tuple[Optional[float], Optional[float]]:
        """Extract min/max range from rule expression."""
        # Try BETWEEN pattern
        match = re.search(
            r'BETWEEN\s+(\d+\.?\d*)\s+AND\s+(\d+\.?\d*)',
            rule.rule_expression,
            re.IGNORECASE
        )
        if match:
            return float(match.group(1)), float(match.group(2))

        # Try comparison pattern
        min_match = re.search(r'>=?\s*(\d+\.?\d*)', rule.rule_expression)
        max_match = re.search(r'<=?\s*(\d+\.?\d*)', rule.rule_expression)

        min_val = float(min_match.group(1)) if min_match else None
        max_val = float(max_match.group(1)) if max_match else None

        return min_val, max_val

    def _extract_pattern(self, rule: DQRule) -> Optional[str]:
        """Extract regex pattern from rule expression."""
        # Try MATCHES/REGEXP pattern
        match = re.search(r"(?:MATCHES|REGEXP)\s*['\"]([^'\"]+)['\"]", rule.rule_expression, re.IGNORECASE)
        if match:
            return match.group(1)

        # Try .str.match pattern from Python expression
        match = re.search(r"\.str\.match\(r?['\"]([^'\"]+)['\"]", rule.rule_expression_python)
        if match:
            return match.group(1)

        return None

    def _extract_length_bounds(self, rule: DQRule) -> Tuple[Optional[int], Optional[int]]:
        """Extract min/max length from rule expression."""
        match = re.search(
            r'LENGTH.*?BETWEEN\s+(\d+)\s+AND\s+(\d+)',
            rule.rule_expression,
            re.IGNORECASE
        )
        if match:
            return int(match.group(1)), int(match.group(2))

        min_match = re.search(r'LENGTH.*?>=?\s*(\d+)', rule.rule_expression, re.IGNORECASE)
        max_match = re.search(r'LENGTH.*?<=?\s*(\d+)', rule.rule_expression, re.IGNORECASE)

        min_len = int(min_match.group(1)) if min_match else None
        max_len = int(max_match.group(1)) if max_match else None

        return min_len, max_len

    def _extract_expected_type(self, rule: DQRule) -> str:
        """Extract expected data type from rule expression."""
        if 'numeric' in rule.rule_expression.lower() or 'number' in rule.rule_expression.lower():
            return 'numeric'
        if 'date' in rule.rule_expression.lower():
            return 'date'
        return 'string'

    def validate_all_rules(self, rules: List[DQRule]) -> List[ValidationResult]:
        """
        Validate all rules and return results.

        Args:
            rules: List of DQRule objects to validate

        Returns:
            List of ValidationResult objects
        """
        results = []
        for rule in rules:
            result = self.validate_rule(rule)
            results.append(result)
        return results

    def suggest_threshold_adjustment(
        self,
        rule: DQRule,
        validation_result: ValidationResult,
    ) -> float:
        """
        Suggest adjusted threshold based on validation results.

        Args:
            rule: Original DQRule
            validation_result: Validation results

        Returns:
            Suggested threshold percentage
        """
        actual_fail_rate = 100 - validation_result.pass_rate
        current_threshold = rule.threshold_percent

        # If actual failures exceed threshold significantly, adjust
        if actual_fail_rate > current_threshold * 1.5:
            # Suggest a more realistic threshold (10% buffer above actual)
            suggested = round(actual_fail_rate * 1.1, 1)
            return min(suggested, 100)

        # If failures are much lower than threshold, tighten it
        if actual_fail_rate < current_threshold * 0.5 and actual_fail_rate > 0:
            suggested = round(actual_fail_rate * 1.5, 1)
            return max(suggested, 0.1)

        return current_threshold

    def refine_rules(
        self,
        rules: List[DQRule],
        validation_results: Dict[str, ValidationResult],
    ) -> List[DQRule]:
        """
        Refine rules based on validation results.

        Args:
            rules: List of DQRule objects
            validation_results: Dictionary mapping rule_id to ValidationResult

        Returns:
            List of refined DQRule objects
        """
        refined_rules = []

        for rule in rules:
            if rule.rule_id in validation_results:
                result = validation_results[rule.rule_id]

                # Adjust threshold if needed
                new_threshold = self.suggest_threshold_adjustment(rule, result)
                if new_threshold != rule.threshold_percent:
                    # Create new rule with adjusted threshold
                    rule_dict = rule.to_dict()
                    rule_dict['threshold_percent'] = new_threshold
                    rule_dict['derived_from'] += f" (threshold adjusted from {rule.threshold_percent}%)"
                    refined_rules.append(DQRule(**rule_dict))
                else:
                    refined_rules.append(rule)
            else:
                refined_rules.append(rule)

        return refined_rules
