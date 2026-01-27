# CLAUDE.md - Data Quality Rules Derivation Project

> This file provides context and instructions for Claude when working on this project.
> Place this file in your project root directory.

---

## Project Overview

This project derives **Data Quality Rules** for manufacturers' contactors and relays data (specifically ABB products) by synthesizing multiple data sources using GPT-4o. The system uses a RAG (Retrieval-Augmented Generation) pipeline to extract specifications from technical PDFs.

---

## Project Structure

```
data_quality_rules_project/
├── CLAUDE.md                    # This file - Claude's instructions
├── prompts/
│   └── data_quality_rules_prompt.xml   # Main XML prompt template
├── config/
│   ├── config.yaml              # Application configuration
│   ├── logging_config.yaml      # Logging settings
│   └── shape_constraints.yaml   # Shape constraint thresholds
├── src/
│   ├── __init__.py
│   ├── ingestion/               # PDF processing pipeline
│   │   ├── __init__.py
│   │   ├── pdf_processor.py
│   │   ├── text_extractor.py
│   │   ├── table_extractor.py
│   │   ├── image_processor.py
│   │   └── metadata_extractor.py
│   ├── chunking/                # Document chunking
│   │   ├── __init__.py
│   │   ├── semantic_chunker.py
│   │   ├── table_chunker.py
│   │   └── chunk_enricher.py
│   ├── embedding/               # Vector embeddings
│   │   ├── __init__.py
│   │   ├── embedder.py
│   │   └── batch_processor.py
│   ├── vectordb/                # Vector database
│   │   ├── __init__.py
│   │   ├── chroma_client.py
│   │   └── collection_manager.py
│   ├── retrieval/               # RAG retrieval
│   │   ├── __init__.py
│   │   ├── retriever.py
│   │   ├── hybrid_search.py
│   │   ├── query_expander.py
│   │   └── reranker.py
│   ├── data_sources/            # Input data loaders
│   │   ├── __init__.py
│   │   ├── crosstab_loader.py
│   │   ├── profiling_loader.py
│   │   └── wikipedia_scraper.py
│   ├── matching/                # Attribute matching
│   │   ├── __init__.py
│   │   └── attribute_matcher.py
│   ├── rules/                   # Rule generation
│   │   ├── __init__.py
│   │   ├── prompt_builder.py
│   │   ├── rule_generator.py
│   │   ├── rule_models.py
│   │   └── shape_constraints.py # Deterministic rule derivation
│   ├── exporters/               # Output generation
│   │   ├── __init__.py
│   │   ├── json_exporter.py
│   │   └── excel_exporter.py
│   └── pipeline.py              # Main orchestrator
├── data/
│   ├── input/
│   │   ├── crosstab/            # Cross-tab CSV/Excel files
│   │   ├── profiling/           # Profiling statistics JSON
│   │   ├── wikipedia/           # Cached Wikipedia data
│   │   └── pdfs/                # ABB technical PDFs
│   ├── processed/               # Intermediate outputs
│   └── output/                  # Final outputs (JSON, Excel)
├── vectordb/                    # ChromaDB persistence
├── tests/
├── notebooks/
├── requirements.txt
└── main.py
```

---

## Key Objectives

1. **Generate Data Quality Rules** for attributes found in BOTH:
   - Cross-Tab (Priority Attributes from Ontology)
   - RAG-retrieved Technical Specifications (ABB data)

2. **Build a Production-Grade RAG Pipeline** that handles:
   - PDF text extraction (multi-column, OCR)
   - Table extraction and structuring
   - Image/diagram processing
   - Context-aware semantic chunking
   - Optimized retrieval with hybrid search

3. **Output formats**: JSON and Excel with comprehensive rule documentation

---

## Data Sources

| Source | Description | Location |
|--------|-------------|----------|
| **Cross-Tab** | Priority Attributes ↔ Core Properties from Ontology | `data/input/crosstab/` |
| **Profiling** | Python profiling statistics for contactors data | `data/input/profiling/` |
| **Wikipedia** | Web-scraped standard definitions | `data/input/wikipedia/` |
| **RAG Specs** | ABB technical PDFs (contactors, relays) | `data/input/pdfs/` |

---

## Critical Rules for Development

### Attribute Matching
```
IMPORTANT: Only generate data quality rules for attributes that exist in BOTH:
1. Cross-Tab ontology (canonical attribute names)
2. RAG-retrieved ABB specifications

Attributes in only one source should be REPORTED but NOT have rules generated.
```

