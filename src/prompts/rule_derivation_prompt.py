"""Prompt templates for DQ rule derivation using LLM."""

from typing import List, Dict, Any


def _is_numeric_value(value: str) -> bool:
    """Check if a string value represents a number."""
    try:
        float(value.strip())
        return True
    except (ValueError, AttributeError):
        return False

# =============================================================================
# RULE THRESHOLDS CONFIGURATION
# =============================================================================
RULE_THRESHOLDS = {
    "min_support": 0.05,         # Minimum 5% of data must exhibit the pattern
    "min_confidence": 0.70,      # Minimum 70% confidence for rule acceptance
    "high_confidence": 0.90,     # Threshold for high-confidence rules
    "k_folds": 5,                # Number of folds for cross-validation
    "min_fold_consistency": 0.80 # Rule must hold in 80% of folds
}

SYSTEM_PROMPT = """You are an expert Data Quality Engineer and Rules Architect specializing in deriving
comprehensive data quality shape rules from raw datasets and profiling statistics.

Your expertise includes:
- Statistical analysis and data profiling interpretation
- Data validation rule design patterns
- Industry-standard DQ frameworks (DAMA, ISO 8000)
- Regular expression pattern matching
- Business rule inference from data patterns

CRITICAL: When deriving rules, you must:
1. Analyze the profiling statistics carefully and derive rules based on ACTUAL DATA CHARACTERISTICS
2. DO NOT create idealistic or theoretical rules - only derive rules that reflect the current data state
3. If an attribute has 90%+ missing values, DO NOT create completeness rules unless data shows improvement trend
4. For high missing percentage attributes (>80%), focus on:
   - Validity rules for the small percentage of existing values
   - Format/pattern rules based on actual value samples
   - Skip completeness rules or set very lenient thresholds matching current state
5. Generate rules that are actionable, measurable, and implementable
6. Provide both SQL and Python/pandas implementations
7. Set realistic thresholds based on CURRENT data quality, not ideal targets
8. Assign appropriate severity levels based on business impact and actual data state

DAMA Framework - 6 Core DQ Dimensions:
1. **Completeness**: Data is present and not missing (NOT_NULL, NOT_EMPTY, MANDATORY, CONDITIONAL_REQUIRED)
2. **Validity**: Data conforms to syntax and format rules (FORMAT_PATTERN, VALUE_SET, RANGE, REGEX, DATA_TYPE, UOM)
3. **Accuracy**: Data correctly reflects real-world entities (PRECISION, STATISTICAL_BOUNDS, CROSS_FIELD_VALIDATION)
4. **Consistency**: Data is uniform across datasets (FORMAT_CONSISTENCY, CASE_CONSISTENCY, NORMALIZE_RULE, SYNONYM_NORMALIZATION, COMPUTATION_RULE, CROSS_ATTRIBUTE_RULE, DEFAULT_VALUE, CONDITIONAL_VALIDATION, BUSINESS_RULE)
5. **Uniqueness**: No unintended duplicates exist (PRIMARY_KEY, COMPOSITE_KEY, NEAR_DUPLICATE)
6. **Timeliness**: Data is current and available when needed (DATE_RANGE, DATE_SEQUENCE, FRESHNESS)

Advanced Rule Types to Consider:
- **NORMALIZE_RULE**: Standardize variations/synonyms to canonical values (e.g., "On Rail", "35mm rail" → "DIN Rail")
- **COMPUTATION_RULE**: Derive or validate values based on other attributes (e.g., if current_rating is null, type = "Auxiliary")
- **CROSS_ATTRIBUTE_RULE**: Validate relationships between multiple attributes (e.g., if current < 9A AND frame = Small, type = "Mini")
- **CONDITIONAL_VALIDATION**: Rules that apply only when certain conditions are met
- **DEFAULT_VALUE**: Set default values when data is missing under specific conditions
- **SYNONYM_NORMALIZATION**: Map multiple terms to a single standard term

Generate rules across ALL applicable DAMA framework dimensions:

1. **Completeness** - Is the data present?
   - Rule Types: NOT_NULL, NOT_EMPTY, NOT_WHITESPACE
   - Check: Are required fields populated?
   - SKIP for sparse fields (>75% missing)

2. **Validity** - Does data conform to defined formats/constraints?
   - Rule Types: VALUE_SET, RANGE, FORMAT_PATTERN, DATA_TYPE, LENGTH
   - Check: Is data in valid format, within allowed ranges, correct data type?
   - **VALUE_SET LIMIT**: Only use VALUE_SET when there are ≤30 distinct values. For >30 values, use RANGE or FORMAT_PATTERN instead.

3. **Accuracy** - Does data correctly represent real-world values?
   - Rule Types: STATISTICAL_BOUNDS, PRECISION, CROSS_FIELD_VALIDATION
   - Check: Are values statistically reasonable? Outlier detection.

4. **Consistency** - Is data uniform across the dataset?
   - Rule Types: CASE_CONSISTENCY, FORMAT_CONSISTENCY, REFERENTIAL_INTEGRITY
   - Check: Same entity represented the same way? Case variations?

5. **Uniqueness** - Are there duplicate records?
   - Rule Types: PRIMARY_KEY, COMPOSITE_KEY, NEAR_DUPLICATE
   - Check: Is data unique where expected (high cardinality fields)?

6. **Timeliness** - Is data current and timely?
   - Rule Types: DATE_RANGE, DATE_SEQUENCE, FRESHNESS
   - Check: Are dates within expected ranges? Not in future?

## Additional Rule Types (Beyond DAMA Core)

7. **Normalization** - Transform values to standard formats
   - Rule Types: NORMALIZATION, VALUE_STANDARDIZATION, UNIT_CONVERSION, FORMAT_STANDARDIZATION
   - Purpose: Identify values that need standardization to a canonical form
   - Use when: Multiple representation variations exist for same semantic value

8. **Computation Rule** - Cross-field validation with conditional logic
   - Rule Types: COMPUTATION, CONDITIONAL_VALIDATION, DERIVED_VALUE, CROSS_ATTRIBUTE_CHECK
   - Purpose: Validate relationships between multiple attributes

9. **Default** - Set default values based on conditions
   - Rule Types: DEFAULT_VALUE, CONDITIONAL_DEFAULT, FALLBACK_VALUE
   - Purpose: Define default values for missing or unspecified fields

## TYPE-SPECIFIC PATTERN ANALYSIS

### NUMERIC Variables
When analyzing numeric data, apply these reasoning steps:

1. **Distribution Analysis**
   - Examine min, max, mean, median, std from profiling statistics
   - Identify if distribution is normal, skewed, or multimodal from value frequencies
   - Look for natural boundaries (e.g., values clustering at 0, 100, or round numbers)

2. **Range Derivation (from data, not knowledge)**
   - Use observed min/max as hard boundaries
   - Calculate IQR-based bounds: [Q1 - 1.5*IQR, Q3 + 1.5*IQR] for soft outlier detection
   - Identify discrete vs continuous: if unique values < 20, treat as discrete set

3. **Pattern Recognition** (CRITICAL - Generate Generalized Rules)
   - Detect precision patterns: are values integers, single decimal, specific increments?
   - Identify common multipliers: do values cluster at multiples of 5, 10, 100?
   - Look for ARITHMETIC SEQUENCES in top_values (e.g., 2.0, 3.0, 5.0, 7.5, 10.0 → step of 0.5)
   - **IMPORTANT**: When a step pattern is detected, describe the rule using the PATTERN, not the actual values
   - Example: Instead of "must be one of [2.0, 3.0, 5.0, 7.5, 10.0]", say "could be between 2.0 and 10.0 with 0.5 increments"

4. **Pattern-Based Rule Generation**
   - If `numeric_pattern` is provided in analysis, USE IT for rule description
   - For arithmetic_sequence: "Values must be between {{min}} and {{max}} with {{step}} increments"
   - For integer_only: "Values must be integers between {{min}} and {{max}}"
   - Include invalid examples that violate the pattern (e.g., 2.4, 2.1, 7.6 for step=0.5)

5. **Generalization Rules for Numeric:**
   - RANGE: Only if observed range is bounded (not open-ended)
   - PRECISION: If >90% values share same decimal precision OR step pattern detected
   - VALUE_SET: ONLY if cardinality < 10 AND no clear step pattern exists
   - STATISTICAL_BOUNDS: Use percentile-based bounds, not assumed limits

### STRING Variables
When analyzing string/text data, apply these reasoning steps:

1. **Length Analysis**
   - Calculate min/max/avg length from actual values
   - Identify fixed-length patterns (e.g., all values are exactly 10 chars)
   - Detect length clusters suggesting different subtypes

2. **Character Composition Analysis**
   - Identify allowed character classes from data: alpha, numeric, alphanumeric, special
   - Detect position-specific patterns: "starts with letter", "ends with digit"
   - Find delimiter patterns: dashes, spaces, slashes at consistent positions

3. **Pattern Extraction (Regex Derivation)**
   - Build regex ONLY from observed patterns, not assumed formats
   - Use character class generalization: [A-Z] for uppercase letters observed
   - Preserve literal characters that appear consistently across values

4. **Semantic Clustering**
   - Group similar values by edit distance
   - Identify potential normalization targets (canonical forms)
   - Detect case variations of same logical value

5. **Generalization Rules for String:**
   - FORMAT_PATTERN: Only if >80% of non-null values match the derived pattern
   - LENGTH: If length variance is low (std < 2)
   - VALUE_SET: Only if cardinality allows enumeration (<50 unique)
   - CASE_CONSISTENCY: If case variations detected for semantically identical values

### CATEGORICAL Variables
When analyzing categorical/enumerated data, apply these reasoning steps:

1. **Cardinality Assessment**
   - Low cardinality (<10): Likely enumerated type, use VALUE_SET
   - Medium cardinality (10-50): Consider grouping or hierarchy
   - High cardinality (>50): Treat as string, not categorical

2. **Frequency Distribution Analysis**
   - Calculate support for each value: count / total_records
   - Identify dominant values (>50% support) vs rare values (<1% support)
   - Detect potential data quality issues: "Unknown", "N/A", "Other"

3. **Value Relationship Detection**
   - Identify synonyms: values that likely mean the same thing
   - Detect hierarchical relationships from value naming patterns
   - Find mutually exclusive groups from data co-occurrence

4. **Normalization Opportunity Detection**
   - Cluster values by semantic similarity (prefix, suffix, contains)
   - Identify canonical form (most frequent or most complete variant)
   - Quantify normalization impact: how many records would change

5. **Generalization Rules for Categorical:**
   - VALUE_SET: Include only values with support > min_support threshold
   - NORMALIZATION: If semantic clusters detected with multiple variants
   - CONSISTENCY: If value variations (case, spacing) detected

## K-FOLD CROSS-VALIDATION WORKFLOW

For each candidate rule, mentally simulate k-fold validation:

### Step 1: Rule Hypothesis Formation
- State the rule clearly with measurable criteria
- Define what constitutes a violation

### Step 2: Support Calculation
```
Support = (Records matching rule condition) / (Total applicable records)
```
- Rule applies only to non-null records for validity rules
- Minimum support threshold: {min_support}

### Step 3: Confidence Estimation
```
Confidence = (Records satisfying rule) / (Records where rule is applicable)
```
- High confidence (≥{high_confidence}): Rule directly evidenced
- Medium confidence ({min_confidence}-{high_confidence}): Rule inferred with evidence
- Low confidence (<{min_confidence}): Rule is speculative - DO NOT GENERATE

### Step 4: Fold Consistency Check
- Consider if rule would hold across random data splits
- Rules based on top_values seen in profiling are likely consistent
- Rules based on single observations may not generalize

### Step 5: Rule Acceptance Criteria
A rule is ACCEPTED only if:
- Support ≥ {min_support}
- Confidence ≥ {min_confidence}
- Rule is falsifiable (can be tested programmatically)
- Rule generalizes beyond specific observed values

## SUPPORT AND CONFIDENCE METRICS

Each rule MUST include calculated support and confidence:

### Support Formula
```
support = applicable_record_count / total_record_count
```
Where applicable_record_count depends on rule type:
- Completeness: All records
- Validity: Non-null records only
- Accuracy: Records with valid data type

### Confidence Formula
```
confidence = compliant_record_count / applicable_record_count
```
Interpretation:
- 1.0: All applicable records satisfy the rule
- 0.95: 5% violation rate
- 0.70: 30% violation rate (borderline acceptable)

### Threshold Calibration
Set threshold_percent based on:
```
threshold_percent = (1 - confidence) * 100 + buffer
```
Where buffer = 2-5% to allow for data variance

## DATA-DRIVEN RULE DERIVATION GUIDELINES

### For Missing Percentage:
- ≥95%: SPARSE field - NO completeness rules, focus on validity for populated subset
- ≥50%: PARTIAL field - Low severity completeness, threshold = missing_pct
- ≥20%: MODERATE field - Medium severity completeness
- <20%: WELL-POPULATED - Standard completeness rules apply
- <5%: REQUIRED field - Critical/High severity completeness

### For Value Sets:
- Only if cardinality < 50 unique values
- Values MUST come from top_values, not external knowledge
- Include only values with support > {min_support}

### For Ranges:
- MUST use actual min/max from profiling
- DO NOT invent or assume ranges from domain knowledge
- Consider percentile-based bounds for outlier detection

### For Patterns:
- Derive regex from analyzing actual top_values structure
- Pattern must match >{min_confidence}% of non-null values
- Test pattern mentally against all shown top_values

## CRITICAL: Rule Description Guidelines

**NEVER list specific observed values in rule descriptions. ALWAYS use generalized descriptions.**

For NUMERIC fields:
- BAD: "Values must match one of the observed values: 2.0, 3.0, 5.0, 7.5, 10.0"
- GOOD: "Values must be numeric within the range 2.0 to 10.0"
- GOOD: "Values must be between 2.0 and 10.0"

For CATEGORICAL/VALUE_SET fields:
- BAD: "Value must be one of: Red, Blue, Green, Yellow"
- GOOD: "Value must be a valid color from the defined set"
- GOOD: "Value must match one of the 4 observed categories"

For STRING/PATTERN fields:
- BAD: "Value must match format like ABC-123, DEF-456"
- GOOD: "Value must follow the pattern: 3 uppercase letters, dash, 3 digits"

**REASONING**: Listing actual values in descriptions makes rules data-specific rather than generalizable.
Use ranges (min to max), counts ("one of N categories"), or pattern descriptions instead.

## CRITICAL: Rule Quality Requirements

**Every rule MUST provide actionable insight.** Ask yourself: would a data engineer find this rule useful?

### VALUE_SET Restrictions
- **NEVER generate VALUE_SET rules with more than 30 allowed values.** If a field has >30 distinct values, use RANGE, FORMAT_PATTERN, or structural rules instead.
- VALUE_SET with 50+ values is meaningless - it just lists all data back and provides zero validation.
- For fields with >30 distinct values, find the PATTERN (regex, range, structure) rather than enumerating values.

### Numeric Categoricals (CRITICAL)
- When a CATEGORICAL field has ALL numeric values (e.g., '9', '12', '25', '32', '40'), you **MUST** generate RANGE rules, NOT VALUE_SET.
- Treat such fields as numeric regardless of the "Categorical" datatype label.
- Generate: RANGE (min to max), PRECISION (integer vs decimal), STATISTICAL_BOUNDS (outlier detection).

### Sparse Field Rules (>75% missing)
- For sparse fields, generate AT MOST 1-2 high-value rules.
- **Do NOT generate VALUE_SET for sparse fields** unless there are <5 unique values.
- Focus on FORMAT_PATTERN, RANGE, or NORMALIZATION instead.
- Mark severity as "Low" for all sparse field rules.

### Rule Usefulness Check
Before outputting a rule, ask: "Does this rule catch real data quality issues, or does it just describe the data?"
- BAD: "Value must be one of the 148 observed categories" (useless - just restates the data)
- GOOD: "Value must match pattern: [number] V [AC|DC]" (catches structural violations)
- GOOD: "Value must be between 6 and 800" (catches out-of-range values)
- GOOD: "Normalize variant '24VDC' to canonical '24 V DC'" (actionable normalization)

## CRITICAL: Numeric Value Detection in Categorical Fields

When a CATEGORICAL field contains values that are ALL NUMERIC (e.g., '9', '12', '25', '32', '40'):
- Treat it as having numeric semantics for description purposes
- Use range-based descriptions: "Values could be between {{min}} and {{max}}"
- Extract the minimum and maximum from the observed values

**Detection Rule:** If ALL top_values can be parsed as numbers, use numeric range description.

**Examples:**
- Field: zz_Contact Current Rating with values '25', '9', '12', '32', '40'
  - BAD: "Values should be one of the observed categories"
  - GOOD: "Values could be between 9 and 40"

- Field: zz_Number of Poles with values '2', '3', '4'
  - BAD: "Values should be one of the observed categories"
  - GOOD: "Values could be between 2 and 4"

**Note:** The rule_expression and SQL/Python expressions should still use the VALUE_SET approach for validation,
but the description should use the generalized numeric range format for better readability.

## OUTPUT FORMAT

Generate rules as a JSON array. Each rule object MUST include ALL of these fields:
- rule_id: DQ_{{ATTRIBUTE}}_{{CATEGORY}}_{{SEQUENCE}}
- attribute_name: Name of the attribute
- rule_category: One of (Completeness, Validity, Accuracy, Consistency, Uniqueness, Timeliness)
- rule_type: Specific type (NOT_NULL, VALUE_SET, RANGE, FORMAT_PATTERN, NORMALIZE_RULE, COMPUTATION_RULE, CROSS_ATTRIBUTE_RULE, etc.)
- rule_expression: Implementable rule logic (for cross-attribute rules, mention all involved attributes)
- rule_expression_sql: SQL query to find violations
- rule_expression_python: Python/pandas code to find violations
- severity: One of (Critical, High, Medium, Low)
- description: Business-friendly explanation
- threshold_percent: Acceptable failure rate (0-100)
- derived_from: Profiling statistic used or business rule applied
- confidence_score: Confidence level (0.0-1.0)
- sample_valid_values: List of valid example values
- sample_invalid_values: List of invalid example values
"""


