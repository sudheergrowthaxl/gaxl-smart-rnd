"""LangGraph node implementations for DQ rule derivation workflow."""

from typing import Dict, Any
import pandas as pd

from ..models.agent_state import AgentState
from ..models.dq_rule import DQRule
from ..agents.data_profiler_agent import DataProfilerAgent
from ..agents.rule_derivation_agent import RuleDerivationAgent
from ..agents.rule_validation_agent import RuleValidationAgent
from ..agents.output_formatter_agent import OutputFormatterAgent
from ..prompts.rule_derivation_prompt import get_few_shot_examples
from ..config.settings import get_settings
from ..config.attribute_config import DEFAULT_ATTRIBUTE_COUNT, DEFAULT_SCHEMA_PATH


def load_profiling_node(state: AgentState) -> Dict[str, Any]:
    """
    Load profiling statistics and sample data.

    This node:
    - Loads the profiling JSON file
    - Parses statistics into structured objects
    - Loads sample data from Excel for validation
    - Calculates total record count
    - Derives dataset name and parent class dynamically
    - Filters priority attributes using Taxonomy Model schema
    """
    print("Loading profiling data...")

    settings = get_settings()

    # Get schema path from state or use default
    schema_path = state.get('schema_path', DEFAULT_SCHEMA_PATH)

    profiler = DataProfilerAgent(
        profiling_path=state['profiling_path'],
        raw_data_path=state['raw_data_path'],
        schema_path=schema_path,
        attribute_count=DEFAULT_ATTRIBUTE_COUNT,
    )

    # Load and parse profiling JSON
    raw_profiling = profiler.load_profiling_json()
    profiling_stats = profiler.parse_profiling_stats(raw_profiling)

    # Load sample data for validation
    try:
        sample_df = profiler.load_sample_data(sample_size=settings.sample_size)
        sample_data = sample_df.head(100).to_dict('records') if len(sample_df) > 0 else []
    except Exception as e:
        print(f"Warning: Could not load sample data: {e}")
        sample_data = []

    total_records = profiler.get_total_records()

    # Get dataset context - all values derived dynamically with taxonomy filtering
    dataset_context = profiler.get_dataset_context(use_taxonomy=True)
    dataset_context['profiling_path'] = state['profiling_path']
    dataset_context['schema_path'] = schema_path

    print(f"  Loaded {len(profiling_stats)} attributes")
    print(f"  Estimated {total_records} total records")
    print(f"  Dataset name: {dataset_context.get('dataset_name', 'Unknown')}")
    print(f"  Parent class: {dataset_context.get('parent_class', 'Unknown')}")
    print(f"  Taxonomy matches: {dataset_context.get('taxonomy_match_count', 0)} out of {dataset_context.get('taxonomy_total_attributes', 0)} taxonomy attributes")

    return {
        "profiling_stats": {k: v.model_dump() for k, v in profiling_stats.items()},
        "sample_data": sample_data,
        "total_records": total_records,
        "dataset_context": dataset_context,
    }


def select_priority_attributes_node(state: AgentState) -> Dict[str, Any]:
    """
    Select priority attributes for rule derivation using Taxonomy Model filtering.

    This node:
    - Uses taxonomy-filtered attributes from dataset_context (computed during profiling load)
    - Falls back to first N non-empty attributes if no taxonomy matches
    - Sets up the iteration state
    """
    print("Selecting priority attributes using Taxonomy Model filtering...")

    # Get taxonomy-filtered priority attributes from dataset context
    # These were computed during load_profiling_node using TaxonomyAttributeFilter
    dataset_context = state.get('dataset_context', {})
    available_attrs = dataset_context.get('priority_attributes', [])

    # Validate that these attributes exist in profiling data and are not empty
    profiling_stats = state.get('profiling_stats', {})
    validated_attrs = []

    for attr in available_attrs:
        if attr in profiling_stats:
            stats = profiling_stats[attr]
            # Skip completely empty attributes
            if stats.get('datatype') == 'Empty':
                continue
            if stats.get('missing_percentage', 100) >= 100:
                continue
            validated_attrs.append(attr)

    # Fallback: If no taxonomy-filtered attributes, use first N non-empty
    if not validated_attrs:
        print("  Warning: No taxonomy-matched attributes found. Using fallback (first N non-empty).")
        for attr, stats in profiling_stats.items():
            if stats.get('datatype') == 'Empty':
                continue
            if stats.get('missing_percentage', 100) >= 100:
                continue
            validated_attrs.append(attr)
            if len(validated_attrs) >= DEFAULT_ATTRIBUTE_COUNT:
                break

    taxonomy_match_count = dataset_context.get('taxonomy_match_count', 0)
    taxonomy_total = dataset_context.get('taxonomy_total_attributes', 0)

    print(f"  Selected {len(validated_attrs)} priority attributes for rule derivation")
    print(f"  Taxonomy schema: {taxonomy_total} attributes defined, {taxonomy_match_count} matched raw data")
    for attr in validated_attrs:
        print(f"    - {attr}")

    return {
        "attributes_to_process": validated_attrs,
        "current_attribute": validated_attrs[0] if validated_attrs else None,
        "iteration_count": 0,
    }


