"""Prompt templates for DQ rule derivation using LLM."""

from typing import List, Dict, Any

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

## CORE PRINCIPLE: REASONING FROM DATA, NOT KNOWLEDGE

You MUST derive ALL rules through logical reasoning and pattern analysis of the provided data.
DO NOT use external domain knowledge or assumptions about what the data "should" contain.

**Generalization Approach:**
1. OBSERVE: Analyze the actual values, frequencies, and distributions in the profiling data
2. ABSTRACT: Identify patterns, clusters, and regularities using ONLY the evidence provided
3. GENERALIZE: Form rules that capture these patterns with measurable support and confidence
4. VALIDATE: Ensure rules are falsifiable and can be tested against the data

## DAMA Framework - 6 Core Data Quality Dimensions

Generate rules across ALL applicable DAMA framework dimensions:

1. **Completeness** - Is the data present?
   - Rule Types: NOT_NULL, NOT_EMPTY, NOT_WHITESPACE
   - Check: Are required fields populated?
   - SKIP for sparse fields (>75% missing)

2. **Validity** - Does data conform to defined formats/constraints?
   - Rule Types: VALUE_SET, RANGE, FORMAT_PATTERN, DATA_TYPE, LENGTH
   - Check: Is data in valid format, within allowed ranges, correct data type?

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
- rule_category: One of (Completeness, Validity, Accuracy, Consistency, Uniqueness, Timeliness, Normalization, Computation, Default)
- rule_type: Specific rule type
- rule_expression: Implementable rule logic
- rule_expression_sql: SQL query to find violations
- rule_expression_python: Python/pandas code to find violations
- severity: One of (Critical, High, Medium, Low)
- description: Business-friendly explanation (use GENERALIZED descriptions - ranges, counts, patterns - NOT actual values)
- threshold_percent: Acceptable failure rate (0-100)
- **support** (REQUIRED): Proportion of data this rule applies to (0.0-1.0) - MUST be calculated
- **confidence** (REQUIRED): Proportion of applicable data satisfying rule (0.0-1.0) - MUST be calculated
- derived_from: Profiling statistic and reasoning used
- sample_valid_values: Valid examples FROM THE DATA
- sample_invalid_values: Invalid examples (for numeric patterns, show values that violate the step/increment)
- generalization_method: How the rule was derived (OBSERVED_PATTERN | STATISTICAL_BOUND | ENUMERATION | CLUSTERING | ARITHMETIC_SEQUENCE)

