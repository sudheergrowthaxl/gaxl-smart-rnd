"""LangGraph state for normalisation rules derivation."""

import operator
from typing import Annotated, TypedDict


class RuleDerivationState(TypedDict, total=False):
    """State for the rule derivation graph."""

    # Current attribute being processed
    current_attribute: dict
    # Web search context for this attribute (from Tavily)
    web_context: str
    # Few-shot examples text
    few_shot_examples: str
    # Domain (e.g. Contactors)
    domain: str
    # Whether to call Tavily for web context
    use_tavily: bool
    # Path to log file for Tavily responses (optional)
    tavily_log_path: str
    # Accumulated rules (reducer appends when node returns {"rules": [...]})
    rules: Annotated[list[str], operator.add]
    # Last error if any
    error: str
