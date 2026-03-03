"""Configuration, environment variables, and dynamic helpers.

All category-specific logic is derived at runtime via LLM-generated domain
models — no static YAML backbone files.  The domain model is produced once
per session and passed through as a dict.
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
# Dynamic manufacturer list for a category (LLM-only, no YAML)
# ---------------------------------------------------------------------------

def get_manufacturers_for_category(category: str, domain_model: dict | None = None) -> list[str]:
    """Get manufacturers for a category via LLM or from the runtime domain model."""
    if domain_model:
        gov = domain_model.get("entities", {}).get("governance", [])
        mfrs = [e.get("name", "") for e in gov if e.get("type") == "external" and e.get("name")]
        if mfrs:
            return mfrs

    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": (
                f"List the top 5 global manufacturers of {category}. "
                f"Output ONLY a JSON object with key 'manufacturers' containing an array of strings."
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
# Runtime domain model helpers (read from LLM-generated dict, not YAML)
# ---------------------------------------------------------------------------

def get_domain_model_context(domain_model: dict) -> str:
    """Build a compact text summary from the runtime domain model for prompt injection."""
    if not domain_model:
        return ""

    parts = []
    ov = domain_model.get("domain_overview", {})
    if ov:
        parts.append(
            f"Domain: {ov.get('domain', '?')} > {ov.get('sub_domain', '?')} > {ov.get('category', '?')}\n"
            f"Purpose: {ov.get('functional_purpose', '')}\n"
            f"Boundaries: {ov.get('system_boundaries', '')}"
        )

    entities = domain_model.get("entities", {})
    for group, items in entities.items():
        if items:
            names = [e.get("name", "?") for e in items[:10]]
            parts.append(f"{group}: {', '.join(names)}")

    pm = domain_model.get("property_model", {})
    if pm:
        for entity, groups in list(pm.items())[:3]:
            all_props = []
            for group_name, props in groups.items():
                if isinstance(props, list):
                    all_props.extend(props[:5])
            if all_props:
                parts.append(f"Properties of {entity}: {', '.join(all_props[:15])}")

    triplets = domain_model.get("ontology", {}).get("triplets", [])
    if triplets:
        trip_strs = [f"({t[0]}, {t[1]}, {t[2]})" for t in triplets[:10]]
        parts.append(f"Ontology ({len(triplets)} triplets): {'; '.join(trip_strs)}")

    invariants = domain_model.get("invariants", [])
    if invariants:
        inv_strs = [f"{i.get('id','')}: {i.get('rule','')}" for i in invariants[:8]]
        parts.append(f"Invariants: {'; '.join(inv_strs)}")

    return "\n".join(parts)


def get_domain_entities_summary(domain_model: dict) -> str:
    """Return entities section as formatted text."""
    if not domain_model:
        return ""
    entities = domain_model.get("entities", {})
    lines = []
    for group, items in entities.items():
        if items:
            lines.append(f"**{group.replace('_', ' ').title()}**:")
            for e in items:
                lines.append(f"  - {e.get('name', '?')} ({e.get('type', '?')}): {e.get('description', '')}")
    return "\n".join(lines)


def get_domain_property_model_summary(domain_model: dict) -> str:
    """Return property model as formatted text."""
    if not domain_model:
        return ""
    pm = domain_model.get("property_model", {})
    lines = []
    for entity, groups in pm.items():
        lines.append(f"**{entity}**:")
        for group_name, props in groups.items():
            if isinstance(props, list) and props:
                lines.append(f"  {group_name}: {', '.join(str(p) for p in props)}")
    return "\n".join(lines)


def get_domain_ontology_summary(domain_model: dict) -> str:
    """Return ontology triplets as formatted text."""
    if not domain_model:
        return ""
    onto = domain_model.get("ontology", {})
    triplets = onto.get("triplets", [])
    if not triplets:
        return ""
    lines = [f"Namespace: {onto.get('namespace_prefix', 'fso')}"]
    for t in triplets:
        if len(t) >= 3:
            lines.append(f"  ({t[0]}, {t[1]}, {t[2]})")
    return "\n".join(lines)


def get_domain_invariants_summary(domain_model: dict) -> str:
    """Return invariants as formatted text."""
    if not domain_model:
        return ""
    invariants = domain_model.get("invariants", [])
    if not invariants:
        return ""
    return "\n".join(
        f"- {inv.get('id', '?')}: {inv.get('rule', '')} — {inv.get('description', '')}"
        for inv in invariants
    )


def get_domain_normalization_context(domain_model: dict, attr_name: str) -> str:
    """Extract normalization-relevant context for an attribute from the domain model."""
    if not domain_model:
        return ""

    lines = []
    pm = domain_model.get("property_model", {})
    for entity, groups in pm.items():
        for group_name, props in groups.items():
            if isinstance(props, list):
                for p in props:
                    p_str = str(p).lower()
                    if attr_name.lower() in p_str:
                        lines.append(f"Domain model property match: {entity} > {group_name} > {p}")

    terminology = domain_model.get("terminology", [])
    for t in terminology:
        if attr_name.lower() in t.get("term", "").lower():
            lines.append(
                f"Terminology: {t.get('term', '')} — {t.get('definition', '')}\n"
                f"  Functional role: {t.get('functional_role', '')}"
            )

    invariants = domain_model.get("invariants", [])
    for inv in invariants:
        if attr_name.lower() in inv.get("rule", "").lower() or attr_name.lower() in inv.get("description", "").lower():
            lines.append(f"Invariant {inv.get('id','')}: {inv.get('rule','')} — {inv.get('description','')}")

    return "\n".join(lines) if lines else ""