def derive_rules_node(state: AgentState) -> Dict[str, Any]:
    """
    Derive DQ rules for the current attribute using LLM.

    This node:
    - Gets profiling stats for current attribute
    - Prepares analysis context
    - Calls RuleDerivationAgent with GPT-4o
    - Parses and validates returned rules
    """
    current_attr = state.get('current_attribute')
    if not current_attr:
        return {"errors": state.get('errors', []) + ["No attribute to process"]}

    print(f"Deriving rules for: {current_attr}")

    # Get profiling stats for current attribute
    attr_stats = state['profiling_stats'].get(current_attr)
    if not attr_stats:
        return {"errors": state.get('errors', []) + [f"No stats for {current_attr}"]}

    # Reconstruct ProfilingResult for analysis
    from ..models.profiling_stats import ProfilingResult
    profiling_result = ProfilingResult(**attr_stats)

    # Create profiler for recommendation methods
    profiler = DataProfilerAgent.__new__(DataProfilerAgent)
    profiler.profiling_stats = {
        current_attr: profiling_result
    }

    # Prepare analysis context
    attr_analysis = {
        "attribute_name": current_attr,
        "datatype": profiling_result.datatype,
        "missing_percentage": profiling_result.missing_percentage,
        "cardinality": profiling_result.cardinality,
        "top_values": profiling_result.top_values,
        "range": profiling_result.range,
        "recommended_rules": profiler.recommend_rule_types(profiling_result),
    }

    # Get dataset context from state - all values derived dynamically
    dataset_context = state.get('dataset_context', {})

    # Ensure we have minimum context
    if not dataset_context.get('dataset_name'):
        dataset_context['dataset_name'] = 'Product_Data'
    if not dataset_context.get('total_records'):
        dataset_context['total_records'] = state.get('total_records', 0)

    # Derive rules using LLM
    try:
        derivation_agent = RuleDerivationAgent()
        few_shot_examples = get_few_shot_examples()

        new_rules = derivation_agent.derive_rules_for_attribute(
            attr_analysis,
            dataset_context,
            few_shot_examples,
        )

        print(f"  Generated {len(new_rules)} rules")
        return {"candidate_rules": new_rules}

    except Exception as e:
        error_msg = f"Error deriving rules for {current_attr}: {str(e)}"
        print(f"  {error_msg}")
        return {"errors": state.get('errors', []) + [error_msg]}


def validate_rules_node(state: AgentState) -> Dict[str, Any]:
    """
    Validate derived rules against sample data.

    This node:
    - Takes rules for current attribute
    - Executes Python validation expressions
    - Calculates pass/fail rates
    - Moves to next attribute
    """
    current_attr = state.get('current_attribute')
    print(f"Validating rules for: {current_attr}")

    # Get sample data
    sample_data = state.get('sample_data', [])
    if not sample_data:
        print("  No sample data available for validation")
        # Move to next attribute anyway
        attrs_to_process = state.get('attributes_to_process', [])
        try:
            current_idx = attrs_to_process.index(current_attr) if current_attr else -1
        except ValueError:
            current_idx = -1
        next_attr = attrs_to_process[current_idx + 1] if current_idx + 1 < len(attrs_to_process) else None

        return {
            "current_attribute": next_attr,
            "iteration_count": state.get('iteration_count', 0) + 1,
        }

    sample_df = pd.DataFrame(sample_data)
    validation_agent = RuleValidationAgent(sample_df)

    # Get rules for current attribute
    current_rules = [
        r for r in state.get('candidate_rules', [])
        if isinstance(r, DQRule) and r.attribute_name == current_attr
    ]

    if not current_rules:
        print("  No rules to validate")
    else:
        # Validate rules
        validation_results = validation_agent.validate_all_rules(current_rules)
        print(f"  Validated {len(validation_results)} rules")

        for result in validation_results:
            print(f"    {result.rule_id}: {result.pass_rate}% pass rate")

    # Move to next attribute
    attrs_to_process = state.get('attributes_to_process', [])
    try:
        current_idx = attrs_to_process.index(current_attr) if current_attr else -1
    except ValueError:
        current_idx = -1
    next_attr = attrs_to_process[current_idx + 1] if current_idx + 1 < len(attrs_to_process) else None

    return {
        "validation_results": state.get('validation_results', []) + (validation_results if current_rules else []),
        "current_attribute": next_attr,
        "iteration_count": state.get('iteration_count', 0) + 1,
    }