### ABB Term Mapping
| Canonical Name | ABB Terms |
|----------------|-----------|
| `rated_current` | Ie, rated operational current |
| `rated_voltage` | Ue, rated operational voltage |
| `coil_voltage` | control circuit voltage |
| `utilization_category` | AC-1, AC-3, AC-4 |
| `mechanical_durability` | mechanical life, operations |
| `electrical_durability` | electrical life |

### RAG Pipeline Requirements
- **Chunking**: Semantic boundaries, 512 tokens target, 50 token overlap
- **Embedding**: OpenAI `text-embedding-3-small` (1536 dimensions)
- **Vector DB**: ChromaDB with cosine similarity
- **Retrieval**: Hybrid search (vector 0.7 + BM25 0.3), top_k=10, threshold=0.75

---

## XML Prompt Template

The main prompt template is located at: `prompts/data_quality_rules_prompt.xml`

### How to Use the Prompt

1. **Load the template**:
```python
with open('prompts/data_quality_rules_prompt.xml', 'r') as f:
    prompt_template = f.read()
```

2. **Replace placeholders** with actual data:
```python
prompt = prompt_template.replace('{{CROSSTAB_DATA}}', formatted_crosstab)
prompt = prompt_template.replace('{{PROFILING_STATISTICS}}', formatted_profiling)
prompt = prompt_template.replace('{{WIKIPEDIA_DEFINITIONS}}', formatted_wikipedia)
prompt = prompt_template.replace('{{RAG_TECHNICAL_SPECS}}', formatted_rag_specs)
```

3. **Send to GPT-4o**:
```python
response = openai_client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "You are a Data Quality Architect..."},
        {"role": "user", "content": prompt}
    ],
    response_format={"type": "json_object"},
    temperature=0.3,
    max_tokens=4096
)
```

---

## Code Standards

When writing or modifying code in this project:

- **Python Version**: 3.10+
- **Type Hints**: Required for all functions
- **Docstrings**: Google style
- **Error Handling**: Use custom exceptions in `src/utils/exceptions.py`
- **Logging**: Use `logging` module, not `print()`
- **Config**: Load from `config/config.yaml`

### Example Function Template
```python
def process_attribute(
    attribute_name: str,
    crosstab_data: pd.DataFrame,
    rag_chunks: list[dict]
) -> dict[str, Any]:
    """
    Process a single attribute for rule generation.
    
    Args:
        attribute_name: Canonical name of the attribute
        crosstab_data: Cross-tab DataFrame with ontology mappings
        rag_chunks: Retrieved specification chunks from vector DB
    
    Returns:
        Dictionary containing attribute analysis and suggested rules
    
    Raises:
        AttributeNotFoundError: If attribute not in crosstab
        RAGRetrievalError: If retrieval fails
    """
    logger.info(f"Processing attribute: {attribute_name}")
    # Implementation here
```

---

## Pipeline Modes

The pipeline supports multiple modes for generating data quality rules:

### Mode 1: Cross-Tab Based with Shape Constraints (RECOMMENDED)
Generate rules for **Cross-Tab attributes** using deterministic shape constraints.
```bash
uv run python main.py crosstab --verbose
```

**Rule Derivation Approach:**
- **COMPLETENESS Rules**: Descriptive (based on actual data patterns in Profiling)
- **VALIDITY Rules**: Prescriptive (based on Wikipedia/industry standards)

**Completeness Thresholds (configurable in `config/shape_constraints.yaml`):**
| Missing % | Interpretation | Rule Generated |
|-----------|----------------|----------------|
| **< 5%** | Customers always provide | `COMPLETENESS: mandatory_field, severity=ERROR` |
| **5-20%** | Usually provided | `COMPLETENESS: threshold, severity=WARNING` |
| **20-70%** | Sometimes provided | `COMPLETENESS: conditional_mandatory, severity=INFO` |
| **> 70%** | Rarely provided | **NO completeness rule** (optional field) |
| **100%** | Never provided | `FLAG: consider removing from schema` |

**Validity Sources (in priority order):**
1. Wikipedia industry standards (IEC 60038, IEC 60947, etc.)
2. Built-in standard values (`config/shape_constraints.yaml`)
3. Profiling statistics (fallback)

**Use Legacy GPT-4o Mode:**
```bash
uv run python main.py crosstab --legacy --verbose
```

### Mode 2: Full Pipeline (with Attribute Matching)
Match attributes between Cross-Tab and RAG, generate rules for matched only.
```bash
uv run python main.py run --verbose
```

### Mode 3: PDF-Only
Generate rules directly from vectorized PDF data (no Cross-Tab matching).
```bash
uv run python main.py pdf-only --verbose
```