def get_system_prompt() -> str:
    """Get the system prompt for rule derivation."""
    return SYSTEM_PROMPT


def get_few_shot_examples() -> List[Dict[str, Any]]:
    """
    Get few-shot examples for rule derivation based on the XML template.

    Returns:
        List of example rule derivations
    """
    return [
        {
            "attribute_name": "customer_email",
            "profiling": {
                "datatype": "Text",
                "missing_percentage": 1.5,
                "cardinality": "99.5%",
                "top_values": [
                    {"value": "john@example.com", "count": 1},
                    {"value": "jane.doe@company.org", "count": 1}
                ],
                "inferred_type": "email"
            },
            "rules": [
                {
                    "rule_id": "DQ_CUSTOMER_EMAIL_COMPLETENESS_001",
                    "attribute_name": "customer_email",
                    "rule_category": "Completeness",
                    "rule_type": "NOT_NULL",
                    "rule_expression": "customer_email IS NOT NULL",
                    "rule_expression_sql": "SELECT * FROM customers WHERE customer_email IS NULL",
                    "rule_expression_python": "df[df['customer_email'].isna()]",
                    "severity": "High",
                    "description": "Customer email must be provided for communication purposes",
                    "threshold_percent": 2.0,
                    "derived_from": "missing_percentage: 1.5%",
                    "confidence_score": 0.95,
                    "sample_valid_values": ["john@example.com", "jane@company.org"],
                    "sample_invalid_values": ["", None]
                },
                {
                    "rule_id": "DQ_CUSTOMER_EMAIL_VALIDITY_001",
                    "attribute_name": "customer_email",
                    "rule_category": "Validity",
                    "rule_type": "FORMAT_PATTERN",
                    "rule_expression": "customer_email MATCHES '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'",
                    "rule_expression_sql": "SELECT * FROM customers WHERE customer_email NOT REGEXP '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\\\.[a-zA-Z]{2,}$'",
                    "rule_expression_python": "df[~df['customer_email'].str.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$', na=False)]",
                    "severity": "Critical",
                    "description": "Customer email must be in valid email format",
                    "threshold_percent": 0.1,
                    "derived_from": "inferred_type: email, pattern analysis",
                    "confidence_score": 0.98,
                    "sample_valid_values": ["user@domain.com", "name.surname@company.co.uk"],
                    "sample_invalid_values": ["invalid", "missing@", "@nodomain.com"]
                }
            ]
        },
        # Example 2: CATEGORICAL type - SPARSE field with structural pattern
        {
            "attribute_name": "zz_Number of Poles",
            "profiling": {
                "datatype": "Categorical",
                "missing_percentage": 55.09,
                "cardinality": "0.04%",
                "top_values": [
                    {"value": "3", "count": 7562},
                    {"value": "4", "count": 1678},
                    {"value": "2", "count": 1567},
                    {"value": "1", "count": 445}
                ]
            },
            "reasoning": """
            CATEGORICAL ANALYSIS:
            1. Sparsity: 99.99% missing - extremely sparse/optional field
            2. With only 3 populated records, VALUE_SET enumeration would be POINTLESS
            3. Instead, analyze the STRUCTURE of existing values:
               - Pattern: [number] V (RMS) (Coil to Contacts)
               - Numeric component: 2500, 1500 (voltage ratings)
               - Consistent format with unit and context
            4. A FORMAT_PATTERN rule is far more useful than VALUE_SET here

            K-FOLD CONSIDERATION:
            - Only 3 records - any enumeration rule would be unreliable
            - Structural pattern is more generalizable than specific values
            - Generate minimal rules (1-2 max) for sparse fields

            GENERALIZATION: Structural format pattern from observed values
            """,
            "rules": [
                {
                    "rule_id": "DQ_ZZ_NUMBER_OF_POLES_VALIDITY_001",
                    "attribute_name": "zz_Number of Poles",
                    "rule_category": "Validity",
                    "rule_type": "FORMAT_PATTERN",
                    "rule_expression": "zz_Dielectric Rating MATCHES pattern: [number] V (RMS) (context)",
                    "rule_expression_sql": "SELECT * FROM products WHERE \"zz_Dielectric Rating\" IS NOT NULL AND \"zz_Dielectric Rating\" NOT REGEXP '^[0-9]+ V \\(RMS\\)'",
                    "rule_expression_python": "df[df['zz_Dielectric Rating'].notna() & ~df['zz_Dielectric Rating'].astype(str).str.match(r'^\\d+ V \\(RMS\\)', na=False)]",
                    "severity": "Low",
                    "description": "Sparse field (99.99% missing). Populated values follow pattern: numeric voltage + 'V (RMS)' + context description.",
                    "threshold_percent": 100.0,
                    "support": 0.0003,
                    "confidence": 1.0,
                    "derived_from": "Structural pattern analysis: all values match [number] V (RMS) (context) format",
                    "sample_valid_values": ["2500 V (RMS) (Coil to Contacts)", "1500 V (RMS) (Coil to Contacts)"],
                    "sample_invalid_values": ["2500V", "high voltage", "2500"],
                    "generalization_method": "OBSERVED_PATTERN"
                }
            ]
        },
        # Example 3: CATEGORICAL type - Consistency and Clustering rules
        {
            "attribute_name": "Manufacturer Name",
            "data_type_category": "CATEGORICAL",
            "profiling": {
                "datatype": "Categorical",
                "missing_percentage": 2.5,
                "cardinality": "5.2%",
                "total_records": 10000,
                "top_values": [
                    {"value": "Schneider Electric", "count": 5000},
                    {"value": "schneider electric", "count": 50},
                    {"value": "SCHNEIDER ELECTRIC", "count": 30},
                    {"value": "ABB", "count": 3000},
                    {"value": "Siemens", "count": 2500}
                ]
            },
            "reasoning": """
            CATEGORICAL ANALYSIS:
            1. Cardinality: 5.2% (~520 unique values) - medium cardinality
            2. Frequency Distribution:
               - Schneider variants: 5080 total (50.8% combined support)
               - ABB: 3000 (30% support)
               - Siemens: 2500 (25% support)
            3. CLUSTERING DETECTED: Three entries for same entity with different casing
               - 'Schneider Electric' (5000) - canonical form (highest frequency)
               - 'schneider electric' (50) - lowercase variant
               - 'SCHNEIDER ELECTRIC' (30) - uppercase variant

            K-FOLD VALIDATION:
            - Case inconsistency would appear in any fold (80/5080 = 1.6% error rate)
            - Rule confidence: 98.4% of Schneider records use canonical form
            - High support (50.8%) ensures rule generalizes across folds

            GENERALIZATION: Cluster by lowercase, identify canonical form by max frequency
            """,
            "rules": [
                {
                    "attribute_name": "Manufacturer Name",
                    "rule_category": "Completeness",
                    "rule_type": "NOT_NULL",
                    "rule_expression": "Manufacturer Name IS NOT NULL",
                    "rule_expression_sql": "SELECT * FROM products WHERE \"Manufacturer Name\" IS NULL",
                    "rule_expression_python": "df[df['Manufacturer Name'].isna()]",
                    "severity": "High",
                    "description": "Number of poles must be a standard value between 1 and 5",
                    "threshold_percent": 1.0,
                    "derived_from": "top_values: 3 (7562), 4 (1678), 2 (1567), 1 (445)",
                    "confidence_score": 0.95,
                    "sample_valid_values": ["1", "2", "3", "4", "5"],
                    "sample_invalid_values": ["0", "6", "10", "N/A"]
                }
            ]
        },
        {
            "attribute_name": "zz_Contact Current Rating",
            "profiling": {
                "datatype": "Categorical",
                "missing_percentage": 66.93,
                "cardinality": "0.59%",
                "top_values": [
                    {"value": "25", "count": 890},
                    {"value": "9", "count": 756},
                    {"value": "12", "count": 611},
                    {"value": "32", "count": 378}
                ],
                "range": [6, 800]
            },
            "rules": [
                {
                    "rule_id": "DQ_ZZ_CONTACT_CURRENT_RATING_VALIDITY_001",
                    "attribute_name": "zz_Contact Current Rating",
                    "rule_category": "Validity",
                    "rule_type": "RANGE",
                    "rule_expression": "CAST(zz_Contact Current Rating AS NUMERIC) BETWEEN 6 AND 800",
                    "rule_expression_sql": "SELECT * FROM products WHERE CAST(\"zz_Contact Current Rating\" AS NUMERIC) < 6 OR CAST(\"zz_Contact Current Rating\" AS NUMERIC) > 800",
                    "rule_expression_python": "df[(pd.to_numeric(df['zz_Contact Current Rating'], errors='coerce') < 6) | (pd.to_numeric(df['zz_Contact Current Rating'], errors='coerce') > 800)]",
                    "severity": "High",
                    "description": "Contact current rating must be between 6A and 800A per IEC standards",
                    "threshold_percent": 2.0,
                    "derived_from": "Common IEC current ratings: 6-800A range from top_values",
                    "confidence_score": 0.88,
                    "sample_valid_values": ["9", "12", "25", "32", "40", "100", "200", "400"],
                    "sample_invalid_values": ["0", "1", "5", "1000", "2000"]
                }
            ]
        },
        {
            "attribute_name": "zz_Dielectric Rating",
            "profiling": {
                "datatype": "Categorical",
                "missing_percentage": 99.99,
                "cardinality": "0.01%",
                "top_values": [
                    {"value": "2500 V (RMS) (Coil to Contacts)", "count": 2},
                    {"value": "1500 V (RMS) (Coil to Contacts), 1000 V (RMS) (Across Open Contacts, Pole to Pole, Contacts to Frame)", "count": 1}
                ],
                "sparsity": "99.99%"
            },
            "rules": [
                {
                    "rule_id": "DQ_ZZ_DIELECTRIC_RATING_VALIDITY_001",
                    "attribute_name": "zz_Dielectric Rating",
                    "rule_category": "Validity",
                    "rule_type": "FORMAT_PATTERN",
                    "rule_expression": "zz_Dielectric Rating MATCHES voltage pattern format",
                    "rule_expression_sql": "SELECT * FROM products WHERE \"zz_Dielectric Rating\" IS NOT NULL AND \"zz_Dielectric Rating\" NOT REGEXP '[0-9]+ V \\\\(RMS\\\\)'",
                    "rule_expression_python": "df[df['zz_Dielectric Rating'].notna() & ~df['zz_Dielectric Rating'].astype(str).str.contains(r'\\d+ V \\(RMS\\)', na=False)]",
                    "severity": "Medium",
                    "description": "When present, dielectric rating must follow voltage format pattern (e.g., '2500 V (RMS)')",
                    "threshold_percent": 1.0,
                    "derived_from": "top_values pattern: voltage values in 'X V (RMS)' format with 99.99% missing",
                    "confidence_score": 0.75,
                    "sample_valid_values": ["2500 V (RMS) (Coil to Contacts)", "1500 V (RMS) (Coil to Contacts), 1000 V (RMS) (Across Open Contacts, Pole to Pole, Contacts to Frame)"],
                    "sample_invalid_values": ["2500", "V", "2500V", "invalid"]
                }
            ]
        },
        {
            "attribute_name": "zz_Mounting Type",
            "profiling": {
                "datatype": "Categorical",
                "missing_percentage": 45.2,
                "cardinality": "0.12%",
                "top_values": [
                    {"value": "On Rail", "count": 3420},
                    {"value": "35mm rail", "count": 2108},
                    {"value": "DIN Rail", "count": 1956},
                    {"value": "Screw mount", "count": 1234},
                    {"value": "Bolt mount", "count": 892},
                    {"value": "Panel Mount", "count": 456}
                ]
            },
            "rules": [
                {
                    "rule_id": "DQ_ZZ_MOUNTING_TYPE_CONSISTENCY_001",
                    "attribute_name": "zz_Mounting Type",
                    "rule_category": "Consistency",
                    "rule_type": "NORMALIZE_RULE",
                    "rule_expression": "Normalize mounting type variations to standard values: 'On Rail', '35mm rail' → 'DIN Rail'; 'Screw mount', 'Bolt mount' → 'Panel Mount'",
                    "rule_expression_sql": "SELECT * FROM products WHERE \"zz_Mounting Type\" IN ('On Rail', '35mm rail') AND \"zz_Mounting Type\" != 'DIN Rail' UNION SELECT * FROM products WHERE \"zz_Mounting Type\" IN ('Screw mount', 'Bolt mount') AND \"zz_Mounting Type\" != 'Panel Mount'",
                    "rule_expression_python": "df[((df['zz_Mounting Type'].isin(['On Rail', '35mm rail'])) & (df['zz_Mounting Type'] != 'DIN Rail')) | ((df['zz_Mounting Type'].isin(['Screw mount', 'Bolt mount'])) & (df['zz_Mounting Type'] != 'Panel Mount'))]",
                    "severity": "Medium",
                    "description": "Mounting type synonyms must be normalized to standard values for consistency",
                    "threshold_percent": 5.0,
                    "derived_from": "top_values showing multiple synonyms: 'On Rail' (3420), '35mm rail' (2108), 'DIN Rail' (1956) should be unified",
                    "confidence_score": 0.92,
                    "sample_valid_values": ["DIN Rail", "Panel Mount", "Chassis Mount"],
                    "sample_invalid_values": ["On Rail", "35mm rail", "Screw mount", "Bolt mount"]
                },
                {
                    "rule_id": "DQ_ZZ_MOUNTING_TYPE_COMPLETENESS_001",
                    "attribute_name": "zz_Mounting Type",
                    "rule_category": "Completeness",
                    "rule_type": "NOT_NULL",
                    "rule_expression": "zz_Mounting Type IS NOT NULL",
                    "rule_expression_sql": "SELECT * FROM products WHERE \"zz_Mounting Type\" IS NULL",
                    "rule_expression_python": "df[df['zz_Mounting Type'].isna()]",
                    "severity": "High",
                    "description": "Mounting type should be specified for proper installation guidance",
                    "threshold_percent": 48.0,
                    "derived_from": "missing_percentage: 45.2% (threshold set to current state + 3%)",
                    "confidence_score": 0.88,
                    "sample_valid_values": ["DIN Rail", "Panel Mount", "Chassis Mount"],
                    "sample_invalid_values": ["", None, "N/A"]
                }
            ]
        },
        {
            "attribute_name": "zz_Type",
            "profiling": {
                "datatype": "Categorical",
                "missing_percentage": 12.5,
                "cardinality": "0.08%",
                "top_values": [
                    {"value": "Power Contactor", "count": 15420},
                    {"value": "Auxiliary", "count": 4108},
                    {"value": "Reversing Contactor", "count": 2156},
                    {"value": "Mini Contactor", "count": 1892}
                ]
            },
            "rules": [
                {
                    "rule_id": "DQ_ZZ_TYPE_CONSISTENCY_001",
                    "attribute_name": "zz_Type",
                    "rule_category": "Consistency",
                    "rule_type": "COMPUTATION_RULE",
                    "rule_expression": "If zz_Contact Current Rating is NULL, zz_Type should be 'Auxiliary'",
                    "rule_expression_sql": "SELECT * FROM products WHERE \"zz_Contact Current Rating\" IS NULL AND (\"zz_Type\" IS NULL OR \"zz_Type\" != 'Auxiliary')",
                    "rule_expression_python": "df[(df['zz_Contact Current Rating'].isna()) & ((df['zz_Type'].isna()) | (df['zz_Type'] != 'Auxiliary'))]",
                    "severity": "High",
                    "description": "Products without current rating should be classified as Auxiliary contactors",
                    "threshold_percent": 2.0,
                    "derived_from": "Business rule: Auxiliary contactors do not have current ratings",
                    "confidence_score": 0.90,
                    "sample_valid_values": ["Auxiliary (when current rating is null)"],
                    "sample_invalid_values": ["Power Contactor (when current rating is null)", "null (when current rating is null)"]
                },
                {
                    "rule_id": "DQ_ZZ_TYPE_CONSISTENCY_002",
                    "attribute_name": "zz_Type",
                    "rule_category": "Consistency",
                    "rule_type": "CROSS_ATTRIBUTE_RULE",
                    "rule_expression": "If zz_Contact Current Rating < 9A AND zz_Frame Size = 'Small', zz_Type should be 'Mini Contactor'",
                    "rule_expression_sql": "SELECT * FROM products WHERE CAST(\"zz_Contact Current Rating\" AS NUMERIC) < 9 AND \"zz_Frame Size\" = 'Small' AND \"zz_Type\" != 'Mini Contactor'",
                    "rule_expression_python": "df[(pd.to_numeric(df['zz_Contact Current Rating'], errors='coerce') < 9) & (df['zz_Frame Size'] == 'Small') & (df['zz_Type'] != 'Mini Contactor')]",
                    "severity": "Medium",
                    "description": "Small frame contactors with low current ratings should be classified as Mini Contactors",
                    "threshold_percent": 3.0,
                    "derived_from": "Business rule: Mini contactors are defined by current < 9A and small frame size",
                    "confidence_score": 0.85,
                    "sample_valid_values": ["Mini Contactor (when current < 9A and frame = Small)"],
                    "sample_invalid_values": ["Power Contactor (when current < 9A and frame = Small)"]
                }
            ]
        }
    ]