**CRITICAL**: Every rule MUST have calculated support and confidence values. Rules without these will be rejected.
"""


def get_system_prompt(thresholds: Dict[str, float] = None) -> str:
    """
    Get the system prompt for rule derivation with configurable thresholds.

    Args:
        thresholds: Optional dict with min_support, min_confidence, high_confidence, k_folds

    Returns:
        Formatted system prompt with threshold values interpolated
    """
    t = thresholds or RULE_THRESHOLDS
    return SYSTEM_PROMPT.format(
        min_support=t.get("min_support", 0.05),
        min_confidence=t.get("min_confidence", 0.70),
        high_confidence=t.get("high_confidence", 0.90),
        k_folds=t.get("k_folds", 5),
        min_fold_consistency=t.get("min_fold_consistency", 0.80)
    )


def get_few_shot_examples() -> List[Dict[str, Any]]:
    """
    Get few-shot examples for rule derivation based on data-driven approach.
    Includes examples demonstrating type-specific handling, support/confidence metrics,
    and generalization methods.

    Returns:
        List of example rule derivations showing proper data-driven rules
    """
    return [
        # Example 1: STRING type - ID field with pattern derivation
        {
            "attribute_name": "RS Stock Number",
            "data_type_category": "STRING",
            "profiling": {
                "datatype": "ID",
                "missing_percentage": 0.0,
                "cardinality": "100%",
                "total_records": 10000,
                "top_values": [
                    {"value": "123-4567", "count": 1},
                    {"value": "234-5678", "count": 1},
                    {"value": "345-6789", "count": 1}
                ],
                "length_stats": {"min": 8, "max": 8, "avg": 8.0}
            },
            "reasoning": """
            STRING ANALYSIS:
            1. Length Analysis: All values are exactly 8 characters (fixed length)
            2. Character Composition: Pattern observed is DDD-DDDD (digits-dash-digits)
            3. Delimiter: Dash at position 4 is consistent across all samples
            4. Cardinality: 100% unique suggests identifier/primary key

            GENERALIZATION: Fixed-length alphanumeric with consistent delimiter pattern
            """,
            "rules": [
                {
                    "attribute_name": "RS Stock Number",
                    "rule_category": "Completeness",
                    "rule_type": "NOT_NULL",
                    "rule_expression": "RS Stock Number IS NOT NULL",
                    "rule_expression_sql": "SELECT * FROM products WHERE \"RS Stock Number\" IS NULL",
                    "rule_expression_python": "df[df['RS Stock Number'].isna()]",
                    "severity": "Critical",
                    "description": "RS Stock Number is 100% populated - this is a required identifier field.",
                    "threshold_percent": 0.0,
                    "support": 1.0,
                    "confidence": 1.0,
                    "derived_from": "missing_percentage: 0.0% - mandatory field observed in data",
                    "sample_valid_values": ["123-4567", "234-5678", "345-6789"],
                    "sample_invalid_values": ["", None],
                    "generalization_method": "OBSERVED_PATTERN"
                },
                {
                    "attribute_name": "RS Stock Number",
                    "rule_category": "Uniqueness",
                    "rule_type": "PRIMARY_KEY",
                    "rule_expression": "RS Stock Number must be unique across all records",
                    "rule_expression_sql": "SELECT \"RS Stock Number\", COUNT(*) FROM products GROUP BY \"RS Stock Number\" HAVING COUNT(*) > 1",
                    "rule_expression_python": "df[df.duplicated(subset=['RS Stock Number'], keep=False)]",
                    "severity": "Critical",
                    "description": "RS Stock Number has 100% cardinality - each value is unique, functioning as primary key.",
                    "threshold_percent": 0.0,
                    "support": 1.0,
                    "confidence": 1.0,
                    "derived_from": "cardinality: 100% - all top_values have count=1",
                    "sample_valid_values": ["123-4567", "234-5678"],
                    "sample_invalid_values": ["duplicate_value"],
                    "generalization_method": "OBSERVED_PATTERN"
                },
                {
                    "attribute_name": "RS Stock Number",
                    "rule_category": "Validity",
                    "rule_type": "FORMAT_PATTERN",
                    "rule_expression": "RS Stock Number MATCHES pattern ^[0-9]{3}-[0-9]{4}$",
                    "rule_expression_sql": "SELECT * FROM products WHERE \"RS Stock Number\" NOT REGEXP '^[0-9]{3}-[0-9]{4}$'",
                    "rule_expression_python": "df[~df['RS Stock Number'].astype(str).str.match(r'^[0-9]{3}-[0-9]{4}$', na=False)]",
                    "severity": "High",
                    "description": "Pattern derived from data: 3 digits, dash, 4 digits. All observed values follow this structure.",
                    "threshold_percent": 1.0,
                    "support": 1.0,
                    "confidence": 0.95,
                    "derived_from": "Regex derived from top_values analysis: fixed length 8, dash at position 4, numeric characters",
                    "sample_valid_values": ["123-4567", "234-5678"],
                    "sample_invalid_values": ["12345", "ABC-1234", "123-456"],
                    "generalization_method": "OBSERVED_PATTERN"
                }
            ]
        },
        # Example 2: CATEGORICAL type - SPARSE field (>95% missing)
        {
            "attribute_name": "zz_Dielectric Rating",
            "data_type_category": "CATEGORICAL",
            "profiling": {
                "datatype": "Categorical",
                "missing_percentage": 99.99,
                "cardinality": "0.01%",
                "total_records": 10000,
                "populated_records": 3,
                "top_values": [
                    {"value": "2500 V (RMS) (Coil to Contacts)", "count": 2},
                    {"value": "1500 V (RMS) (Coil to Contacts)", "count": 1}
                ]
            },
            "reasoning": """
            CATEGORICAL ANALYSIS:
            1. Cardinality Assessment: Only 2 unique values observed (very low cardinality)
            2. Frequency Distribution: 2500V has 66.7% support (2/3), 1500V has 33.3% (1/3)
            3. Sparsity: 99.99% missing - this is an optional/specialized field

            K-FOLD CONSIDERATION:
            - With only 3 records, rule may not generalize well across folds
            - Confidence is high for existing data but support is extremely low
            - DO NOT generate completeness rule (would fail k-fold validation)

            GENERALIZATION: Low-cardinality enumeration for populated subset only
            """,
            "rules": [
                {
                    "attribute_name": "zz_Dielectric Rating",
                    "rule_category": "Validity",
                    "rule_type": "VALUE_SET",
                    "rule_expression": "zz_Dielectric Rating IN observed values when populated",
                    "rule_expression_sql": "SELECT * FROM products WHERE \"zz_Dielectric Rating\" IS NOT NULL AND \"zz_Dielectric Rating\" NOT IN ('2500 V (RMS) (Coil to Contacts)', '1500 V (RMS) (Coil to Contacts)')",
                    "rule_expression_python": "df[df['zz_Dielectric Rating'].notna() & ~df['zz_Dielectric Rating'].isin(['2500 V (RMS) (Coil to Contacts)', '1500 V (RMS) (Coil to Contacts)'])]",
                    "severity": "Low",
                    "description": "SPARSE FIELD (99.99% missing). For populated records, values should be one of the 2 observed dielectric rating categories.",
                    "threshold_percent": 100.0,
                    "support": 0.0003,
                    "confidence": 1.0,
                    "derived_from": "Enumerated all observed values from top_values (exhaustive for 3 records)",
                    "sample_valid_values": ["2500 V (RMS) (Coil to Contacts)", "1500 V (RMS) (Coil to Contacts)"],
                    "sample_invalid_values": ["Invalid", "N/A", "Unknown"],
                    "generalization_method": "ENUMERATION"
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
                    "description": "97.5% populated - effectively required. Only 2.5% missing.",
                    "threshold_percent": 3.0,
                    "support": 1.0,
                    "confidence": 0.975,
                    "derived_from": "missing_percentage: 2.5% indicates near-mandatory field",
                    "sample_valid_values": ["Schneider Electric", "ABB", "Siemens"],
                    "sample_invalid_values": ["", None],
                    "generalization_method": "OBSERVED_PATTERN"
                },
                {
                    "attribute_name": "Manufacturer Name",
                    "rule_category": "Consistency",
                    "rule_type": "CASE_CONSISTENCY",
                    "rule_expression": "Manufacturer Name should have consistent casing per entity",
                    "rule_expression_sql": "SELECT \"Manufacturer Name\", COUNT(*) FROM products GROUP BY LOWER(\"Manufacturer Name\") HAVING COUNT(DISTINCT \"Manufacturer Name\") > 1",
                    "rule_expression_python": "df.groupby(df['Manufacturer Name'].str.lower())['Manufacturer Name'].nunique().loc[lambda x: x > 1]",
                    "severity": "Medium",
                    "description": "Clustering detected 3 case variants for 'Schneider Electric'. Canonical form has 98.4% frequency within cluster.",
                    "threshold_percent": 5.0,
                    "support": 0.508,
                    "confidence": 0.984,
                    "derived_from": "Semantic clustering by lowercase: 3 variants detected with counts 5000, 50, 30",
                    "sample_valid_values": ["Schneider Electric"],
                    "sample_invalid_values": ["schneider electric", "SCHNEIDER ELECTRIC"],
                    "generalization_method": "CLUSTERING"
                },
                {
                    "attribute_name": "Manufacturer Name",
                    "rule_category": "Normalization",
                    "rule_type": "VALUE_STANDARDIZATION",
                    "rule_expression": "Normalize case variants to canonical form: 'Schneider Electric'",
                    "rule_expression_sql": "SELECT * FROM products WHERE LOWER(\"Manufacturer Name\") = 'schneider electric' AND \"Manufacturer Name\" != 'Schneider Electric'",
                    "rule_expression_python": "df[(df['Manufacturer Name'].str.lower() == 'schneider electric') & (df['Manufacturer Name'] != 'Schneider Electric')]",
                    "severity": "Low",
                    "description": "80 records need normalization to canonical 'Schneider Electric' (1.6% of Schneider cluster).",
                    "threshold_percent": 2.0,
                    "support": 0.508,
                    "confidence": 0.984,
                    "derived_from": "Canonical form identified by max frequency (5000) within case-insensitive cluster",
                    "sample_valid_values": ["Schneider Electric"],
                    "sample_invalid_values": ["schneider electric", "SCHNEIDER ELECTRIC"],
                    "generalization_method": "CLUSTERING"
                }
            ]
        },
        # Example 4: NUMERIC type - Range, Statistical Bounds, Precision
        {
            "attribute_name": "zz_Contact Current Rating",
            "data_type_category": "NUMERIC",
            "profiling": {
                "datatype": "Numeric",
                "missing_percentage": 66.93,
                "cardinality": "0.59%",
                "total_records": 10000,
                "populated_records": 3307,
                "top_values": [
                    {"value": "25", "count": 890},
                    {"value": "9", "count": 756},
                    {"value": "12", "count": 611},
                    {"value": "32", "count": 378}
                ],
                "range": [6, 800],
                "numeric_stats": {
                    "min": 6, "max": 800, "mean": 42.5, "median": 25, "std": 58.3,
                    "q1": 12, "q3": 40, "iqr": 28
                }
            },
            "reasoning": """
            NUMERIC ANALYSIS:
            1. Distribution Analysis:
               - Range: 6-800 (observed from data)
               - Mean: 42.5, Median: 25 (right-skewed distribution)
               - Most values cluster in low range: 9, 12, 25, 32 are top values
            2. Range Derivation:
               - Hard bounds: [6, 800] from observed min/max
               - IQR-based soft bounds: [12 - 1.5*28, 40 + 1.5*28] = [-30, 82]
               - Since min > 0 in data, use [6, 82] for outlier detection
            3. Precision Pattern:
               - All top values are integers (no decimals observed)
               - Values appear to be discrete, not continuous
            4. Multiplier Pattern:
               - No obvious multiplier (values: 6, 9, 12, 25, 32, 40... not consistent multiples)

            K-FOLD VALIDATION:
            - Range [6, 800] observed across full dataset - will hold in all folds
            - Statistical bounds may vary slightly by fold
            - Integer precision is 100% consistent in top_values

            GENERALIZATION: Observed range bounds + statistical outlier detection
            """,
            "rules": [
                {
                    "attribute_name": "zz_Contact Current Rating",
                    "rule_category": "Validity",
                    "rule_type": "RANGE",
                    "rule_expression": "zz_Contact Current Rating BETWEEN 6 AND 800",
                    "rule_expression_sql": "SELECT * FROM products WHERE CAST(\"zz_Contact Current Rating\" AS NUMERIC) < 6 OR CAST(\"zz_Contact Current Rating\" AS NUMERIC) > 800",
                    "rule_expression_python": "df[(pd.to_numeric(df['zz_Contact Current Rating'], errors='coerce') < 6) | (pd.to_numeric(df['zz_Contact Current Rating'], errors='coerce') > 800)]",
                    "severity": "Medium",
                    "description": "Values could be between 6 and 800. Values outside this range are anomalies.",
                    "threshold_percent": 68.0,
                    "support": 0.3307,
                    "confidence": 1.0,
                    "derived_from": "range: [6, 800] from profiling numeric_stats - observed bounds",
                    "sample_valid_values": ["9", "12", "25", "32", "100", "400"],
                    "sample_invalid_values": ["0", "1", "5", "1000", "2000"],
                    "generalization_method": "OBSERVED_PATTERN"
                },
                {
                    "attribute_name": "zz_Contact Current Rating",
                    "rule_category": "Accuracy",
                    "rule_type": "STATISTICAL_BOUNDS",
                    "rule_expression": "zz_Contact Current Rating <= Q3 + 1.5*IQR (82)",
                    "rule_expression_sql": "SELECT * FROM products WHERE CAST(\"zz_Contact Current Rating\" AS NUMERIC) > 82",
                    "rule_expression_python": "df[pd.to_numeric(df['zz_Contact Current Rating'], errors='coerce') > 82]",
                    "severity": "Low",
                    "description": "IQR-based outlier detection: Q3(40) + 1.5*IQR(28) = 82. Values >82 are statistical outliers.",
                    "threshold_percent": 70.0,
                    "support": 0.3307,
                    "confidence": 0.85,
                    "derived_from": "Calculated from Q1=12, Q3=40, IQR=28. Upper fence = 40 + 42 = 82",
                    "sample_valid_values": ["9", "12", "25", "32", "40", "80"],
                    "sample_invalid_values": ["100", "200", "400", "800"],
                    "generalization_method": "STATISTICAL_BOUND"
                },
                {
                    "attribute_name": "zz_Contact Current Rating",
                    "rule_category": "Validity",
                    "rule_type": "PRECISION",
                    "rule_expression": "zz_Contact Current Rating must be integer (no decimals)",
                    "rule_expression_sql": "SELECT * FROM products WHERE \"zz_Contact Current Rating\" IS NOT NULL AND CAST(\"zz_Contact Current Rating\" AS NUMERIC) != FLOOR(CAST(\"zz_Contact Current Rating\" AS NUMERIC))",
                    "rule_expression_python": "df[df['zz_Contact Current Rating'].notna() & (pd.to_numeric(df['zz_Contact Current Rating'], errors='coerce') % 1 != 0)]",
                    "severity": "Low",
                    "description": "All observed values are integers. Decimal values may indicate data entry error.",
                    "threshold_percent": 68.0,
                    "support": 0.3307,
                    "confidence": 0.98,
                    "derived_from": "Precision analysis: 100% of top_values are whole numbers",
                    "sample_valid_values": ["9", "12", "25", "32"],
                    "sample_invalid_values": ["9.5", "12.3", "25.75"],
                    "generalization_method": "OBSERVED_PATTERN"
                }
            ]
        },
        # Example 5: CATEGORICAL type - Semantic clustering for normalization
        {
            "attribute_name": "zz_Number of Poles",
            "data_type_category": "CATEGORICAL",
            "profiling": {
                "datatype": "Categorical",
                "missing_percentage": 45.2,
                "cardinality": "2.1%",
                "total_records": 10000,
                "populated_records": 5480,
                "top_values": [
                    {"value": "3", "count": 2500},
                    {"value": "3P", "count": 800},
                    {"value": "3 Pole", "count": 350},
                    {"value": "Three Pole", "count": 120},
                    {"value": "4", "count": 1800},
                    {"value": "4P", "count": 600},
                    {"value": "2", "count": 1500}
                ]
            },
            "reasoning": """
            CATEGORICAL ANALYSIS:
            1. Cardinality: 2.1% (~210 unique) - low-medium cardinality
            2. Frequency Distribution with Semantic Clustering:
               - CLUSTER "3": 3(2500) + 3P(800) + 3 Pole(350) + Three Pole(120) = 3770 (68.8%)
                 * Canonical form: "3" (highest frequency in cluster)
               - CLUSTER "4": 4(1800) + 4P(600) = 2400 (43.8%)
                 * Canonical form: "4"
               - CLUSTER "2": 2(1500) = 1500 (27.4%)
                 * Already canonical

            3. Pattern Recognition for Variants:
               - Suffix "P": 3P, 4P (P = Pole abbreviation)
               - Suffix " Pole": 3 Pole (explicit form)
               - Word form: Three Pole (spelled out)
               - Numeric only: 2, 3, 4 (canonical form)

            K-FOLD VALIDATION:
            - Cluster "3" variants appear 1270/3770 = 33.7% of cluster (needs normalization)
            - High support (68.8% for largest cluster) ensures rule generalizes
            - Semantic similarity is deterministic - will hold across all folds

            GENERALIZATION: Extract numeric portion as canonical form
            """,
            "rules": [
                {
                    "attribute_name": "zz_Number of Poles",
                    "rule_category": "Normalization",
                    "rule_type": "VALUE_STANDARDIZATION",
                    "rule_expression": "Normalize pole representations to numeric: extract digit from variant forms",
                    "rule_expression_sql": "SELECT * FROM products WHERE \"zz_Number of Poles\" IS NOT NULL AND \"zz_Number of Poles\" NOT REGEXP '^[0-9]+$'",
                    "rule_expression_python": "df[df['zz_Number of Poles'].notna() & ~df['zz_Number of Poles'].astype(str).str.match(r'^\\d+$')]",
                    "severity": "Low",
                    "description": "Detected 4 variant forms for '3': '3', '3P', '3 Pole', 'Three Pole'. Normalize to numeric canonical form.",
                    "threshold_percent": 50.0,
                    "support": 0.548,
                    "confidence": 0.77,
                    "derived_from": "Semantic clustering: grouped variants by extractable numeric value. 23.2% need normalization.",
                    "sample_valid_values": ["2", "3", "4"],
                    "sample_invalid_values": ["3P", "3 Pole", "Three Pole", "4P"],
                    "generalization_method": "CLUSTERING"
                },
                {
                    "attribute_name": "zz_Number of Poles",
                    "rule_category": "Validity",
                    "rule_type": "VALUE_SET",
                    "rule_expression": "Extracted pole number IN (2, 3, 4)",
                    "rule_expression_sql": "SELECT * FROM products WHERE \"zz_Number of Poles\" IS NOT NULL AND REGEXP_REPLACE(\"zz_Number of Poles\", '[^0-9]', '') NOT IN ('2', '3', '4')",
                    "rule_expression_python": "df[df['zz_Number of Poles'].notna() & ~df['zz_Number of Poles'].astype(str).str.extract(r'(\\d+)')[0].isin(['2', '3', '4'])]",
                    "severity": "Medium",
                    "description": "Values could be one of the 3 observed pole count categories. Other values are anomalies.",
                    "threshold_percent": 50.0,
                    "support": 0.548,
                    "confidence": 0.99,
                    "derived_from": "Enumerated unique pole counts from clustered data: {2, 3, 4}",
                    "sample_valid_values": ["2", "3", "4", "3P", "4P"],
                    "sample_invalid_values": ["1", "5", "6", "0", "N/A"],
                    "generalization_method": "ENUMERATION"
                }
            ]
        },
        # Example 6: STRING type - Format pattern derivation with normalization
        {
            "attribute_name": "zz_Contact Configuration",
            "data_type_category": "STRING",
            "profiling": {
                "datatype": "Categorical",
                "missing_percentage": 52.8,
                "cardinality": "3.5%",
                "total_records": 10000,
                "populated_records": 4720,
                "top_values": [
                    {"value": "1NO+1NC", "count": 1200},
                    {"value": "1 NO + 1 NC", "count": 450},
                    {"value": "1NO 1NC", "count": 230},
                    {"value": "2NO", "count": 980},
                    {"value": "2 NO", "count": 340},
                    {"value": "2NC", "count": 750},
                    {"value": "3NO+1NC", "count": 560}
                ]
            },
            "reasoning": """
            STRING ANALYSIS:
            1. Pattern Extraction from observed values:
               - Structure: [digit]NO([separator][digit]NC)?
               - Separators observed: '+', ' + ', ' '
               - Components: NO (normally open), NC (normally closed)

            2. Character Composition:
               - Digits: 1, 2, 3 (leading count)
               - Letters: NO, NC (contact type)
               - Delimiters: +, space (inconsistent)

            3. Semantic Clustering:
               - "1NO+1NC" cluster: 1NO+1NC(1200), 1 NO + 1 NC(450), 1NO 1NC(230) = 1880
               - "2NO" cluster: 2NO(980), 2 NO(340) = 1320
               - Canonical forms: most compact (no spaces)

            4. Regex Derivation:
               - Canonical pattern: ^\\d+NO(\\+\\d+NC)?$|^\\d+NC$
               - Covers: 1NO+1NC, 2NO, 2NC, 3NO+1NC

            K-FOLD VALIDATION:
            - Pattern holds for 1200+980+750+560 = 3490/4720 = 73.9% (canonical)
            - 26.1% need normalization - consistent across folds

            GENERALIZATION: Regex from structural analysis + normalization mapping
            """,
            "rules": [
                {
                    "attribute_name": "zz_Contact Configuration",
                    "rule_category": "Validity",
                    "rule_type": "FORMAT_PATTERN",
                    "rule_expression": "Contact config matches pattern: digit + NO/NC + optional digit + NC",
                    "rule_expression_sql": "SELECT * FROM products WHERE \"zz_Contact Configuration\" IS NOT NULL AND REGEXP_REPLACE(\"zz_Contact Configuration\", ' ', '') NOT REGEXP '^[0-9]+NO(\\+?[0-9]+NC)?$|^[0-9]+NC$'",
                    "rule_expression_python": "df[df['zz_Contact Configuration'].notna() & ~df['zz_Contact Configuration'].str.replace(' ', '').str.match(r'^\\d+NO(\\+?\\d+NC)?$|^\\d+NC$')]",
                    "severity": "Medium",
                    "description": "Pattern derived from data structure: [count]NO([+][count]NC)? or [count]NC",
                    "threshold_percent": 55.0,
                    "support": 0.472,
                    "confidence": 0.95,
                    "derived_from": "Regex built from structural analysis of top_values character composition",
                    "sample_valid_values": ["1NO+1NC", "2NO", "2NC", "3NO+1NC", "1 NO + 1 NC"],
                    "sample_invalid_values": ["ABC", "Open", "N/A", "1-NO"],
                    "generalization_method": "OBSERVED_PATTERN"
                },
                {
                    "attribute_name": "zz_Contact Configuration",
                    "rule_category": "Normalization",
                    "rule_type": "FORMAT_STANDARDIZATION",
                    "rule_expression": "Remove spaces, use '+' separator: '1 NO + 1 NC' → '1NO+1NC'",
                    "rule_expression_sql": "SELECT * FROM products WHERE \"zz_Contact Configuration\" IS NOT NULL AND \"zz_Contact Configuration\" NOT REGEXP '^[0-9]+NO(\\+[0-9]+NC)?$|^[0-9]+NC$'",
                    "rule_expression_python": "df[df['zz_Contact Configuration'].notna() & ~df['zz_Contact Configuration'].astype(str).str.match(r'^\\d+NO(\\+\\d+NC)?$|^\\d+NC$')]",
                    "severity": "Low",
                    "description": "26.1% records have spacing variations. Normalize to compact form: XNO+YNC",
                    "threshold_percent": 55.0,
                    "support": 0.472,
                    "confidence": 0.739,
                    "derived_from": "Identified canonical form (no spaces) has highest frequency per semantic cluster",
                    "sample_valid_values": ["1NO+1NC", "2NO", "2NC", "3NO+1NC"],
                    "sample_invalid_values": ["1 NO + 1 NC", "1NO 1NC", "2 NO"],
                    "generalization_method": "CLUSTERING"
                }
            ]
        },
        # Example 7: CATEGORICAL type - Low cardinality with enumeration
        {
            "attribute_name": "zz_Frequency",
            "data_type_category": "CATEGORICAL",
            "profiling": {
                "datatype": "Categorical",
                "missing_percentage": 78.5,
                "cardinality": "0.8%",
                "total_records": 10000,
                "populated_records": 2150,
                "top_values": [
                    {"value": "50/60 Hz", "count": 3200},
                    {"value": "50 Hz", "count": 1100},
                    {"value": "60 Hz", "count": 890},
                    {"value": "DC", "count": 450}
                ]
            },
            "reasoning": """
            CATEGORICAL ANALYSIS:
            1. Cardinality: 0.8% (~80 unique) but top 4 values cover majority
            2. Frequency Distribution:
               - 50/60 Hz: 56.7% support within populated records (dominant)
               - 50 Hz: 19.5%
               - 60 Hz: 15.8%
               - DC: 8.0%
            3. Value Set: 4 distinct values cover ~100% of populated data

            K-FOLD VALIDATION:
            - All 4 values have sufficient counts (>400) for fold stability
            - Value set would be consistent across all folds
            - Support for each value > 5% threshold

            GENERALIZATION: Complete enumeration of low-cardinality domain
            """,
            "rules": [
                {
                    "attribute_name": "zz_Frequency",
                    "rule_category": "Validity",
                    "rule_type": "VALUE_SET",
                    "rule_expression": "zz_Frequency IN ('50/60 Hz', '50 Hz', '60 Hz', 'DC')",
                    "rule_expression_sql": "SELECT * FROM products WHERE \"zz_Frequency\" IS NOT NULL AND \"zz_Frequency\" NOT IN ('50/60 Hz', '50 Hz', '60 Hz', 'DC')",
                    "rule_expression_python": "df[df['zz_Frequency'].notna() & ~df['zz_Frequency'].isin(['50/60 Hz', '50 Hz', '60 Hz', 'DC'])]",
                    "severity": "Medium",
                    "description": "Values could be one of the 4 observed frequency categories. All have >5% support within populated records.",
                    "threshold_percent": 80.0,
                    "support": 0.215,
                    "confidence": 0.99,
                    "derived_from": "Exhaustive enumeration of top_values covering 100% of populated records",
                    "sample_valid_values": ["50/60 Hz", "50 Hz", "60 Hz", "DC"],
                    "sample_invalid_values": ["100 Hz", "Unknown", "N/A"],
                    "generalization_method": "ENUMERATION"
                },
                {
                    "attribute_name": "zz_Frequency",
                    "rule_category": "Normalization",
                    "rule_type": "VALUE_STANDARDIZATION",
                    "rule_expression": "Normalize spacing: '50Hz' → '50 Hz'",
                    "rule_expression_sql": "SELECT * FROM products WHERE \"zz_Frequency\" IS NOT NULL AND \"zz_Frequency\" NOT IN ('50 Hz', '60 Hz', '50/60 Hz', 'DC')",
                    "rule_expression_python": "df[df['zz_Frequency'].notna() & ~df['zz_Frequency'].isin(['50 Hz', '60 Hz', '50/60 Hz', 'DC'])]",
                    "severity": "Low",
                    "description": "Standardize to canonical forms with space before Hz unit.",
                    "threshold_percent": 80.0,
                    "support": 0.215,
                    "confidence": 0.95,
                    "derived_from": "Canonical forms identified by highest frequency in semantic clusters",
                    "sample_valid_values": ["50 Hz", "60 Hz", "50/60 Hz", "DC"],
                    "sample_invalid_values": ["50Hz", "60Hz", "50/60Hz"],
                    "generalization_method": "CLUSTERING"
                }
            ]
        },
        # Example 8: STRING type - Complex pattern with value/unit structure
        {
            "attribute_name": "zz_Coil Voltage",
            "data_type_category": "STRING",
            "profiling": {
                "datatype": "Categorical",
                "missing_percentage": 35.2,
                "cardinality": "4.2%",
                "total_records": 10000,
                "populated_records": 6480,
                "top_values": [
                    {"value": "24 V DC", "count": 2800},
                    {"value": "24V DC", "count": 650},
                    {"value": "24VDC", "count": 420},
                    {"value": "230 V AC", "count": 1900},
                    {"value": "230V AC", "count": 380},
                    {"value": "12 V DC", "count": 1200},
                    {"value": "48 V DC", "count": 890}
                ]
            },
            "reasoning": """
            STRING ANALYSIS:
            1. Pattern Extraction:
               - Structure: [numeric value] + [optional space] + V + [optional space] + [AC|DC]
               - Components: voltage number, unit (V), current type (AC/DC)

            2. Character Composition:
               - Numeric prefix: 12, 24, 48, 230 (discrete voltage values)
               - Unit: V (always present)
               - Suffix: AC or DC (current type)
               - Spacing variations: with/without spaces

            3. Semantic Clustering for "24V DC":
               - "24 V DC" (2800) - canonical (most frequent)
               - "24V DC" (650) - no space before V
               - "24VDC" (420) - no spaces at all
               - Total cluster: 3870 records

            4. Regex Derivation:
               - Canonical pattern: ^\\d+ V (AC|DC)$
               - Flexible pattern: ^\\d+\\s*V\\s*(AC|DC)$

            K-FOLD VALIDATION:
            - Canonical form "24 V DC" has 72.3% within its cluster (2800/3870)
            - Pattern holds across all observed values
            - Sufficient records per cluster for fold stability

            GENERALIZATION: Structural regex + normalization to canonical spacing
            """,
            "rules": [
                {
                    "attribute_name": "zz_Coil Voltage",
                    "rule_category": "Validity",
                    "rule_type": "FORMAT_PATTERN",
                    "rule_expression": "Voltage matches pattern: [number] V [AC|DC]",
                    "rule_expression_sql": "SELECT * FROM products WHERE \"zz_Coil Voltage\" IS NOT NULL AND REGEXP_REPLACE(\"zz_Coil Voltage\", ' ', '') NOT REGEXP '^[0-9]+V(AC|DC)$'",
                    "rule_expression_python": "df[df['zz_Coil Voltage'].notna() & ~df['zz_Coil Voltage'].str.replace(' ', '').str.match(r'^\\d+V(AC|DC)$')]",
                    "severity": "Medium",
                    "description": "Pattern derived: numeric voltage + V + AC/DC. All observed values follow this structure.",
                    "threshold_percent": 40.0,
                    "support": 0.648,
                    "confidence": 0.98,
                    "derived_from": "Regex built from structural analysis: [number][space?]V[space?][AC|DC]",
                    "sample_valid_values": ["24 V DC", "24V DC", "24VDC", "230 V AC"],
                    "sample_invalid_values": ["24 volts", "DC 24V", "24V", "high"],
                    "generalization_method": "OBSERVED_PATTERN"
                },
                {
                    "attribute_name": "zz_Coil Voltage",
                    "rule_category": "Normalization",
                    "rule_type": "FORMAT_STANDARDIZATION",
                    "rule_expression": "Normalize to canonical: 'XX V AC/DC' with proper spacing",
                    "rule_expression_sql": "SELECT * FROM products WHERE \"zz_Coil Voltage\" IS NOT NULL AND \"zz_Coil Voltage\" NOT REGEXP '^[0-9]+ V (AC|DC)$'",
                    "rule_expression_python": "df[df['zz_Coil Voltage'].notna() & ~df['zz_Coil Voltage'].astype(str).str.match(r'^\\d+ V (AC|DC)$')]",
                    "severity": "Low",
                    "description": "27.7% of '24V' cluster needs normalization (1070/3870). Canonical: space before V and after V.",
                    "threshold_percent": 40.0,
                    "support": 0.648,
                    "confidence": 0.78,
                    "derived_from": "Canonical form 'XX V DC' identified by max frequency within each voltage cluster",
                    "sample_valid_values": ["24 V DC", "230 V AC", "12 V DC", "48 V DC"],
                    "sample_invalid_values": ["24V DC", "24VDC", "230V AC"],
                    "generalization_method": "CLUSTERING"
                }
            ]
        }
    ]


def format_few_shot_examples(examples: List[Dict[str, Any]], include_reasoning: bool = True) -> str:
    """
    Format few-shot examples for inclusion in prompt.

    Args:
        examples: List of example dictionaries
        include_reasoning: Whether to include the reasoning section

    Returns:
        Formatted string for prompt
    """
    import json

    formatted = []
    for ex in examples[:3]:
        data_type = ex.get('data_type_category', 'UNKNOWN')
        reasoning = ex.get('reasoning', '').strip() if include_reasoning else ''

        example_text = f"""