### Mode 4: Profiling-Based
Generate rules for all attributes in Python Profiling data.
```bash
uv run python main.py profiling --verbose
```

---

## Shape Constraints Configuration

The shape constraint engine uses `config/shape_constraints.yaml` for thresholds:

```yaml
shape_constraints:
  completeness:
    mandatory_threshold: 5.0      # < 5% missing = mandatory
    expected_threshold: 20.0      # 5-20% missing = expected
    conditional_threshold: 70.0   # 20-70% missing = conditional
    optional_above: 70.0          # > 70% missing = no rule

  validity:
    scrape_wikipedia: true        # Use Wikipedia for industry standards
    fallback_to_profiling: true   # Use profiling range if Wikipedia fails

  standard_values:
    voltage:
      common_values: [24, 48, 110, 220, 230, 240, 400, 480, 690]
      range: {min: 12, max: 1000}
      unit: "V"
    frequency:
      common_values: [50, 60]
      unit: "Hz"
    # ... more standard values
```

### Key Files for Shape Constraints
- `config/shape_constraints.yaml` - Threshold configuration
- `src/rules/shape_constraints.py` - ShapeConstraintEngine class
- `src/data_sources/wikipedia_scraper.py` - `extract_standard_values()` method

---

## Common Tasks

### Task 1: Add a New PDF to RAG Pipeline
```bash
uv run python main.py ingest --pdf-path data/input/pdfs/new_document.pdf
```

### Task 2: Generate Rules for Specific Attributes
```bash
uv run python main.py generate --attributes rated_current,rated_voltage
```

### Task 3: Export Rules to Excel
```bash
uv run python main.py export --format excel --output data/output/rules.xlsx
```

### Task 4: Run Cross-Tab Based Pipeline (Recommended)
```bash
uv run python main.py crosstab --config config/config.yaml --verbose
```

### Task 5: View Pipeline Statistics
```bash
uv run python main.py stats
```

---

## Environment Variables

```bash
# Required
OPENAI_API_KEY=sk-...

# Optional
CHROMA_PERSIST_DIR=./vectordb
LOG_LEVEL=INFO
```

---

## Dependencies

Key dependencies (see `requirements.txt` for full list):

```
openai>=1.0.0
chromadb>=0.4.0
PyMuPDF>=1.23.0
pdfplumber>=0.10.0
pandas>=2.0.0
openpyxl>=3.1.0
pydantic>=2.0.0
beautifulsoup4>=4.12.0
rapidfuzz>=3.0.0
sentence-transformers>=2.2.0
tiktoken>=0.5.0
```

---

## Output Schema Summary

### JSON Output (`data/output/data_quality_rules.json`)
```json
{
  "metadata": { ... },
  "attribute_matching_report": {
    "matched_attributes": [...],
    "crosstab_only_attributes": [...],
    "rag_only_attributes": [...]
  },
  "rules": [
    {
      "rule_id": "DQR_001",
      "category": "VALIDITY",
      "attribute": "rated_current",
      "validation_logic": { ... },
      "source_evidence": [...]
    }
  ],
  "summary": { ... }
}
```

### Excel Output (`data/output/data_quality_rules.xlsx`)
Sheets: `Rules_Master`, `Attribute_Mapping`, `Unmatched_Attributes`, `By_Category`, `Source_Traceability`, `Implementation_Checklist`

---

## Prompt Reference

The complete XML prompt specification is embedded below for reference. Use this when generating rules or extending the system.

<details>
<summary><b>Click to expand full XML Prompt Template</b></summary>

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!--
================================================================================
DATA QUALITY RULES DERIVATION PROMPT - ENHANCED VERSION
================================================================================
Purpose: Derive comprehensive data quality rules for manufacturers' contactors 
         data by synthesizing multiple contextual data sources with focus on
         ABB contactors and relays specifications.
Target Model: OpenAI GPT-4o
Domain: Manufacturing Industry - Electrical Contactors & Relays (ABB)
Version: 2.0
================================================================================
-->

