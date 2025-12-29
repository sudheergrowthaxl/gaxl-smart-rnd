"""LangGraph edge routing functions for DQ rule derivation workflow."""

from typing import Literal
from ..models.agent_state import AgentState
from ..config.settings import get_settings


def should_process_more_attributes(state: AgentState) -> Literal["continue", "complete"]:
    """
    Determine if there are more attributes to process.

    This edge function checks:
    - If there's a next attribute to process
    - If we've hit the iteration limit

    Returns:
        "continue" if more attributes remain, "complete" otherwise
    """
    settings = get_settings()

    current_attr = state.get('current_attribute')

    # No more attributes to process
    if current_attr is None:
        return "complete"

    # Check iteration limit (safety)
    iteration_count = state.get('iteration_count', 0)
    if iteration_count >= settings.max_iterations:
        print(f"  Reached iteration limit ({settings.max_iterations})")
        return "complete"

    return "continue"
