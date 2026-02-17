"""Configuration and environment variables."""

import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (parent of src)
_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_env_path)

# API keys (required at runtime when using respective features)
OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
GROQ_API_KEY: str | None = os.getenv("GROQ_API_KEY")
TAVILY_API_KEY: str | None = os.getenv("TAVILY_API_KEY")

# When True, deduplicate the merged list of possible values (customer + standards + manufacturers)
_DEDUP_ENV = os.getenv("DEDUP_MERGED_VALUES", "true").strip().lower()
DEDUP_MERGED_VALUES: bool = _DEDUP_ENV in ("1", "true", "yes")

# Paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILING_JSON = PROJECT_ROOT / "Contactors_Profiling_distinct_values.json"
DEFAULT_FEW_SHOT_PATH = PROJECT_ROOT / "Few_Shot_Examples.txt"
DOMAIN = "Contactors"
OUTPUT_RULES_FILE = PROJECT_ROOT / "Derived_Normalisation_Rules.xlsx"
TAVILY_LOGS_DIR = PROJECT_ROOT / "logs"
CONTACTORS_DATASET_XLSX = PROJECT_ROOT / "Contactors_Dataset.xlsx"
CONTACTORS_COMPARISON_XLSX = PROJECT_ROOT / "Contactors_Normalisation_Comparison.xlsx"
GENERATED_NORMALISERS_JSON = PROJECT_ROOT / "generated_normalisers.json"


def get_tavily_log_path_for_run() -> Path:
    """Return a unique log file path for this run (logs dir, timestamped filename)."""
    TAVILY_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    return TAVILY_LOGS_DIR / f"tavily_context_{ts}.log"


def ensure_api_keys(use_openai: bool, use_groq: bool, use_tavily: bool) -> list[str]:
    """Return list of missing required API key names."""
    missing = []
    if use_openai and not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    if use_groq and not GROQ_API_KEY:
        missing.append("GROQ_API_KEY")
    if use_tavily and not TAVILY_API_KEY:
        missing.append("TAVILY_API_KEY")
    return missing