<data_quality_rules_derivation_prompt version="2.0">

    <!-- SECTION 1: SYSTEM ROLE AND OBJECTIVE -->
    <system_context>
        <role>
            You are an expert Data Quality Architect, Manufacturing Domain Specialist,
            and Python Developer with extensive experience in:
            - Industrial data governance and quality management
            - Electrical equipment specifications (contactors, relays, switchgear)
            - ABB product catalogs and technical documentation
            - RAG system architecture and vector databases
            - Python development for data engineering pipelines
        </role>

        <primary_objective>
            Analyze and synthesize information from FOUR distinct data sources to derive 
            comprehensive data quality rules for manufacturers' contactors and relays data.
            
            CRITICAL: Only generate rules for attributes found in BOTH:
            1. The Cross-Tab (Priority Attributes from Ontology)
            2. The RAG-retrieved Technical Specifications (ABB product data)
        </primary_objective>
    </system_context>

    <!-- SECTION 2: ATTRIBUTE MATCHING STRATEGY -->
    <attribute_matching_strategy>
        <matching_process>
            1. Extract attributes from Cross-Tab (canonical names)
            2. Extract attributes from RAG specifications (ABB terms)
            3. Perform fuzzy matching with synonym support
            4. Create: MATCHED, CROSSTAB_ONLY, RAG_ONLY sets
            5. Generate rules ONLY for MATCHED attributes
        </matching_process>

        <abb_mapping_hints>
            - rated_current → Ie, rated operational current
            - rated_voltage → Ue, rated operational voltage
            - coil_voltage → control circuit voltage
            - utilization_category → AC-1, AC-3, AC-4
            - mechanical_durability → mechanical life, operations
        </abb_mapping_hints>
    </attribute_matching_strategy>

    <!-- SECTION 3: INPUT DATA SOURCES -->
    <input_data_sources>
        <source id="CROSSTAB">{{CROSSTAB_DATA}}</source>
        <source id="PROFILING">{{PROFILING_STATISTICS}}</source>
        <source id="WIKIPEDIA">{{WIKIPEDIA_DEFINITIONS}}</source>
        <source id="RAG_SPECS">{{RAG_TECHNICAL_SPECS}}</source>
    </input_data_sources>

    <!-- SECTION 4: RAG PIPELINE SPECIFICATION -->
    <rag_pipeline>
        <ingestion>
            - PDF preprocessing and validation
            - Text extraction (multi-column, OCR)
            - Table extraction (pdfplumber/camelot)
            - Image processing with OCR
            - Metadata extraction
        </ingestion>
        <chunking>
            - Semantic chunking (512 tokens, 50 overlap)
            - Table-specific chunking
            - Hierarchical multi-level chunks
            - Metadata enrichment
        </chunking>
        <retrieval>
            - Hybrid search (vector 0.7 + BM25 0.3)
            - Query expansion with synonyms
            - Cross-encoder reranking
            - Similarity threshold: 0.75
        </retrieval>
    </rag_pipeline>

    <!-- SECTION 5: RULE TAXONOMY -->
    <rule_categories>
        - COMPLETENESS: mandatory_field, conditional_mandatory, threshold
        - VALIDITY: data_type, range_check, enumeration, format_pattern
        - CONSISTENCY: cross_field, referential_integrity, temporal
        - ACCURACY: precision, tolerance, outlier_detection
        - UNIQUENESS: primary_key, composite_key
        - TIMELINESS: freshness, date_validity
    </rule_categories>

    <!-- SECTION 6: OUTPUT REQUIREMENTS -->
    <outputs>
        <json>data_quality_rules.json with full schema</json>
        <excel>data_quality_rules.xlsx with multiple sheets</excel>
    </outputs>

</data_quality_rules_derivation_prompt>
```

</details>

---

## Notes for Claude

When working on this project:

1. **Always check attribute matching** before generating rules
2. **Refer to the XML prompt** in `prompts/` for detailed specifications
3. **Follow the RAG pipeline stages** in order: ingest → chunk → embed → index → retrieve
4. **Test with sample data** before processing full datasets
5. **Log all operations** for debugging and audit trails

---

## Quick Reference Commands

```bash
# Install dependencies (using uv package manager)
uv sync

# Run tests
uv run pytest tests/ -v

# View available commands
uv run python main.py --help

# Cross-Tab based pipeline with shape constraints (RECOMMENDED)
uv run python main.py crosstab --verbose

# Cross-Tab with legacy GPT-4o mode (not recommended)
uv run python main.py crosstab --legacy --verbose

# Full pipeline with attribute matching
uv run python main.py run --verbose

# PDF-only pipeline
uv run python main.py pdf-only --verbose

# Profiling-based pipeline
uv run python main.py profiling --verbose
```

---

## Package Manager

This project uses **uv** as the package manager. All commands should be run with `uv run`.

```bash
# Install uv (if not already installed)
pip install uv

# Install project dependencies
uv sync

# Run any command
uv run python main.py <command>
```

---

## Wikipedia Scraping

Wikipedia definitions are scraped **at runtime** after attributes are identified:
- Definitions are fetched from Wikipedia's REST API
- Results are cached in `data/input/wikipedia/definitions_cache.json`
- Related electrical terms are also fetched for context

---

*Last Updated: January 2026*