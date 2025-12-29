"""LangGraph workflow builder for DQ rule derivation."""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from ..models.agent_state import AgentState
from .nodes import (
    load_profiling_node,
    select_priority_attributes_node,
    derive_rules_node,
    validate_rules_node,
    refine_rules_node,
    format_output_node,
)
from .edges import should_process_more_attributes


def build_dq_workflow(use_checkpointer: bool = True):
    """
    Build the LangGraph workflow for DQ rule derivation.

    The workflow follows this structure:
    1. load_profiling: Load and parse profiling JSON
    2. select_priority_attributes: Choose attributes to process
    3. derive_rules: Use LLM to derive rules for current attribute
    4. validate_rules: Test rules against sample data
    5. (conditional) Loop back to derive_rules or continue to refine
    6. refine_rules: Adjust thresholds and deduplicate
    7. format_output: Export to JSON and Excel

    Args:
        use_checkpointer: Whether to use memory checkpointer

    Returns:
        Compiled LangGraph workflow
    """
    # Initialize the graph with state schema
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("load_profiling", load_profiling_node)
    workflow.add_node("select_priority_attributes", select_priority_attributes_node)
    workflow.add_node("derive_rules", derive_rules_node)
    workflow.add_node("validate_rules", validate_rules_node)
    workflow.add_node("refine_rules", refine_rules_node)
    workflow.add_node("format_output", format_output_node)

    # Define edges
    workflow.set_entry_point("load_profiling")

    # Linear flow for initial steps
    workflow.add_edge("load_profiling", "select_priority_attributes")
    workflow.add_edge("select_priority_attributes", "derive_rules")
    workflow.add_edge("derive_rules", "validate_rules")

    # Conditional edge for iteration
    workflow.add_conditional_edges(
        "validate_rules",
        should_process_more_attributes,
        {
            "continue": "derive_rules",
            "complete": "refine_rules",
        }
    )

    # Final steps
    workflow.add_edge("refine_rules", "format_output")
    workflow.add_edge("format_output", END)

    # Compile with optional checkpointer
    if use_checkpointer:
        memory = MemorySaver()
        return workflow.compile(checkpointer=memory)
    else:
        return workflow.compile()


def get_workflow_diagram() -> str:
    """
    Get ASCII diagram of the workflow.

    Returns:
        ASCII art representation of the workflow
    """
    return """
    ┌─────────────────────────────────────────────────────────────┐
    │                      DQ Rule Derivation                      │
    │                        LangGraph Workflow                    │
    └─────────────────────────────────────────────────────────────┘

                              ┌─────────┐
                              │  START  │
                              └────┬────┘
                                   │
                                   ▼
                        ┌──────────────────┐
                        │  load_profiling  │
                        │  ─────────────── │
                        │  • Load JSON     │
                        │  • Parse stats   │
                        │  • Get samples   │
                        └────────┬─────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │ select_priority_attrs  │
                    │ ────────────────────── │
                    │ • Filter attributes    │
                    │ • Set up iteration     │
                    └───────────┬────────────┘
                                │
                                ▼
              ┌─────────────────────────────────────┐
              │           derive_rules              │◄──────┐
              │ ─────────────────────────────────── │       │
              │ • Analyze attribute                 │       │
              │ • Call GPT-4o with few-shot prompt  │       │
              │ • Parse returned rules              │       │
              └──────────────────┬──────────────────┘       │
                                 │                          │
                                 ▼                          │
              ┌─────────────────────────────────────┐       │
              │          validate_rules             │       │
              │ ─────────────────────────────────── │       │
              │ • Execute Python expressions        │       │
              │ • Calculate pass/fail rates         │       │
              │ • Move to next attribute            │       │
              └──────────────────┬──────────────────┘       │
                                 │                          │
                                 ▼                          │
                    ┌────────────────────────┐              │
                    │   more_attributes?     │──── Yes ─────┘
                    └───────────┬────────────┘
                                │ No
                                ▼
                    ┌────────────────────────┐
                    │     refine_rules       │
                    │ ────────────────────── │
                    │ • Adjust thresholds    │
                    │ • Remove duplicates    │
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │    format_output       │
                    │ ────────────────────── │
                    │ • Export to JSON       │
                    │ • Export to Excel      │
                    │ • Generate summary     │
                    └───────────┬────────────┘
                                │
                                ▼
                           ┌─────────┐
                           │   END   │
                           └─────────┘
    """