### Example: {ex['attribute_name']} (Type: {data_type})
**Profiling Statistics:**
```json
{json.dumps(ex['profiling'], indent=2)}
```
"""
        if reasoning:
            example_text += f"""
**Reasoning Process:**
```
{reasoning}
```
"""
        example_text += f"""
**Derived Rules:**
```json
{json.dumps(ex['rules'], indent=2)}
```
"""
        formatted.append(example_text)
    return "\n".join(formatted)


def get_data_population_category(missing_percentage: float) -> str:
    """
    Categorize the data population level based on missing percentage.

    Args:
        missing_percentage: The percentage of missing values

    Returns:
        Human-readable category description
    """
    if missing_percentage >= 95:
        return "SPARSE/OPTIONAL (rarely populated - only for specific products)"
    elif missing_percentage >= 80:
        return "VERY LOW POPULATION (mostly empty)"
    elif missing_percentage >= 50:
        return "PARTIALLY POPULATED (about half empty)"
    elif missing_percentage >= 20:
        return "MODERATELY POPULATED"
    elif missing_percentage >= 5:
        return "WELL POPULATED"
    else:
        return "REQUIRED/NEARLY COMPLETE (effectively mandatory)"


def get_type_category(datatype: str) -> str:
    """
    Map data type to category for type-specific analysis.

    Args:
        datatype: The datatype from profiling

    Returns:
        Type category: NUMERIC, STRING, or CATEGORICAL
    """
    datatype_lower = datatype.lower()
    if datatype_lower in ['numeric', 'integer', 'float', 'decimal', 'number']:
        return "NUMERIC"
    elif datatype_lower in ['categorical', 'enum', 'boolean']:
        return "CATEGORICAL"
    else:
        return "STRING"


def build_derivation_prompt(
    attribute_analysis: Dict[str, Any],
    dataset_context: Dict[str, Any],
    few_shot_examples: List[Dict[str, Any]],
    thresholds: Dict[str, float] = None,
) -> str:
    """
    Build the complete prompt for rule derivation with type-specific guidance
    and support/confidence thresholds.

    Args:
        attribute_analysis: Analysis results for the attribute
        dataset_context: Overall dataset metadata
        few_shot_examples: Example rule derivations
        thresholds: Optional custom thresholds for support/confidence

    Returns:
        Complete prompt string
    """
    import json

    t = thresholds or RULE_THRESHOLDS
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

    prompt = f"""
