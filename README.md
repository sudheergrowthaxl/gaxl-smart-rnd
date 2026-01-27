# Data Quality Rules Derivation Pipeline

A production-grade RAG (Retrieval-Augmented Generation) pipeline for deriving data quality rules from ABB contactors and relays technical specifications.

## Features

- **PDF Ingestion**: Extract text, tables, and images from ABB technical PDFs
- **Semantic Chunking**: Context-aware document chunking with token limits
- **Vector Database**: ChromaDB-based storage with hybrid search
- **Attribute Matching**: Fuzzy matching between cross-tab ontology and RAG specs
- **Rule Generation**: GPT-4o powered data quality rule derivation
- **Multi-format Export**: JSON and Excel output with comprehensive documentation

## Installation

```bash
# Install dependencies using uv
uv sync

# Or using pip
pip install -e .
```

## Configuration

1. Set your OpenAI API key:
```bash
export OPENAI_API_KEY=sk-...
```

2. Review configuration in `config/config.yaml`

## Usage

### Run Full Pipeline
```bash
python main.py run --config config/config.yaml
```

### Ingest PDFs
```bash
python main.py ingest --pdf-path data/input/pdfs/
```

### Generate Rules for Specific Attributes
```bash
python main.py generate --attributes rated_current,rated_voltage
```

### Export Rules
```bash
python main.py export --format excel --output data/output/rules.xlsx
```

## Project Structure

```
├── config/              # Configuration files
├── src/
│   ├── ingestion/       # PDF processing
│   ├── chunking/        # Document chunking
│   ├── embedding/       # Vector embeddings
│   ├── vectordb/        # ChromaDB integration
│   ├── retrieval/       # RAG retrieval
│   ├── data_sources/    # Data loaders
│   ├── matching/        # Attribute matching
│   ├── rules/           # Rule generation
│   └── exporters/       # Output generation
├── data/
│   ├── input/           # Input data
│   └── output/          # Generated outputs
└── main.py              # Entry point
```

## License

MIT
