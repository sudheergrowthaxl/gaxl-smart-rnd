"""Generate data quality rules using GPT-4o."""

import json
import logging
import os
from typing import Any

from openai import OpenAI

from src.rules.prompt_builder import PromptBuilder
from src.rules.rule_models import (
    DataQualityRule,
    RuleCategory,
    RuleSet,
    RuleSubtype,
    SourceEvidence,
    ValidationLogic,
)
from src.utils.exceptions import RuleGenerationError

logger = logging.getLogger(__name__)


class RuleGenerator:
    """
    Generate data quality rules using GPT-4o.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the rule generator.

        Args:
            config: Configuration dictionary with OpenAI settings.
        """
        self.config = config or {}
        openai_config = self.config.get("openai", {})

        api_key = openai_config.get("api_key") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuleGenerationError(
                "OpenAI API key not found",
                details={"hint": "Set OPENAI_API_KEY environment variable"},
            )

        self.client = OpenAI(api_key=api_key)
        self.model = openai_config.get("chat_model", "gpt-4o")
        self.temperature = openai_config.get("temperature", 0.3)
        self.max_tokens = openai_config.get("max_tokens", 4096)

        self.prompt_builder = PromptBuilder(config)

    def generate_rules(
        self,
        crosstab_data: str,
        profiling_stats: str,
        wikipedia_defs: str,
        rag_specs: str,
        matched_attributes: list[str] | None = None,
    ) -> RuleSet:
        """
        Generate data quality rules from all data sources.

        Args:
            crosstab_data: Formatted cross-tab data.
            profiling_stats: Formatted profiling statistics.
            wikipedia_defs: Formatted Wikipedia definitions.
            rag_specs: Formatted RAG specifications.
            matched_attributes: Optional list of matched attributes.

        Returns:
            RuleSet containing generated rules.

        Raises:
            RuleGenerationError: If rule generation fails.
        """
        logger.info("Generating data quality rules...")

        # Build prompts
        system_prompt = self.prompt_builder.build_system_prompt()
        user_prompt = self.prompt_builder.build_prompt(
            crosstab_data=crosstab_data,
            profiling_stats=profiling_stats,
            wikipedia_defs=wikipedia_defs,
            rag_specs=rag_specs,
            matched_attributes=matched_attributes,
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            content = response.choices[0].message.content

            if not content:
                raise RuleGenerationError("Empty response from GPT-4o")

            # Parse response
            result = json.loads(content)
            rule_set = self._parse_rules(result)

            logger.info(f"Generated {len(rule_set.rules)} rules")
            return rule_set

        except json.JSONDecodeError as e:
            raise RuleGenerationError(
                f"Failed to parse GPT-4o response as JSON: {e}",
                details={"error": str(e)},
            )
        except Exception as e:
            raise RuleGenerationError(
                f"Rule generation failed: {e}",
                details={"error": str(e)},
            )

    def _parse_rules(self, response_data: dict[str, Any]) -> RuleSet:
        """
        Parse GPT-4o response into RuleSet.

        Args:
            response_data: Parsed JSON response.

        Returns:
            RuleSet with parsed rules.
        """
        rule_set = RuleSet()

        rules_data = response_data.get("rules", [])

        for i, rule_data in enumerate(rules_data):
            try:
                rule = self._parse_single_rule(rule_data, i)
                rule_set.add_rule(rule)
            except Exception as e:
                logger.warning(f"Failed to parse rule {i}: {e}")
                continue

        return rule_set

    def _parse_single_rule(
        self, rule_data: dict[str, Any], index: int
    ) -> DataQualityRule:
        """
        Parse a single rule from response data.

        Args:
            rule_data: Rule dictionary from response.
            index: Rule index for ID generation.

        Returns:
            Parsed DataQualityRule.
        """
        # Parse validation logic
        validation_data = rule_data.get("validation_logic", {})
        validation_logic = ValidationLogic(
            expression=validation_data.get("expression", ""),
            parameters=validation_data.get("parameters", {}),
            error_message=validation_data.get("error_message", "Validation failed"),
            severity=validation_data.get("severity", "ERROR"),
        )

        # Parse source evidence
        evidence_list = []
        for ev_data in rule_data.get("source_evidence", []):
            evidence = SourceEvidence(
                source_type=ev_data.get("source_type", "unknown"),
                source_reference=ev_data.get("source_reference", ""),
                excerpt=ev_data.get("excerpt", ""),
                confidence=ev_data.get("confidence", 0.5),
            )
            evidence_list.append(evidence)

        # Parse category and subtype
        category_str = rule_data.get("category", "VALIDITY").upper()
        try:
            category = RuleCategory(category_str)
        except ValueError:
            category = RuleCategory.VALIDITY

        subtype_str = rule_data.get("subtype", "data_type").lower()
        try:
            subtype = RuleSubtype(subtype_str)
        except ValueError:
            subtype = RuleSubtype.DATA_TYPE

        return DataQualityRule(
            rule_id=rule_data.get("rule_id", f"DQR_{index + 1:03d}"),
            attribute=rule_data.get("attribute", "unknown"),
            category=category,
            subtype=subtype,
            description=rule_data.get("description", ""),
            validation_logic=validation_logic,
            source_evidence=evidence_list,
            business_impact=rule_data.get("business_impact", ""),
            implementation_notes=rule_data.get("implementation_notes", ""),
        )

    def generate_rules_for_attribute(
        self,
        attribute: str,
        crosstab_info: str,
        rag_specs: str,
        profiling_stats: str,
    ) -> list[DataQualityRule]:
        """
        Generate rules for a single attribute.

        Args:
            attribute: Attribute name.
            crosstab_info: Cross-tab info for attribute.
            rag_specs: RAG specs for attribute.
            profiling_stats: Profiling stats for attribute.

        Returns:
            List of generated rules.
        """
        prompt = self.prompt_builder.build_attribute_prompt(
            attribute=attribute,
            crosstab_info=crosstab_info,
            rag_specs=rag_specs,
            profiling_stats=profiling_stats,
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": self.prompt_builder.build_system_prompt(),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=self.temperature,
                max_tokens=2048,
            )

            content = response.choices[0].message.content
            if not content:
                return []

            result = json.loads(content)
            rules_data = result.get("rules", [])

            rules = []
            for i, rule_data in enumerate(rules_data):
                try:
                    rule = self._parse_single_rule(rule_data, i)
                    rules.append(rule)
                except Exception as e:
                    logger.warning(f"Failed to parse rule for {attribute}: {e}")

            return rules

        except Exception as e:
            logger.error(f"Failed to generate rules for {attribute}: {e}")
            return []
