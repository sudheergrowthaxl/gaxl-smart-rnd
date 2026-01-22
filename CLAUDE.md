# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an AI-powered Data Quality (DQ) Rules Derivation System that automatically generates comprehensive data quality rules from raw product data. The system uses **LangGraph** for workflow orchestration, **LangChain** for AI chain composition, and **OpenAI GPT-4o** for intelligent rule generation.

**Core Value Proposition**: Transforms weeks of manual DQ rule creation into minutes by automatically analyzing data profiling statistics, deriving validation/normalization rules, and generating production-ready SQL and Python implementations.

## Setup & Configuration

### Environment Setup

1. Create `.env` file from template:
```bash
cp .env.example .env
```

2. Configure OpenAI API key in `.env`:
```
OPENAI_API_KEY=your_openai_api_key_here
```

3. Install dependencies:
```bash
pip install -r requirements.txt
# OR
pip install -e .
```

### Configuration Settings

Key settings in `src/config/settings.py` (can override via `.env`):

- **OPENAI_MODEL**: Default `gpt-4o` (LLM for rule derivation)
- **TEMPERATURE**: `0.1` (high precision for rule generation)
- **MAX_TOKENS**: `8000` (sufficient for complex rule derivations)
- **ATTRIBUTE_LIMIT**: `0` = no limit (process ALL taxonomy-matched attributes); set positive number to limit
- **RAW_DATA_PATH**: Path to Excel/JSON product data file
- **PROFILING_PATH**: Path to profiling JSON with statistical analysis
- **SCHEMA_PATH**: Path to taxonomy model schema folder

### Running the System

```bash
python main.py
```

The system will:
1. Validate environment (API key, input files)
2. Display workflow diagram
3. Execute LangGraph workflow
4. Generate output files in `output/` directory

## Architecture

### LangGraph Workflow (State Machine)

The system follows a **stateful workflow** with iterative rule derivation:

```
START
  → load_profiling         # Load profiling JSON, parse stats, load sample data
  → select_priority_attrs  # Filter taxonomy-matched attributes
  → [LOOP START]
     → derive_rules        # GPT-4o generates rules for current attribute
     → validate_rules      # Execute Python expressions against sample data
     → [Check: More attributes?]
        Yes → derive_rules (loop back)
        No  → continue
  → [LOOP END]
  → refine_rules           # Adjust thresholds, deduplicate rules
  → format_output          # Export JSON + Excel
  → END
```

**Critical Design Pattern**: The workflow uses conditional edges to iterate through attributes one at a time. The `should_process_more_attributes()` edge function determines whether to loop back to `derive_rules` or proceed to `refine_rules`.

### Agent Architecture

#### 1. DataProfilerAgent (`src/agents/data_profiler_agent.py`)
- Loads profiling JSON and parses statistical attributes
- Filters attributes using **Taxonomy Model schema** (Excel file in `data/schema/`)
- Matches profiling attributes against taxonomy definitions
- Dynamically derives dataset name and parent class from data
- Provides data-driven severity and threshold recommendations

#### 2. RuleDerivationAgent (`src/agents/rule_derivation_agent.py`)
- Uses **GPT-4o with few-shot prompting** (examples in `src/prompts/rule_derivation_prompt.py`)
- Analyzes attribute profiling statistics (cardinality, missing %, top values, ranges)
- Generates rules across 9 DQ dimensions: Completeness, Validity, Accuracy, Consistency, Uniqueness, Timeliness, Normalization, Computation, Default
- Returns structured Pydantic `DQRule` objects with SQL and Python implementations

#### 3. RuleValidationAgent (`src/agents/rule_validation_agent.py`)
- Executes `rule_expression_python` against sample DataFrame
- Calculates pass/fail rates
- Adjusts thresholds if actual failure rate exceeds expected by 1.5x
- Provides validation results for refinement

#### 4. OutputFormatterAgent (`src/agents/output_formatter_agent.py`)
- Exports to `output/dq_rules.json` (production-ready ruleset)
- Exports to `output/dq_rules.xlsx` (multi-sheet Excel report: summary, by category, by attribute, validation results)
- Generates summary statistics

### Data Models (Pydantic)

