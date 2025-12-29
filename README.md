# Ontology Ruleset Builder

## Overview
A production-ready Generative AI pipeline using LangGraph, LangChain, and OpenAI to identify core classes (e.g., "Contactors") from customer raw data (Excel/JSON), derive validation/normalization rules based on schema examples, and build a Customer Ontology Ruleset JSON. Handles real-world data like product attributes (e.g., `zz_Contact Current Rating`).

### Key Workflow (LangGraph Nodes)
- **Ingestion**: Loads raw data (`a7e6e2fc-6699-495a-9669-ec91804103f4_out 1 (1).xlsx`), profiling (`python_profiling 3.json`), and schema (`EDB-DQ-Shape Rules.xlsx`).
- **Class Identification**: Analyzes `RS Product Category`, `zz_Type`, `dr_Series` for core/sub-classes (e.g., "Contactors" → "IEC Contactor", "TeSys Deca Series").
- **Rule Derivation**: Uses few-shot LLM prompts to generate rules (e.g., Range Validation: 6A–800A for current ratings; Normalization: "3P" → 3).
- **Ontology Building**: Compiles into Pydantic-modeled JSON ruleset.
- **Validation**: Simulates rules on sample data, computes pass rates.

Identified Classes Example:
- Core: Contactors
- Sub-Classes: IEC Contactor, Definite Purpose Contactor (from low-sparsity attrs in profiling).

Derived Rules Example:
- `zz_Contact Current Rating` (Validation): "Anything outside 6 A – 800 A is not valid" → Range Validator.
- High-missing attrs (>90% sparsity) → Mandatory Validation.
