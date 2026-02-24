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

# Paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILING_JSON = PROJECT_ROOT / "Contactors_Profiling_distinct_values.json"
DEFAULT_FEW_SHOT_PATH = PROJECT_ROOT / "Few_Shot_Examples.txt"
DOMAIN = "Contactors"
OUTPUT_RULES_FILE = PROJECT_ROOT / "Derived_Normalisation_Rules.xlsx"
TAVILY_LOGS_DIR = PROJECT_ROOT / "logs"
CURATED_VALUES_DIR = PROJECT_ROOT / "curated_values"

# Default manufacturers to search for catalog values (configurable via CLI)
DEFAULT_MANUFACTURERS = [
    "ABB",
    "Eaton Cutler Hammer",
    "Schneider Electric",
    "Siemens",
    "Square D",
]


def get_tavily_log_path_for_run() -> Path:
    """Return a unique log file path for this run (logs dir, timestamped filename)."""
    TAVILY_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    return TAVILY_LOGS_DIR / f"tavily_context_{ts}.log"


def get_curated_values_path_for_run() -> Path:
    """Return a unique JSON file path for curated values output (timestamped)."""
    CURATED_VALUES_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    return CURATED_VALUES_DIR / f"curated_values_{ts}.json"


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


def get_openai_client():
    """Return a raw OpenAI client instance (used by hierarchy and attribute resolver)."""
    from openai import OpenAI
    key = OPENAI_API_KEY
    if not key or not str(key).strip():
        raise ValueError("OPENAI_API_KEY not set. Add it to .env or environment.")
    return OpenAI(api_key=key)


# Output paths for hierarchy pipeline
HIERARCHY_OUTPUT_CSV = PROJECT_ROOT / "standardized_hierarchies.csv"
HIERARCHY_CRAWLED_PATHS_JSON = PROJECT_ROOT / "manufacturer_crawled_paths.json"
HIERARCHY_RECOMMENDED_JSON = PROJECT_ROOT / "recommended_hierarchies.json"

# Output paths for attribute resolver pipeline
ATTRIBUTE_RESOLVER_OUTPUT_JSON = PROJECT_ROOT / "recommended_attributes.json"
ATTRIBUTE_RESOLVER_OUTPUT_CSV = PROJECT_ROOT / "standardized_attributes.csv"