#### DQRule (`src/models/dq_rule.py`)
The core rule model with fields:
- `attribute_name`: Target attribute
- `rule_category`: DQ dimension (Completeness, Validity, etc.)
- `rule_type`: Specific type (NOT_NULL, RANGE, VALUE_SET, etc.)
- `rule_expression`: Natural language description
- `rule_expression_sql`: SQL query to detect violations
- `rule_expression_python`: Pandas/Python expression for validation
- `description`: Business-friendly explanation
- `derived_from`: Profiling statistic source
- `confidence_score`: AI confidence (0.0-1.0)
- `support`, `confidence`: Data-driven metrics
- `sample_valid_values`, `sample_invalid_values`: Examples

#### AgentState (`src/models/agent_state.py`)
LangGraph state shared across nodes. Key fields:
- `profiling_stats`: Dict of attribute → profiling statistics
- `sample_data`: Sample records for validation
- `attributes_to_process`: List of attributes to derive rules for
- `current_attribute`: Currently processing attribute
- `candidate_rules`: Accumulated rules (uses `Annotated[List, add]` for append-only)
- `validated_rules`: Final validated rules
- `dataset_context`: Dynamically derived metadata (dataset name, parent class, taxonomy matches)
- `iteration_count`: Tracks loop iterations

### Taxonomy Filtering (`src/config/taxonomy_filter.py`)

The system uses an **Excel-based taxonomy schema** to filter relevant attributes:
- Schema file location: `data/schema/` (configurable via `SCHEMA_PATH`)
- Matches profiling attributes against taxonomy definitions
- Case-insensitive matching with fuzzy logic
- Only processes attributes that match taxonomy model
- Significantly reduces noise from irrelevant attributes

**Why This Matters**: In datasets with 100+ attributes, taxonomy filtering focuses rule generation on the 15-20 attributes that matter for the business domain (e.g., for Contactors: current rating, voltage, poles, series).

### Configuration Tuning (`src/config/attribute_config.py`)

Key constants that control behavior:

- `MAX_MISSING_THRESHOLD`: Skip attributes with >70% missing values
- `CARDINALITY_THRESHOLDS`: Minimum cardinality by datatype (Numeric: 0.1%, Categorical: 0.1%, etc.)
- `DATATYPE_RULE_MAPPING`: Which rule types to derive for each datatype
- `MISSING_SEVERITY_THRESHOLDS`: Data-driven severity based on missing %
  - Critical: 0-5% missing
  - High: 5-20% missing
  - Medium: 20-50% missing
  - Low: 50-95% missing
  - Sparse: 95-100% missing (no completeness rules)

**Design Philosophy**: Severity and thresholds are **data-driven**, not prescriptive. Rules reflect actual data state, not ideal expectations.

## Common Development Workflows

### Testing Rule Derivation on New Dataset

1. Place raw data in `data/` (Excel or JSON)
2. Generate profiling JSON (external tool or custom script)
3. Update `.env` with new paths:
   ```
   RAW_DATA_PATH=data/your_new_data.xlsx
   PROFILING_PATH=data/your_profiling.json
   ```
4. Run: `python main.py`

### Modifying Few-Shot Examples

Edit `src/prompts/rule_derivation_prompt.py` to add domain-specific examples for GPT-4o. The few-shot examples teach the LLM:
- Pattern matching (e.g., email validation)
- Statistical bounds (e.g., numeric ranges)
- Semantic types (e.g., date formats)
- Business rules (e.g., referential integrity)

### Adjusting Attribute Limits

Set `ATTRIBUTE_LIMIT` in `.env`:
- `ATTRIBUTE_LIMIT=0` → Process ALL taxonomy-matched attributes (recommended for production)
- `ATTRIBUTE_LIMIT=10` → Process first 10 attributes (for testing)

### Adding New Rule Categories

1. Add to `RuleCategory` enum in `src/models/dq_rule.py`
2. Add to `RuleType` enum with specific types
3. Update `DATATYPE_RULE_MAPPING` in `src/config/attribute_config.py`
4. Add few-shot examples in `src/prompts/rule_derivation_prompt.py`

## Critical Design Decisions

### Why LangGraph Over Simple Chains?

LangGraph provides:
- **Stateful workflow** with persistent state across iterations
- **Conditional routing** for dynamic attribute processing
- **Checkpointing** via `MemorySaver` (can resume from failures)
- **Transparency** with workflow diagrams and node-by-node execution

