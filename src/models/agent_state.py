"""LangGraph agent state definitions."""

from typing import TypedDict, List, Dict, Any, Optional, Annotated
from operator import add
from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    """Result of validating a single rule against sample data."""

    rule_id: str = Field(..., description="ID of the validated rule")
    pass_count: int = Field(default=0, description="Number of records that passed")
    fail_count: int = Field(default=0, description="Number of records that failed")
    pass_rate: float = Field(default=0.0, description="Pass rate as percentage")
    sample_failures: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Sample of records that failed validation"
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "rule_id": self.rule_id,
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "pass_rate": self.pass_rate,
            "sample_failures": self.sample_failures,
        }


class AgentState(TypedDict, total=False):
    """
    State shared across all LangGraph nodes.

    This state is passed through the workflow and updated by each node.
    """

    # Input configuration
    raw_data_path: str
    profiling_path: str
    schema_path: str

    # Profiling data
    profiling_stats: Dict[str, Any]  # Dict of attribute name -> ProfilingResult
    sample_data: List[Dict[str, Any]]  # Sample records for validation
    total_records: int

    # Attribute processing
    attributes_to_process: List[str]
    current_attribute: Optional[str]

    # Rules
    candidate_rules: Annotated[List[Any], add]  # DQRule objects accumulated
    validated_rules: List[Any]  # Final validated rules

    # Validation results
    validation_results: List[Any]  # ValidationResult objects

    # Output paths
    output_json_path: str
    output_excel_path: str

    # Control flow
    iteration_count: int
    errors: List[str]

    # Dataset context
    dataset_context: Dict[str, Any]


def create_initial_state(
    raw_data_path: str,
    profiling_path: str,
    schema_path: str = "",
) -> AgentState:
    """Create initial agent state with default values."""
    return AgentState(
        raw_data_path=raw_data_path,
        profiling_path=profiling_path,
        schema_path=schema_path,
        profiling_stats={},
        sample_data=[],
        total_records=0,
        attributes_to_process=[],
        current_attribute=None,
        candidate_rules=[],
        validated_rules=[],
        validation_results=[],
        output_json_path="",
        output_excel_path="",
        iteration_count=0,
        errors=[],
        dataset_context={
            "dataset_name": "Contactors_Product_Data",
            "domain": "Product",
            "total_records": 0,
        },
    )
