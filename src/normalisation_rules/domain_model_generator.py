"""Runtime domain model generator.

Produces the full 7-section domain model via LLM for any
domain / sub-domain / category combination.  No static YAML files needed.

The generated model is persisted to ``data/domain_models/`` and returned
as a Python dict for session-state storage.
"""

import json
from datetime import datetime
from pathlib import Path

from normalisation_rules.config import get_openai_client, PROJECT_ROOT
from normalisation_rules.prompts.domain_model_prompt import (
    build_domain_model_prompt,
)

_SAVE_DIR = PROJECT_ROOT / "data" / "domain_models"


def generate_domain_model(
    domain: str,
    sub_domain: str,
    category: str,
    user_columns: list[str] | None = None,
    sample_values: dict | None = None,
    model: str = "gpt-4o",
) -> tuple[dict, Path]:
    """Generate the full 7-section domain model and persist to disk.

    Returns
    -------
    (domain_model_dict, saved_file_path)
    """
    prompt = build_domain_model_prompt(
        domain=domain,
        sub_domain=sub_domain,
        category=category,
        user_columns=user_columns,
        sample_values=sample_values,
    )

    client = get_openai_client()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=16000,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content or "{}"
    model_dict = json.loads(raw)

    _ensure_sections(model_dict, domain, sub_domain, category)

    save_path = _persist(model_dict, domain, sub_domain, category)
    return model_dict, save_path


def _ensure_sections(m: dict, domain: str, sub_domain: str, category: str):
    """Fill in any missing top-level sections with safe defaults."""
    m.setdefault("domain_overview", {})
    overview = m["domain_overview"]
    overview.setdefault("domain", domain)
    overview.setdefault("sub_domain", sub_domain)
    overview.setdefault("category", category)
    overview.setdefault("domain_summary", "")
    overview.setdefault("sub_domain_summary", "")
    overview.setdefault("functional_purpose", "")
    overview.setdefault("system_boundaries", "")

    m.setdefault("entities", {})
    for key in ("primary", "supporting_infrastructure", "control_and_monitoring",
                "safety_and_protection", "governance"):
        m["entities"].setdefault(key, [])

    m.setdefault("property_model", {})
    m.setdefault("ontology", {"namespace_prefix": "fso", "triplets": []})
    m.setdefault("terminology", [])
    m.setdefault("operational_logic", {
        "workflows": [], "energy_flow": "",
        "failure_conditions": [], "compliance_constraints": [],
    })
    m.setdefault("invariants", [])


def _persist(model_dict: dict, domain: str, sub_domain: str, category: str) -> Path:
    """Save the domain model JSON to data/domain_models/."""
    _SAVE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = lambda s: s.lower().replace(" ", "_").replace("/", "_")
    filename = f"{safe(domain)}_{safe(sub_domain)}_{safe(category)}_{ts}.json"
    path = _SAVE_DIR / filename
    path.write_text(
        json.dumps(model_dict, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Domain overview detection from data (extends existing category detection)
# ---------------------------------------------------------------------------

def detect_domain_overview(
    columns: list[str],
    sample_values: dict,
    filename: str,
    detected_category: str | None = None,
    model: str = "gpt-4o-mini",
) -> dict:
    """Detect domain, sub-domain, and category from dataset evidence.

    Returns dict with keys: domain, sub_domain, category, confidence, reasoning.
    """
    sample_block = "\n".join(
        f"  - {col}: {', '.join(str(v) for v in vals[:5])}"
        for col, vals in list(sample_values.items())[:25]
    )

    prompt = f"""You are a domain classification expert for product data.

Given a dataset with the following evidence, identify the DOMAIN, SUB-DOMAIN,
and CATEGORY of the products in this data.

**Filename**: {filename}
**Columns**: {columns[:50]}
**Sample values**:
{sample_block}
{f'**Previously detected category hint**: {detected_category}' if detected_category else ''}

**Definitions:**
- DOMAIN: The broadest classification (e.g., "Industrial Component", "Consumer Electronics", "Automotive Parts")
- SUB-DOMAIN: A narrower grouping within the domain (e.g., "Electrical Equipment", "Mechanical Components", "Pneumatic Systems")
- CATEGORY: The specific product type (e.g., "Contactors", "Circuit Breakers", "Limit Switches", "Relays")

**Output ONLY valid JSON:**
{{
  "domain": "the domain name",
  "sub_domain": "the sub-domain name",
  "category": "the specific product category",
  "confidence": 0.0,
  "reasoning": "brief explanation of why these were chosen"
}}
"""
    client = get_openai_client()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        result = json.loads(raw)
        result.setdefault("domain", "Unknown")
        result.setdefault("sub_domain", "Unknown")
        result.setdefault("category", detected_category or "Unknown")
        result.setdefault("confidence", 0.0)
        result.setdefault("reasoning", "")
        return result
    except Exception as exc:
        return {
            "domain": "Unknown",
            "sub_domain": "Unknown",
            "category": detected_category or "Unknown",
            "confidence": 0.0,
            "reasoning": f"Detection failed: {exc}",
        }