### Why Iterative Attribute Processing?

Processing one attribute at a time (instead of batch):
- **Better context** for GPT-4o (focused prompts per attribute)
- **Token efficiency** (avoid massive prompts with 15+ attributes)
- **Granular validation** (test rules immediately after derivation)
- **Adaptive thresholds** (adjust based on validation results)

### Why Data-Driven Severity?

Traditional DQ systems use prescriptive rules ("all emails must be valid"). This system is **descriptive**:
- If 30% of emails are missing, severity is Medium (not Critical)
- Thresholds reflect actual data state, allowing gradual improvement
- Prevents "all red" dashboards that discourage adoption

### Why Taxonomy Filtering?

Without taxonomy:
- 100+ attributes → 300+ rules (overwhelming)
- Many irrelevant attributes (IDs, internal fields, metadata)
- Noise obscures signal

With taxonomy:
- 15-20 priority attributes → 40-50 focused rules
- Rules align with business semantics
- Adoption and maintenance are feasible

## File Organization Logic

```
src/
├── agents/          # Agent implementations (profiler, derivation, validation, output)
├── workflow/        # LangGraph construction (graph_builder.py, nodes.py, edges.py)
├── models/          # Pydantic models (dq_rule.py, agent_state.py, profiling_stats.py)
├── prompts/         # Few-shot examples for GPT-4o
├── config/          # Settings, attribute filtering, taxonomy filtering
└── utils/           # Utilities (if any)

data/
├── schema/          # Taxonomy model Excel files
├── *.xlsx           # Raw product data
└── *.json           # Profiling statistics

output/
├── dq_rules.json    # Generated ruleset
└── dq_rules.xlsx    # Excel report
```

## Debugging Tips

### Workflow not progressing?

Check `iteration_count` in logs. If stuck at same attribute:
- Verify `should_process_more_attributes()` edge logic in `src/workflow/edges.py`
- Check `attributes_to_process` list is populated in `select_priority_attributes_node`
- Ensure `current_attribute` advances after each validation

### GPT-4o generating poor rules?

- Review profiling statistics quality (garbage in = garbage out)
- Add domain-specific few-shot examples in `rule_derivation_prompt.py`
- Increase `TEMPERATURE` to 0.2-0.3 for more creative rules (trade-off: less precision)
- Check `derived_from` field to understand which statistics influenced the rule

### Validation failures exceeding thresholds?

This is **expected behavior**. The system auto-adjusts thresholds:
```python
if actual_fail_rate > threshold * 1.5:
    threshold = min(actual_fail_rate * 1.1, 100%)
```
The adjusted rules reflect data reality, not ideal state.

### No taxonomy matches?

- Verify schema Excel file exists in `data/schema/`
- Check `TaxonomyFilter.load_taxonomy_from_schema()` in `src/config/taxonomy_filter.py`
- Ensure attribute names in profiling JSON roughly match taxonomy model
- Try case-insensitive matching: `get_taxonomy_filtered_attributes(case_sensitive=False)`

## Output Artifacts

### dq_rules.json
Production-ready JSON with:
- Dataset metadata (name, parent class, total records, timestamp)
- Array of rules with SQL and Python implementations
- Summary statistics (total rules, rules by category, attributes covered, avg confidence)

### dq_rules.xlsx
Multi-sheet Excel workbook:
- **Summary**: Overview of all rules
- **By Category**: Grouped by DQ dimension (Completeness, Validity, etc.)
- **By Attribute**: Rules organized by attribute name
- **Validation Results**: Pass/fail rates, sample failures

## Integration Points

### Connecting to Data Catalogs
The JSON output can be ingested by:
- Data catalog APIs (Collibra, Alation, etc.)
- DQ tools (Great Expectations, Soda, etc.)
- Custom DQ engines

### Execution Engines
Rules include both SQL and Python implementations:
- **SQL**: Run in databases (Snowflake, Postgres, etc.) for at-scale validation
- **Python/Pandas**: Integrate into ETL pipelines (Airflow, Prefect, etc.)

## Python Version Requirement

Requires **Python >=3.13** (see `pyproject.toml`). Uses modern Pydantic v2 features.