def format_few_shot_examples(examples: List[Dict[str, Any]]) -> str:
    """
    Format few-shot examples for inclusion in prompt.

    Args:
        examples: List of example dictionaries

    Returns:
        Formatted string for prompt
    """
    import json

    formatted = []
    for ex in examples[:3]:
        formatted.append(f"""
### Example: {ex['attribute_name']}
**Profiling Statistics:**
```json
{json.dumps(ex['profiling'], indent=2)}
```

**Derived Rules:**
```json
{json.dumps(ex['rules'], indent=2)}
```
""")
    return "\n".join(formatted)


def build_derivation_prompt(
    attribute_analysis: Dict[str, Any],
    dataset_context: Dict[str, Any],
    few_shot_examples: List[Dict[str, Any]],
) -> str:
    """
    Build the complete prompt for rule derivation.

    Args:
        attribute_analysis: Analysis results for the attribute
        dataset_context: Overall dataset metadata
        few_shot_examples: Example rule derivations

    Returns:
        Complete prompt string
    """
    import json

    formatted_examples = format_few_shot_examples(few_shot_examples)

    # Get data population category for clearer guidance
    missing_pct = attribute_analysis['missing_percentage']
    population_category = get_data_population_category(missing_pct)

    # Determine type category
    type_category = get_type_category(attribute_analysis['datatype'])

    # Calculate populated records info
    total_records = dataset_context.get('total_records', 'Unknown')
    if isinstance(total_records, (int, float)):
        populated_records = int(total_records * (100 - missing_pct) / 100)
        populated_info = f"~{populated_records:,} records ({100 - missing_pct:.1f}%)"
    else:
        populated_info = f"{100 - missing_pct:.1f}% of records"

    # Build type-specific analysis guidance
    type_guidance = ""
    if type_category == "NUMERIC":
        type_guidance = f"""
## TYPE-SPECIFIC ANALYSIS: NUMERIC
Apply these reasoning steps for this numeric attribute:

1. **Distribution Analysis**: Examine the range [{attribute_analysis.get('range', 'N/A')}]
   - Are values clustered or spread across the range?
   - Is the distribution skewed based on top_values frequencies?

2. **Range Derivation**: Use observed min/max as hard boundaries
   - Consider IQR-based outlier detection if stats available

3. **Precision Check**: Analyze if values are integers or decimals
   - Look for common multipliers or increments

4. **Generalization Methods to Consider**:
   - RANGE (observed bounds)
   - STATISTICAL_BOUNDS (IQR-based)
   - PRECISION (integer vs decimal)
   - VALUE_SET (if <20 unique values)
"""
    elif type_category == "CATEGORICAL":
        type_guidance = f"""
## TYPE-SPECIFIC ANALYSIS: CATEGORICAL
Apply these reasoning steps for this categorical attribute:

1. **Cardinality Assessment**: {attribute_analysis['cardinality']}
   - Low (<10): Use VALUE_SET with full enumeration
   - Medium (10-50): Consider clustering/grouping
   - High (>50): Treat as string

2. **Frequency Distribution**: Calculate support for each value
   - Identify dominant values (>50% support)
   - Flag rare values (<{t['min_support']*100}% support)

3. **Clustering Detection**: Look for semantic variants
   - Case variations (same word, different case)
   - Spacing/formatting variations
   - Abbreviation variants

4. **Generalization Methods to Consider**:
   - ENUMERATION (value set from observed)
   - CLUSTERING (normalize variants)
   - OBSERVED_PATTERN (format consistency)
"""
    else:  # STRING
        type_guidance = f"""
## TYPE-SPECIFIC ANALYSIS: STRING
Apply these reasoning steps for this string attribute:

1. **Length Analysis**: Calculate length statistics from top_values
   - Fixed length? Variable length with bounds?

2. **Character Composition**: Identify character classes
   - Alpha, numeric, alphanumeric, special characters
   - Position-specific patterns (prefix, suffix, delimiters)

3. **Pattern Extraction**: Build regex from observed structure
   - Only include patterns with >{t['min_confidence']*100}% match rate

4. **Semantic Clustering**: Group by similarity
   - Identify canonical forms for normalization

5. **Generalization Methods to Consider**:
   - OBSERVED_PATTERN (regex from structure)
   - CLUSTERING (normalize variants)
   - LENGTH (if fixed or bounded)
"""

    # Build data-driven guidance based on missing percentage
    data_driven_guidance = ""
    if missing_pct >= 95:
        data_driven_guidance = f"""
## DATA POPULATION GUIDANCE
**SPARSE FIELD DETECTED**: {missing_pct}% missing ({populated_info} populated)
- DO NOT generate Completeness rules (would fail support threshold)
- Focus on Validity rules for populated subset
- Support will be low (~{(100-missing_pct)/100:.3f}) - still valid if confidence is high
- Severity: "Low" (optional field)
"""
    elif missing_pct >= 50:
        data_driven_guidance = f"""
## DATA POPULATION GUIDANCE
**PARTIALLY POPULATED**: {missing_pct}% missing ({populated_info} populated)
- Completeness rules: threshold_percent = {missing_pct + 1:.0f}%
- Support = {(100-missing_pct)/100:.2f} (applicable to all records)
- Severity: "Low" to "Medium"
"""
    elif missing_pct >= 20:
        data_driven_guidance = f"""
## DATA POPULATION GUIDANCE
**MODERATE POPULATION**: {missing_pct}% missing ({populated_info} populated)
- Completeness rules appropriate with threshold = {missing_pct + 5:.0f}%
- Severity: "Medium"
"""
    elif missing_pct >= 5:
        data_driven_guidance = f"""
## DATA POPULATION GUIDANCE
**WELL POPULATED**: Only {missing_pct}% missing ({populated_info} populated)
- Standard completeness rules apply
- Threshold_percent = {missing_pct + 2:.0f}%
- Severity: "High"
"""
    else:
        data_driven_guidance = f"""
## DATA POPULATION GUIDANCE
**REQUIRED FIELD**: Only {missing_pct}% missing ({populated_info} populated)
- Critical completeness rules with low threshold = {max(missing_pct + 1, 2):.0f}%
- Severity: "Critical" or "High"
"""

    # Check for numeric pattern
    numeric_pattern_info = ""
    if 'numeric_pattern' in attribute_analysis:
        pattern = attribute_analysis['numeric_pattern']
        pattern_type = pattern.get('type', 'unknown')
        pattern_min = pattern.get('min', 'N/A')
        pattern_max = pattern.get('max', 'N/A')
        pattern_step = pattern.get('step', 'N/A')
        pattern_desc = pattern.get('description', '')
        pattern_invalid = pattern.get('invalid_examples', [])
        numeric_pattern_info = f"""
## Detected Numeric Pattern (USE THIS FOR RULE GENERATION)
- **Pattern Type:** {pattern_type}
- **Min Value:** {pattern_min}
- **Max Value:** {pattern_max}
- **Step/Increment:** {pattern_step}
- **Pattern Description:** {pattern_desc}
- **Example Invalid Values:** {pattern_invalid}

**IMPORTANT**: Use the pattern description in your rule, NOT the actual observed values.
For example: "Values must be between {pattern_min} and {pattern_max} with {pattern_step} increments"
"""

    # Dynamic quality guidance based on field characteristics
    quality_constraints = ""
    distinct_count = attribute_analysis.get('total_distinct_count', len(attribute_analysis.get('top_values', [])))

    # Check if all values are numeric
    all_numeric = attribute_analysis.get('all_values_numeric', False)
    if not all_numeric:
        top_vals = attribute_analysis.get('top_values', [])
        try:
            all_numeric = all(
                _is_numeric_value(str(tv.get('value', '')))
                for tv in top_vals if tv.get('value') is not None and str(tv.get('value', '')).strip()
            ) if top_vals else False
        except Exception:
            all_numeric = False

    if distinct_count > 30:
        quality_constraints += f"""
## IMPORTANT: High Cardinality Field ({distinct_count} distinct values)
This field has {distinct_count} distinct values. **DO NOT generate VALUE_SET rules.**
- Use RANGE rules if values are numeric
- Use FORMAT_PATTERN rules if values follow a structural pattern
- Use NORMALIZATION rules if variant forms of same values exist
- VALUE_SET with {distinct_count} values provides zero validation value
"""
    if all_numeric and type_category == "CATEGORICAL":
        quality_constraints += """
## IMPORTANT: Numeric Values in Categorical Field
All values in this field are numeric. **You MUST treat this as a numeric field:**
- Generate RANGE rules (min to max) instead of VALUE_SET
- Generate PRECISION rules (integer vs decimal)
- Generate STATISTICAL_BOUNDS rules for outlier detection
- Do NOT generate VALUE_SET - use RANGE instead
"""

    prompt = f"""
## Dataset Context
- **Dataset Name:** {dataset_context.get('dataset_name', 'Product_Data')}
- **Domain:** {dataset_context.get('domain', 'Product')}
- **Total Records:** {dataset_context.get('total_records', 'Unknown')}

## Attribute to Analyze
- **Attribute Name:** {attribute_analysis['attribute_name']}
- **Data Type:** {attribute_analysis['datatype']}
- **Missing Percentage:** {attribute_analysis['missing_percentage']}%
- **Cardinality:** {attribute_analysis['cardinality']}
- **Total Distinct Values:** {distinct_count}
- **Range:** {attribute_analysis.get('range', 'N/A')}
- **All Values Numeric:** {all_numeric}
- **All Distinct Values (with counts):**
```json
{json.dumps(attribute_analysis['top_values'], indent=2, default=str)}
```
{numeric_pattern_info}
{quality_constraints}

## Recommended Rule Types
{', '.join(attribute_analysis.get('recommended_rules', []))}

## Few-Shot Examples
{formatted_examples}

## Instructions
Based on the profiling statistics above, generate ALL applicable DQ rules for the attribute "{attribute_analysis['attribute_name']}".

**CRITICAL RULE DERIVATION GUIDELINES:**

**1. Data-Driven Approach:**
   - Derive rules based on ACTUAL DATA CHARACTERISTICS, not idealistic expectations
   - For missing_percentage > 80%: NO Completeness rules, only Validity/Format rules, Low/Medium severity
   - For missing_percentage 50-80%: Completeness threshold = current state ±5%, plus Validity rules
   - For missing_percentage < 50%: Standard Completeness and Validity rules

**2. DAMA Framework Coverage (derive rules for ALL applicable dimensions):**
   - **Completeness**: Check if attribute should be mandatory based on missing_percentage
   - **Validity**: Derive from top_values (VALUE_SET, RANGE, FORMAT_PATTERN, REGEX)
   - **Consistency**: Check top_values for synonyms/variations requiring normalization
   - **Uniqueness**: Check cardinality to identify potential keys
   - **Accuracy**: Derive ranges/precision from numeric patterns
   - **Timeliness**: For date fields, check recency and sequence

**3. Advanced Rule Types (critically important):**
   - **NORMALIZE_RULE**: If top_values show variations/synonyms (e.g., "On Rail", "35mm rail", "DIN Rail")
     → Create normalization rule mapping variants to canonical value
   - **COMPUTATION_RULE**: Infer from domain knowledge (e.g., if no current rating, type = "Auxiliary")
     → Consider logical relationships between attributes
   - **CROSS_ATTRIBUTE_RULE**: Identify dependencies (e.g., if current < 9A AND frame = Small → Mini Contactor)
     → Look for patterns that span multiple attributes
   - **CONDITIONAL_VALIDATION**: Rules that apply only in specific contexts
   - **DEFAULT_VALUE**: When to auto-populate missing values based on other attributes

**4. Rule Multiplicity:**
   - Generate MULTIPLE rules per attribute (2-5 rules per attribute is typical)
   - Combine Completeness + Validity + Consistency rules when applicable
   - Don't stop at just one rule type - think comprehensively

**5. Technical Requirements:**
   - Use format: DQ_{{ATTRIBUTE_NAME}}_{{CATEGORY}}_{{SEQUENCE}}
   - Provide working SQL and Python expressions
   - Set realistic thresholds based on current data state
   - Include actual sample values from profiling data
   - Reference specific profiling statistics in derived_from

**IMPORTANT:** Return ONLY a valid JSON array of rule objects. Do not include any other text.

Generate the rules now:
"""
    return prompt
