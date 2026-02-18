"""LangGraph state for normalisation rules derivation."""

import operator
from typing import Annotated, TypedDict


class RuleDerivationState(TypedDict, total=False):
    """State for the rule derivation graph."""

    # Current attribute being processed
    current_attribute: dict
    # Web search context for this attribute (from Tavily standards search)
    web_context: str
    # Manufacturer catalog context (from Tavily manufacturer search)
    manufacturer_context: str
    # Curated combined context string (customer + standards + manufacturer)
    curated_values: str
    # Few-shot examples text
    few_shot_examples: str
    # Domain (e.g. Contactors)
    domain: str
    # Whether to call Tavily for web context
    use_tavily: bool
    # Tavily search depth ("basic" or "advanced")
    search_depth: str
    # Path to log file for Tavily responses (optional)
    tavily_log_path: str
    # List of manufacturers to search for catalog values
    manufacturers: list[str]
    # Accumulated rules (reducer appends when node returns {"rules": [...]})
    rules: Annotated[list[str], operator.add]
    # Last error if any
    error: str
