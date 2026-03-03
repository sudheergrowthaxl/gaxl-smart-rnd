"""Configuration, environment variables, and dynamic helpers.

All category-specific logic is derived at runtime from backbone YAML files
or LLM reasoning -- no hardcoded product-specific constants.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_env_path)

OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
GROQ_API_KEY: str | None = os.getenv("GROQ_API_KEY")
TAVILY_API_KEY: str | None = os.getenv("TAVILY_API_KEY")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FEW_SHOT_PATH = PROJECT_ROOT / "Few_Shot_Examples.txt"
OUTPUT_RULES_FILE = PROJECT_ROOT / "Derived_Normalisation_Rules.xlsx"
TAVILY_LOGS_DIR = PROJECT_ROOT / "logs"
CURATED_VALUES_DIR = PROJECT_ROOT / "curated_values"

# Output paths for hierarchy pipeline
HIERARCHY_OUTPUT_CSV = PROJECT_ROOT / "standardized_hierarchies.csv"
HIERARCHY_CRAWLED_PATHS_JSON = PROJECT_ROOT / "manufacturer_crawled_paths.json"
HIERARCHY_RECOMMENDED_JSON = PROJECT_ROOT / "recommended_hierarchies.json"

# Output paths for attribute resolver pipeline
ATTRIBUTE_RESOLVER_OUTPUT_JSON = PROJECT_ROOT / "recommended_attributes.json"
ATTRIBUTE_RESOLVER_OUTPUT_CSV = PROJECT_ROOT / "standardized_attributes.csv"
ATTRIBUTE_RESOLVER_LOGS_DIR = PROJECT_ROOT / "logs"

# Knowledge base directory for backbone YAML files
KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge_base"

# Data directory for profiling outputs (auto-generated per dataset)
DATA_DIR = PROJECT_ROOT / "data"


# ---------------------------------------------------------------------------
# Timestamped output path helpers
# ---------------------------------------------------------------------------

def get_tavily_log_path_for_run() -> Path:
    TAVILY_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    return TAVILY_LOGS_DIR / f"tavily_context_{ts}.log"


def get_curated_values_path_for_run() -> Path:
    CURATED_VALUES_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    return CURATED_VALUES_DIR / f"curated_values_{ts}.json"


def get_attribute_resolver_log_path_for_run() -> Path:
    ATTRIBUTE_RESOLVER_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    return ATTRIBUTE_RESOLVER_LOGS_DIR / f"attribute_resolver_{ts}.log"


# ---------------------------------------------------------------------------
# API key helpers
# ---------------------------------------------------------------------------

def ensure_api_keys(use_openai: bool, use_groq: bool, use_tavily: bool) -> list[str]:
    missing = []
    if use_openai and not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    if use_groq and not GROQ_API_KEY:
        missing.append("GROQ_API_KEY")
    if use_tavily and not TAVILY_API_KEY:
        missing.append("TAVILY_API_KEY")
    return missing


def get_openai_client():
    from openai import OpenAI
    key = os.getenv("OPENAI_API_KEY") or OPENAI_API_KEY
    if not key or not str(key).strip():
        raise ValueError("OPENAI_API_KEY not set. Add it to .env or environment.")
    return OpenAI(api_key=key)


# ---------------------------------------------------------------------------
# Dynamic category list from Electrical_Components.docx
# ---------------------------------------------------------------------------

_categories_cache: list[str] | None = None


def get_categories_from_docx() -> list[str]:
    """Extract category names from Electrical_Components.docx tables and paragraphs.

    Returns a sorted list of category names. Falls back to an LLM-generated
    list if the docx file is missing or unreadable.
    """
    global _categories_cache
    if _categories_cache is not None:
        return _categories_cache

    docx_path = PROJECT_ROOT / "Electrical_Components.docx"
    if not docx_path.exists():
        _categories_cache = []
        return _categories_cache

    try:
        import docx
        doc = docx.Document(docx_path)
        extracted: set[str] = set()
        skip_lower = {
            "", "column 1", "column 2", "column 3", "s.no", "s. no",
            "serial number", "category", "component", "description",
        }
        for para in doc.paragraphs:
            text = para.text.strip()
            if text and len(text) < 80 and text.lower() not in skip_lower:
                extracted.add(text)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    text = cell.text.strip()
                    if text and len(text) < 80 and text.lower() not in skip_lower:
                        extracted.add(text)
        _categories_cache = sorted(extracted) if extracted else []
    except Exception:
        _categories_cache = []

    return _categories_cache


# ---------------------------------------------------------------------------
# Dynamic manufacturer list for a category
# ---------------------------------------------------------------------------

def get_manufacturers_for_category(category: str) -> list[str]:
    """Get manufacturers for a category from backbone YAML, or via LLM fallback."""
    bb = load_domain_backbone(category)
    domain = bb.get("domain", {})
    manufacturers = domain.get("manufacturers", [])
    if manufacturers:
        return manufacturers

    # LLM fallback: ask for top manufacturers of this category
    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": (
                f"List the top 5 global manufacturers of {category} "
                f"(industrial electrical equipment). "
                f"Output ONLY a JSON array of strings, e.g. "
                f'["ABB", "Siemens", "Schneider Electric", "Eaton", "Rockwell Automation"]'
            )}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or ""
        data = json.loads(content)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list):
                    return v
    except Exception:
        pass

    return ["ABB", "Siemens", "Schneider Electric", "Eaton", "Rockwell Automation"]


# ---------------------------------------------------------------------------
# Domain backbone loader
# ---------------------------------------------------------------------------

_backbone_cache: dict[str, dict] = {}


def load_domain_backbone(category: str) -> dict:
    """Load and cache the domain backbone YAML for a specific category.

    Tries knowledge_base/{category}.yaml first, falls back to default.yaml.
    """
    global _backbone_cache

    safe_category = category.lower().replace(" ", "_")

    if safe_category in _backbone_cache:
        return _backbone_cache[safe_category]

    backbone_path = KNOWLEDGE_BASE_DIR / f"{safe_category}.yaml"
    if not backbone_path.is_file():
        backbone_path = KNOWLEDGE_BASE_DIR / "default.yaml"
        if not backbone_path.is_file():
            _backbone_cache[safe_category] = {}
            return {}

    try:
        import yaml
        with open(backbone_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            _backbone_cache[safe_category] = data
            return data
    except Exception:
        _backbone_cache[safe_category] = {}
        return {}


def get_backbone_attributes_summary(category: str) -> str:
    """Return a compact text summary of backbone attributes for prompt injection."""
    bb = load_domain_backbone(category)
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


def get_backbone_invariants_summary(category: str) -> str:
    """Return a compact text summary of domain invariants for prompt injection."""
    bb = load_domain_backbone(category)
    invariants = bb.get("invariants", [])
    if not invariants:
        return ""
    return "\n".join(
        f"- {inv.get('id', '?')}: {inv.get('rule', '')} — {inv.get('description', '')}"
        for inv in invariants
    )


def get_backbone_normalization_for_attribute(attr_name: str, category: str) -> str:
    """Return normalization guidance for a specific attribute from the backbone."""
    bb = load_domain_backbone(category)
    norm = bb.get("normalization", {})
    attrs = bb.get("attributes", [])

    lines = []

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

    sep = norm.get("multi_value_separator")
    if sep:
        lines.append(f"Multi-value separator: {sep!r}")

    name_lower = attr_name.lower()
    for key, section in norm.items():
        if key == "multi_value_separator":
            continue
        if not isinstance(section, dict):
            continue
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
    key_lower = key.lower().replace("_", " ")
    keywords = key_lower.split()
    return any(kw in attr_name_lower for kw in keywords)