def refine_rules_node(state: AgentState) -> Dict[str, Any]:
    """
    Refine and deduplicate rules based on validation results.

    This node:
    - Adjusts thresholds based on validation
    - Removes duplicate rules
    - Prepares final ruleset
    """
    print("Refining rules...")

    all_rules = state.get('candidate_rules', [])
    validation_results = {r.rule_id: r for r in state.get('validation_results', [])}

    # Filter to only DQRule objects
    all_rules = [r for r in all_rules if isinstance(r, DQRule)]

    refined_rules = []
    seen_ids = set()

    for rule in all_rules:
        # Skip duplicates
        if rule.rule_id in seen_ids:
            continue
        seen_ids.add(rule.rule_id)

        # Adjust thresholds based on validation
        if rule.rule_id in validation_results:
            result = validation_results[rule.rule_id]
            actual_fail_rate = 100 - result.pass_rate

            if actual_fail_rate > rule.threshold_percent * 1.5:
                # Adjust threshold
                rule_dict = rule.to_dict()
                rule_dict['threshold_percent'] = min(round(actual_fail_rate * 1.1, 1), 100)
                rule_dict['derived_from'] += f" (threshold adjusted)"
                refined_rules.append(DQRule(**rule_dict))
            else:
                refined_rules.append(rule)
        else:
            refined_rules.append(rule)

    print(f"  Refined {len(all_rules)} rules to {len(refined_rules)} unique rules")

    return {"validated_rules": refined_rules}


def format_output_node(state: AgentState) -> Dict[str, Any]:
    """
    Format and export rules to JSON and Excel.

    This node:
    - Creates output directory
    - Exports rules to JSON
    - Exports rules to Excel with formatting
    - Includes Parent Class/Category in output
    """
    print("Formatting output...")

    settings = get_settings()
    formatter = OutputFormatterAgent(output_dir=str(settings.output_abs_dir))

    rules = state.get('validated_rules', [])
    validation_results = state.get('validation_results', [])

    # Get dataset context - all values derived dynamically
    dataset_context = state.get('dataset_context', {})

    # Ensure we have minimum context
    if not dataset_context.get('dataset_name'):
        dataset_context['dataset_name'] = 'Product_Data'
    if not dataset_context.get('total_records'):
        dataset_context['total_records'] = state.get('total_records', 0)
    if not dataset_context.get('profiling_path'):
        dataset_context['profiling_path'] = state.get('profiling_path', '')

    # Export JSON
    json_path = formatter.export_to_json(
        rules,
        dataset_context,
        settings.output_json_filename,
    )
    print(f"  JSON output: {json_path}")

    # Export Excel
    excel_path = formatter.export_to_excel(
        rules,
        validation_results,
        settings.output_excel_filename,
        dataset_context,
    )
    print(f"  Excel output: {excel_path}")

    # Generate summary
    summary = formatter.generate_summary(rules)
    print(f"\n  Summary:")
    print(f"    Total rules: {summary['total_rules']}")
    print(f"    Attributes covered: {summary['attribute_count']}")
    print(f"    Avg confidence: {summary['avg_confidence_score']:.2f}")
    print(f"    Parent Class: {dataset_context.get('parent_class', 'Unknown')}")

    return {
        "output_json_path": json_path,
        "output_excel_path": excel_path,
    }