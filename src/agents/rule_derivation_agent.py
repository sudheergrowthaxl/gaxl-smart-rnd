"""RuleDerivationAgent - Uses GPT-4o to derive DQ rules from profiling statistics."""

import json
import re
from typing import List, Dict, Any, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from ..models.dq_rule import DQRule
from ..prompts.rule_derivation_prompt import (
    get_system_prompt,
    get_few_shot_examples,
    build_derivation_prompt,
)
from ..config.settings import get_settings


class RuleDerivationAgent:
    """
    Agent that uses GPT-4o to derive DQ rules from profiling statistics.

    This agent:
    - Takes profiling statistics for an attribute
    - Uses few-shot prompting with examples from the XML template
    - Generates comprehensive DQ rules with SQL and Python implementations
    """

    def __init__(
        self,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """
        Initialize the RuleDerivationAgent.

        Args:
            model: OpenAI model to use (default: gpt-4o)
            temperature: Temperature for generation (default: 0.1)
            max_tokens: Maximum tokens for response (default: 8000)
        """
        settings = get_settings()

        self.model = model or settings.openai_model
        self.temperature = temperature if temperature is not None else settings.temperature
        self.max_tokens = max_tokens or settings.max_tokens

        self.llm = ChatOpenAI(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            api_key=settings.openai_api_key,
        )

    def derive_rules_for_attribute(
        self,
        attribute_analysis: Dict[str, Any],
        dataset_context: Dict[str, Any],
        few_shot_examples: Optional[List[Dict]] = None,
    ) -> List[DQRule]:
        """
        Derive DQ rules for a single attribute using LLM.

        Args:
            attribute_analysis: Profiling stats and recommendations for the attribute
            dataset_context: Overall dataset metadata (name, domain, total records)
            few_shot_examples: Example rule derivations from XML template

        Returns:
            List of derived DQRule objects
        """
        if few_shot_examples is None:
            few_shot_examples = get_few_shot_examples()

        # Build the prompt
        user_prompt = build_derivation_prompt(
            attribute_analysis,
            dataset_context,
            few_shot_examples,
        )

        # Create messages
        messages = [
            SystemMessage(content=get_system_prompt()),
            HumanMessage(content=user_prompt),
        ]

        # Call the LLM
        try:
            response = self.llm.invoke(messages)
            rules = self._parse_rules_from_response(
                response.content,
                attribute_analysis['attribute_name'],
            )
            return rules
        except Exception as e:
            print(f"Error deriving rules for {attribute_analysis['attribute_name']}: {e}")
            return []

    def _parse_rules_from_response(
        self,
        response_content: str,
        attribute_name: str,
    ) -> List[DQRule]:
        """
        Parse LLM response into DQRule objects.

        Args:
            response_content: Raw response from LLM
            attribute_name: Name of the attribute for error context

        Returns:
            List of parsed DQRule objects
        """
        # Try to extract JSON array from response
        json_match = re.search(r'\[[\s\S]*\]', response_content)
        if not json_match:
            print(f"No valid JSON array found for {attribute_name}")
            return []

        try:
            rules_data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            print(f"JSON parse error for {attribute_name}: {e}")
            return []

        rules = []
        for i, rule_data in enumerate(rules_data):
            try:
                # Ensure required fields have defaults
                rule_data = self._ensure_rule_fields(rule_data, attribute_name, i)
                rule = DQRule(**rule_data)
                rules.append(rule)
            except Exception as e:
                print(f"Could not parse rule {i} for {attribute_name}: {e}")
                continue

        return rules

    def _ensure_rule_fields(
        self,
        rule_data: Dict[str, Any],
        attribute_name: str,
        index: int,
    ) -> Dict[str, Any]:
        """
        Ensure all required fields are present in rule data.

        Args:
            rule_data: Raw rule dictionary from LLM
            attribute_name: Attribute name for generating defaults
            index: Index for generating unique IDs

        Returns:
            Rule dictionary with all required fields
        """
        # Generate rule_id if missing
        if 'rule_id' not in rule_data:
            attr_clean = re.sub(r'[^a-zA-Z0-9]', '_', attribute_name).upper()
            category = rule_data.get('rule_category', 'VALIDITY')[:3].upper()
            rule_data['rule_id'] = f"DQ_{attr_clean}_{category}_{index+1:03d}"

        # Ensure rule_id starts with DQ_
        if not rule_data['rule_id'].startswith('DQ_'):
            rule_data['rule_id'] = 'DQ_' + rule_data['rule_id']

        # Set defaults for missing fields
        defaults = {
            'attribute_name': attribute_name,
            'rule_category': 'Validity',
            'rule_type': 'CUSTOM',
            'rule_expression': f"{attribute_name} validation",
            'rule_expression_sql': f"SELECT * FROM products WHERE \"{attribute_name}\" IS NULL",
            'rule_expression_python': f"df[df['{attribute_name}'].isna()]",
            'severity': 'Medium',
            'description': f"Validation rule for {attribute_name}",
            'threshold_percent': 5.0,
            'derived_from': 'profiling analysis',
            'confidence_score': 0.8,
            'sample_valid_values': [],
            'sample_invalid_values': [],
        }

        for field, default in defaults.items():
            if field not in rule_data or rule_data[field] is None:
                rule_data[field] = default

        # Ensure numeric fields are proper types
        if isinstance(rule_data['threshold_percent'], str):
            try:
                rule_data['threshold_percent'] = float(rule_data['threshold_percent'])
            except ValueError:
                rule_data['threshold_percent'] = 5.0

        if isinstance(rule_data['confidence_score'], str):
            try:
                rule_data['confidence_score'] = float(rule_data['confidence_score'])
            except ValueError:
                rule_data['confidence_score'] = 0.8

        # Ensure confidence_score is in valid range
        rule_data['confidence_score'] = max(0.0, min(1.0, rule_data['confidence_score']))
        rule_data['threshold_percent'] = max(0.0, min(100.0, rule_data['threshold_percent']))

        # Ensure list fields are lists
        if not isinstance(rule_data['sample_valid_values'], list):
            rule_data['sample_valid_values'] = []
        if not isinstance(rule_data['sample_invalid_values'], list):
            rule_data['sample_invalid_values'] = []

        # Convert list items to strings
        rule_data['sample_valid_values'] = [
            str(v) for v in rule_data['sample_valid_values']
        ]
        rule_data['sample_invalid_values'] = [
            str(v) for v in rule_data['sample_invalid_values']
        ]

        return rule_data

    def generate_sql_expression(
        self,
        rule: DQRule,
        table_name: str = "products",
    ) -> str:
        """
        Generate SQL validation query for a rule.

        Args:
            rule: DQRule object
            table_name: Name of the table for SQL

        Returns:
            SQL query string
        """
        attr = f'"{rule.attribute_name}"'

        templates = {
            "NOT_NULL": f"SELECT * FROM {table_name} WHERE {attr} IS NULL",
            "NOT_EMPTY": f"SELECT * FROM {table_name} WHERE {attr} IS NULL OR TRIM(CAST({attr} AS VARCHAR)) = ''",
            "VALUE_SET": f"SELECT * FROM {table_name} WHERE {attr} NOT IN ({{valid_values}}) AND {attr} IS NOT NULL",
            "RANGE": f"SELECT * FROM {table_name} WHERE CAST({attr} AS NUMERIC) < {{min}} OR CAST({attr} AS NUMERIC) > {{max}}",
            "PRIMARY_KEY": f"SELECT {attr}, COUNT(*) FROM {table_name} GROUP BY {attr} HAVING COUNT(*) > 1",
            "FORMAT_PATTERN": f"SELECT * FROM {table_name} WHERE {attr} NOT REGEXP '{{pattern}}'",
        }

        return templates.get(rule.rule_type, rule.rule_expression_sql)

    def generate_python_expression(self, rule: DQRule) -> str:
        """
        Generate Python/pandas validation expression for a rule.

        Args:
            rule: DQRule object

        Returns:
            Python expression string
        """
        attr = rule.attribute_name

        templates = {
            "NOT_NULL": f"df[df['{attr}'].isna()]",
            "NOT_EMPTY": f"df[df['{attr}'].isna() | (df['{attr}'].astype(str).str.strip() == '')]",
            "VALUE_SET": f"df[~df['{attr}'].isin({{valid_values}}) & df['{attr}'].notna()]",
            "RANGE": f"df[(pd.to_numeric(df['{attr}'], errors='coerce') < {{min}}) | (pd.to_numeric(df['{attr}'], errors='coerce') > {{max}})]",
            "PRIMARY_KEY": f"df[df.duplicated(subset=['{attr}'], keep=False)]",
            "FORMAT_PATTERN": f"df[~df['{attr}'].astype(str).str.match(r'{{pattern}}', na=False)]",
        }

        return templates.get(rule.rule_type, rule.rule_expression_python)

    def derive_rules_batch(
        self,
        attributes_analysis: List[Dict[str, Any]],
        dataset_context: Dict[str, Any],
    ) -> List[DQRule]:
        """
        Derive rules for multiple attributes.

        Args:
            attributes_analysis: List of attribute analysis dictionaries
            dataset_context: Overall dataset metadata

        Returns:
            List of all derived DQRule objects
        """
        all_rules = []
        few_shot_examples = get_few_shot_examples()

        for attr_analysis in attributes_analysis:
            print(f"Deriving rules for: {attr_analysis['attribute_name']}")
            rules = self.derive_rules_for_attribute(
                attr_analysis,
                dataset_context,
                few_shot_examples,
            )
            all_rules.extend(rules)
            print(f"  Generated {len(rules)} rules")

        return all_rules
