# Normalisation Rules (Contactors)

Generative AI project to **derive normalisation rules** for Electrical Equipment (Contactors) using:

- **LangGraph** / **LangChain** for the orchestration workflow
- **OpenAI** and **Groq** as LLM providers
- **Tavily** for web search context per attribute
- **uv** for project and dependency management

Inputs:

- `Contactors_Profiling_distinct_values.json` – profiling statistics (distinct values, counts, datatypes) per attribute
- `Few_Shot_Examples.txt` – example rules used as few-shot prompts

The pipeline:

1. Load profiling JSON and select attributes (prioritising `zz_Auxiliary Contact`, `zz_Number of Poles`, `zz_Mounting Type`, `zz_Type`).
2. For each attribute, optionally run **Tavily** search to get domain/standard terminology context.
3. Invoke an **LLM** (OpenAI or Groq) with attribute stats + few-shot examples + web context to produce normalisation rules.
4. Write rules to `Derived_Normalisation_Rules.txt` in the same tab-separated format as the few-shot examples.

## Setup

1. **Install uv** (if not already): <https://docs.astral.sh/uv/getting-started/installation/>

2. **Clone/navigate to this folder** and create a virtualenv + install dependencies:

   ```bash
   uv sync
   ```

3. **API keys** (create a `.env` file in the project root):

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set:

   - **At least one LLM provider**
     - `OPENAI_API_KEY=sk-...` for OpenAI (e.g. gpt-4o-mini)
     - `GROQ_API_KEY=...` for Groq (e.g. llama-3.1-8b-instant)
   - **Optional:** `TAVILY_API_KEY=...` for web search context (if unset, the pipeline runs without Tavily).

## Usage

- **Default (OpenAI + Tavily, all suitable attributes):**

  ```bash
  uv run normalisation-rules
  ```

- **Use Groq instead of OpenAI:**

  ```bash
  uv run normalisation-rules --provider groq
  ```

- **Only priority attributes** (zz_Auxiliary Contact, zz_Number of Poles, zz_Mounting Type, zz_Type):

  ```bash
  uv run normalisation-rules --priority-only
  ```

- **Limit number of attributes** (e.g. first 4):

  ```bash
  uv run normalisation-rules --priority-only --limit 4
  ```

- **Custom paths and output:**

  ```bash
  uv run normalisation-rules --profiling path/to/profiling.json --few-shot path/to/examples.txt -o MyRules.txt
  ```

- **Skip Tavily** (no web search; only profiling + few-shot):

  ```bash
  uv run normalisation-rules --no-tavily
  ```

When Tavily is used, the terminal shows `[Tavily] Using web search for attribute: <name>` and `[Tavily] Returned N chars of context` per attribute. The full context returned by Tavily is written to a **per-run log file** in the `logs/` directory, e.g. `logs/tavily_context_2025-02-10_14-30-22.log` (timestamp, attribute, query, and response text for that run).

- **Specific model:**

  ```bash
  uv run normalisation-rules --provider openai --model gpt-4o
  uv run normalisation-rules --provider groq --model llama-3.1-70b-versatile
  ```

- **Generate approach document (Word):** To create the methodology document `Approach_to_Normalisation_Rules.docx` in the project root, run:

  ```bash
  uv run python scripts/generate_approach_doc.py
  ```

Output is written to `Derived_Normalisation_Rules.txt` (or the path given by `-o`), one rule per line:  
`Contactors\t<Attribute>\tNormalization\t<Rule description>`.

## Project layout

```
Normalisation_Rules/
├── pyproject.toml              # uv / project config and dependencies
├── .env.example                 # Template for API keys
├── README.md                    # This file
├── Contactors_Profiling_distinct_values.json
├── Few_Shot_Examples.txt
├── Derived_Normalisation_Rules.xlsx  # Generated rules (after run)
├── Approach_to_Normalisation_Rules.docx  # Approach document (run scripts/generate_approach_doc.py)
├── logs/                             # Per-run Tavily logs (tavily_context_YYYY-MM-DD_HH-MM-SS.log)
├── scripts/
│   └── generate_approach_doc.py      # Generates the approach document (.docx)
└── src/
    └── normalisation_rules/
        ├── __init__.py
        ├── config.py             # Paths and env (OPENAI/GROQ/TAVILY)
        ├── data_loader.py       # Load JSON, extract attributes
        ├── tavily_context.py     # Tavily search per attribute
        ├── state.py              # LangGraph state
        ├── prompts.py            # System/user prompts
        ├── models.py             # get_llm(openai | groq)
        ├── graph.py             # LangGraph: fetch_context -> derive_rules
        └── cli.py               # Entrypoint: normalisation-rules
```

## Dependencies (uv)

- `langgraph` – workflow graph
- `langchain`, `langchain-core` – chain and messages
- `langchain-openai` – OpenAI chat
- `langchain-groq` – Groq chat
- `tavily-python` – Tavily search API
- `python-dotenv` – load `.env`
- `python-docx` – generate approach document (Word)

All managed via `pyproject.toml`; run `uv sync` to install.
