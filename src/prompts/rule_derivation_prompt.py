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

When deriving rules, you must:
1. Analyze the profiling statistics carefully
2. Generate rules that are actionable, measurable, and implementable
3. Provide both SQL and Python/pandas implementations
4. Set realistic thresholds based on current data quality
5. Assign appropriate severity levels based on business impact

Output Format:
Generate rules as a JSON array. Each rule object must include ALL of these fields:
- rule_id: Unique identifier in format DQ_{ATTRIBUTE}_{CATEGORY}_{SEQUENCE}
- attribute_name: Name of the attribute
- rule_category: One of (Completeness, Validity, Accuracy, Consistency, Uniqueness, Timeliness)
- rule_type: Specific type (NOT_NULL, VALUE_SET, RANGE, FORMAT_PATTERN, PRIMARY_KEY, etc.)
- rule_expression: Implementable rule logic
- rule_expression_sql: SQL query to find violations
- rule_expression_python: Python/pandas code to find violations
- severity: One of (Critical, High, Medium, Low)
- description: Business-friendly explanation
- threshold_percent: Acceptable failure rate (0-100)
- derived_from: Profiling statistic used
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

For each rule:
1. Use the exact rule_id format: DQ_{{ATTRIBUTE_NAME}}_{{CATEGORY}}_{{SEQUENCE}}
   - Replace spaces and special characters in attribute name with underscores
   - Use uppercase
2. Provide working SQL and Python expressions
3. Set realistic thresholds based on current data quality
4. Include sample valid and invalid values from the data

**IMPORTANT:** Return ONLY a valid JSON array of rule objects. Do not include any other text.

Generate the rules now:
"""
    return prompt
