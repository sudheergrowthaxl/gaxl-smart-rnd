"""Prompt templates for DQ rule derivation using LLM."""

from typing import List, Dict, Any

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

Output Format:
Generate rules as a JSON array. Each rule object must include ALL of these fields:
- rule_id: Unique identifier in format DQ_{ATTRIBUTE}_{CATEGORY}_{SEQUENCE}
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
            "rules": [
                {
                    "rule_id": "DQ_ZZ_NUMBER_OF_POLES_VALIDITY_001",
                    "attribute_name": "zz_Number of Poles",
                    "rule_category": "Validity",
                    "rule_type": "VALUE_SET",
                    "rule_expression": "zz_Number of Poles IN ('1', '2', '3', '4', '5')",
                    "rule_expression_sql": "SELECT * FROM products WHERE \"zz_Number of Poles\" NOT IN ('1', '2', '3', '4', '5') AND \"zz_Number of Poles\" IS NOT NULL",
                    "rule_expression_python": "df[~df['zz_Number of Poles'].isin(['1', '2', '3', '4', '5']) & df['zz_Number of Poles'].notna()]",
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
- **Range:** {attribute_analysis.get('range', 'N/A')}
- **Top Values:**
```json
{json.dumps(attribute_analysis['top_values'][:10], indent=2)}
```

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