## Dataset Context
- **Dataset Name:** {dataset_context.get('dataset_name', 'Product_Data')}
- **Domain:** {dataset_context.get('domain', 'Product')}
- **Total Records:** {total_records:,}

## Attribute to Analyze
- **Attribute Name:** {attribute_analysis['attribute_name']}
- **Data Type:** {attribute_analysis['datatype']}
- **Type Category:** {type_category}
- **Missing Percentage:** {missing_pct}%
- **Populated Records:** {populated_info}
- **Data Population Category:** {population_category}
- **Cardinality:** {attribute_analysis['cardinality']}
- **Range:** {attribute_analysis.get('range', 'N/A')}
- **Top Values:**
```json
{json.dumps(attribute_analysis['top_values'][:10], indent=2)}
```
{numeric_pattern_info}
## Recommended Rule Types
{', '.join(attribute_analysis.get('recommended_rules', []))}

## Rule Acceptance Thresholds
- **Minimum Support:** {t['min_support']} ({t['min_support']*100}% of data must exhibit pattern)
- **Minimum Confidence:** {t['min_confidence']} ({t['min_confidence']*100}% compliance required)
- **High Confidence:** {t['high_confidence']} (for Critical/High severity rules)
- **K-Fold Consistency:** Rule must hold in {t['min_fold_consistency']*100}% of data splits

