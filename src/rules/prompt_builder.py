"""Build prompts for GPT-4o rule generation."""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PromptBuilder:
    """
    Build prompts for GPT-4o to generate data quality rules.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the prompt builder.

        Args:
            config: Configuration dictionary.
        """
        self.config = config or {}
        self.template_path = Path("prompts/data_quality_rules_prompt.xml")

    def load_template(self) -> str:
        """
        Load the XML prompt template.

        Returns:
            Template string.
        """
        # Try multiple paths
        paths_to_try = [
            self.template_path,
            Path("prompts/data_quality_rules_derivation_prompt_v2.xml"),
            Path("prompts/data_quality_rules_prompt.xml"),
        ]

        for path in paths_to_try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()

        logger.warning("Template not found, using default prompt structure")
        return self._get_default_template()

    def _get_default_template(self) -> str:
        """Get default prompt template."""
        return """
You are an expert Data Quality Architect analyzing manufacturers' contactors and relays data.

Analyze the following data sources and derive comprehensive data quality rules:

## Cross-Tab Data (Priority Attributes)
{{CROSSTAB_DATA}}

## Profiling Statistics
{{PROFILING_STATISTICS}}

## Wikipedia Definitions
{{WIKIPEDIA_DEFINITIONS}}

## RAG Technical Specifications
{{RAG_TECHNICAL_SPECS}}

## Matched Attributes (GENERATE RULES ONLY FOR THESE)
{{MATCHED_ATTRIBUTES}}

IMPORTANT: Generate data quality rules ONLY for the matched attributes listed above.

For EACH matched attribute, generate at least 2-3 rules covering different categories:
- COMPLETENESS: Is the field mandatory? Under what conditions?
- VALIDITY: What are valid data types, ranges, formats based on ABB specs?
- CONSISTENCY: How should this field relate to other fields?
- ACCURACY: What precision/tolerance is required per IEC 60947?

CRITICAL REQUIREMENTS:
1. The "attribute" field MUST contain the canonical attribute name (e.g., "rated_current", "coil_voltage")
2. The "validation_logic.expression" MUST contain a Python-like validation expression
3. Include specific values from the RAG specifications (voltage ranges, current limits, etc.)

Return a JSON object with the following structure:
{
    "rules": [
        {
            "rule_id": "DQR_001",
            "attribute": "rated_current",
            "category": "VALIDITY",
            "subtype": "range_check",
            "description": "Rated current (Ie) must be within valid contactor range per IEC 60947",
            "validation_logic": {
                "expression": "value >= 0.1 and value <= 2050",
                "parameters": {"min": 0.1, "max": 2050, "unit": "A"},
                "error_message": "Rated current must be between 0.1A and 2050A",
                "severity": "ERROR"
            },
            "source_evidence": [
                {
                    "source_type": "rag",
                    "source_reference": "ABB_Contactor_Relays.pdf",
                    "excerpt": "AF contactors range from 9A to 2050A",
                    "confidence": 0.95
                }
            ],
            "business_impact": "Invalid current ratings may cause equipment failure or safety hazards",
            "implementation_notes": "Check against AC-3 category ratings"
        },
        {
            "rule_id": "DQR_002",
            "attribute": "coil_voltage",
            "category": "VALIDITY",
            "subtype": "enumeration",
            "description": "Coil voltage must be a standard control circuit voltage",
            "validation_logic": {
                "expression": "value in [24, 48, 110, 220, 230, 240, 400, 415, 480]",
                "parameters": {"valid_values": [24, 48, 110, 220, 230, 240, 400, 415, 480], "unit": "V"},
                "error_message": "Coil voltage must be a standard control circuit voltage",
                "severity": "ERROR"
            },
            "source_evidence": [
                {
                    "source_type": "rag",
                    "source_reference": "ABB_Contactor_Relays.pdf",
                    "excerpt": "Control circuit voltages: 24V DC/AC, 110V, 220-240V, 380-415V",
                    "confidence": 0.92
                }
            ],
            "business_impact": "Incorrect coil voltage will prevent proper contactor operation",
            "implementation_notes": "Validate against regional voltage standards"
        }
    ]
}

Generate comprehensive rules following these examples. Each rule must have ALL fields populated.
"""

    def build_prompt(
        self,
        crosstab_data: str,
        profiling_stats: str,
        wikipedia_defs: str,
        rag_specs: str,
        matched_attributes: list[str] | None = None,
    ) -> str:
        """
        Build the complete prompt with data sources.

        Args:
            crosstab_data: Formatted cross-tab data.
            profiling_stats: Formatted profiling statistics.
            wikipedia_defs: Formatted Wikipedia definitions.
            rag_specs: Formatted RAG specifications.
            matched_attributes: Optional list of attributes to focus on.

        Returns:
            Complete prompt string.
        """
        template = self.load_template()

        # Replace placeholders
        prompt = template.replace("{{CROSSTAB_DATA}}", crosstab_data)
        prompt = prompt.replace("{{PROFILING_STATISTICS}}", profiling_stats)
        prompt = prompt.replace("{{WIKIPEDIA_DEFINITIONS}}", wikipedia_defs)
        prompt = prompt.replace("{{RAG_TECHNICAL_SPECS}}", rag_specs)

        # Format matched attributes with clear instructions
        if matched_attributes:
            # Deduplicate and get unique canonical names
            unique_attrs = list(set(matched_attributes))
            attrs_formatted = "\n".join(f"- {attr}" for attr in unique_attrs[:20])
            prompt = prompt.replace(
                "{{MATCHED_ATTRIBUTES}}",
                f"Generate rules for these {len(unique_attrs)} matched attributes:\n{attrs_formatted}"
            )
        else:
            prompt = prompt.replace(
                "{{MATCHED_ATTRIBUTES}}",
                "No specific attributes provided - analyze all available attributes."
            )

        logger.debug(f"Built prompt with {len(prompt)} characters")
        return prompt

    def build_system_prompt(self) -> str:
        """
        Build the system prompt for GPT-4o.

        Returns:
            System prompt string.
        """
        return """You are an expert Data Quality Architect, Manufacturing Domain Specialist,
and Python Developer with extensive experience in:
- Industrial data governance and quality management
- Electrical equipment specifications (contactors, relays, switchgear)
- ABB product catalogs and technical documentation
- RAG system architecture and vector databases

Your task is to analyze multiple data sources and derive comprehensive data quality rules
for manufacturers' contactors and relays data.

CRITICAL RULES:
1. Only generate rules for attributes found in BOTH the Cross-Tab AND RAG specifications
2. Each rule must have clear validation logic that can be implemented in code
3. Include source evidence with specific references
4. Consider ABB-specific terminology and standards (IEC 60947)

Return your response as valid JSON only, no additional text."""

    def build_attribute_prompt(
        self,
        attribute: str,
        crosstab_info: str,
        rag_specs: str,
        profiling_stats: str,
    ) -> str:
        """
        Build a focused prompt for a single attribute.

        Args:
            attribute: Attribute name.
            crosstab_info: Cross-tab information for this attribute.
            rag_specs: RAG specifications for this attribute.
            profiling_stats: Profiling statistics for this attribute.

        Returns:
            Focused prompt string.
        """
        return f"""
Generate data quality rules for the attribute: {attribute}

## Cross-Tab Information
{crosstab_info}

## Technical Specifications (from ABB documentation)
{rag_specs}

## Profiling Statistics
{profiling_stats}

Generate comprehensive rules covering:
1. COMPLETENESS - Is this a mandatory field?
2. VALIDITY - Valid ranges, formats, enumerated values
3. CONSISTENCY - Relationships with other fields
4. ACCURACY - Required precision

Return JSON with rules for this attribute only.
"""

    def format_rag_specs(self, chunks: list[dict[str, Any]]) -> str:
        """
        Format RAG chunks for inclusion in prompt.

        Args:
            chunks: List of RAG chunk dictionaries.

        Returns:
            Formatted string.
        """
        lines = ["Technical Specifications from ABB Documentation:"]
        lines.append("-" * 50)

        for i, chunk in enumerate(chunks[:15], 1):  # Limit to avoid token limits
            content = chunk.get("content", "")[:500]  # Truncate long chunks
            source = chunk.get("metadata", {}).get("source", "Unknown")
            page = chunk.get("metadata", {}).get("page_number", "?")

            lines.append(f"\n[Spec {i}] Source: {source}, Page: {page}")
            lines.append(content)
            lines.append("")

        return "\n".join(lines)
