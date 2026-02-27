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
ATTRIBUTE_RESOLVER_LOGS_DIR = PROJECT_ROOT / "logs"


def get_attribute_resolver_log_path_for_run() -> Path:
    """Return a unique log file path for an attribute resolver run (timestamped)."""
    ATTRIBUTE_RESOLVER_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    return ATTRIBUTE_RESOLVER_LOGS_DIR / f"attribute_resolver_{ts}.log"


# ---------------------------------------------------------------------------
# Domain backbone loader
# ---------------------------------------------------------------------------
DOMAIN_BACKBONE_PATH = PROJECT_ROOT / "domain_backbone.yaml"

_backbone_cache: dict | None = None


def load_domain_backbone() -> dict:
    """Load and cache the domain backbone YAML. Returns empty dict on failure."""
    global _backbone_cache
    if _backbone_cache is not None:
        return _backbone_cache

    if not DOMAIN_BACKBONE_PATH.is_file():
        _backbone_cache = {}
        return _backbone_cache

    try:
        import yaml
        with open(DOMAIN_BACKBONE_PATH, "r", encoding="utf-8") as f:
            _backbone_cache = yaml.safe_load(f) or {}
    except Exception:
        _backbone_cache = {}
    return _backbone_cache


def get_backbone_attributes_summary() -> str:
    """Return a compact text summary of backbone attributes for prompt injection."""
    bb = load_domain_backbone()
    attrs = bb.get("attributes", [])
    if not attrs:
        return ""

    lines = []
    for a in attrs:
        name = a.get("name", "")
        role = a.get("structural_role", "")
        dtype = a.get("data_type", "")
        tier = a.get("tier", "")
        deps = a.get("dependencies", [])
        dep_strs = [f"{d.get('attribute', '?')} ({d.get('type', '?')})" for d in deps]
        dep_text = "; ".join(dep_strs) if dep_strs else "none"
        unit = a.get("unit")
        unit_text = unit.get("base_unit", "") if isinstance(unit, dict) else "—"
        lines.append(
            f"- {name} | role={role} | type={dtype} | unit={unit_text} "
            f"| tier={tier} | deps=[{dep_text}]"
        )
    return "\n".join(lines)


def get_backbone_invariants_summary() -> str:
    """Return a compact text summary of domain invariants for prompt injection."""
    bb = load_domain_backbone()
    invariants = bb.get("invariants", [])
    if not invariants:
        return ""
    return "\n".join(
        f"- {inv.get('id', '?')}: {inv.get('rule', '')} — {inv.get('description', '')}"
        for inv in invariants
    )


def get_backbone_normalization_for_attribute(attr_name: str) -> str:
    """Return normalization guidance for a specific attribute from the backbone."""
    bb = load_domain_backbone()
    norm = bb.get("normalization", {})
    attrs = bb.get("attributes", [])

    lines = []

    # Find the attribute in backbone for structural metadata
    attr_meta = None
    for a in attrs:
        if a.get("name", "").lower() == attr_name.lower():
            attr_meta = a
            break

    if attr_meta:
        lines.append(f"Backbone metadata for '{attr_meta.get('name', '')}':")
        lines.append(f"  structural_role: {attr_meta.get('structural_role', '?')}")
        lines.append(f"  data_type: {attr_meta.get('data_type', '?')}")
        allowed = attr_meta.get("allowed_values")
        if allowed:
            lines.append(f"  allowed_values: {allowed}")
        unit = attr_meta.get("unit")
        if isinstance(unit, dict):
            lines.append(f"  unit: {unit.get('base_unit', '?')} ({unit.get('unit_system', '?')})")
        canon = attr_meta.get("canonical_format")
        if canon:
            lines.append(f"  canonical_format: {canon}")
        parse = attr_meta.get("parse_pattern")
        if parse:
            lines.append(f"  parse_pattern: {parse}")

    # Add general normalization patterns
    sep = norm.get("multi_value_separator")
    if sep:
        lines.append(f"Multi-value separator: {sep!r}")

    # Check specific normalization rules by keyword matching
    name_lower = attr_name.lower()
    for key, section in norm.items():
        if key == "multi_value_separator":
            continue
        if not isinstance(section, dict):
            continue
        # Match by key name similarity to attribute name
        if _norm_key_matches(key, name_lower):
            if "canonical" in section:
                lines.append(f"Canonical format: {section['canonical']}")
            if "canonical_values" in section:
                lines.append(f"Canonical values: {section['canonical_values']}")
            if "mappings" in section:
                lines.append("Mappings:")
                for src, tgt in section["mappings"].items():
                    lines.append(f"  {src!r} -> {tgt!r}")
            if "examples" in section:
                lines.append("Examples:")
                for ex in section["examples"]:
                    lines.append(f"  {ex.get('input', '?')} -> {ex.get('output', '?')}")
            if "pattern" in section:
                lines.append(f"Pattern: {section['pattern']}")

    return "\n".join(lines) if lines else ""


def _norm_key_matches(key: str, attr_name_lower: str) -> bool:
    """Check if a normalization section key is relevant to an attribute name."""
    key_lower = key.lower().replace("_", " ")
    keywords = key_lower.split()
    return any(kw in attr_name_lower for kw in keywords)