{type_guidance}

{data_driven_guidance}

## Few-Shot Examples
{formatted_examples}

## Instructions
Generate DQ rules for "{attribute_analysis['attribute_name']}" using the type-specific analysis approach.

**REASONING PROCESS (show your work):**
1. Apply {type_category} analysis steps to the profiling data
2. Calculate support and confidence for each candidate rule
3. Reject rules with confidence < {t['min_confidence']}
4. Consider k-fold consistency - would rule hold across data splits?

**RULE REQUIREMENTS:**
1. Each rule MUST include: support, confidence, generalization_method
2. Support = applicable_records / total_records
3. Confidence = compliant_records / applicable_records
4. Only accept rules where confidence >= {t['min_confidence']}
5. Sample values MUST come from actual top_values

**CRITICAL - DESCRIPTION REQUIREMENT:**
- Do NOT list actual observed values in the description field
- Use GENERALIZED descriptions with ranges, counts, or patterns:
  - GOOD: "Values could be numeric within the range X to Y"
  - GOOD: "Values could be one of the N observed categories"
  - GOOD: "Values should follow the pattern: 3 digits, dash, 4 digits"
  - BAD: "Values must match one of the observed values: 2.0, 3.0, 5.0, 7.5, 10.0"
- **For CATEGORICAL fields with ALL NUMERIC values**: Use range description "Values could be between min and max"

**OUTPUT FORMAT:**
Return a JSON array of rule objects. Each rule must have:
- rule_id, attribute_name, rule_category, rule_type
- rule_expression, rule_expression_sql, rule_expression_python
- severity, description, threshold_percent
- support (0.0-1.0), confidence (0.0-1.0)
- derived_from, sample_valid_values, sample_invalid_values
- generalization_method (OBSERVED_PATTERN | STATISTICAL_BOUND | ENUMERATION | CLUSTERING)

**IMPORTANT:** Return ONLY a valid JSON array. No other text.

Generate the rules now:
"""
    return prompt
