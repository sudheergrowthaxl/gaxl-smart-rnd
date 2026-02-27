"""
Attribute resolver for Contactors category (Electrical equipment domain).
Gathers attributes from: (1) Standards (UNSPSC, IEC, NEMA), (2) Manufacturer sites/technical specs (Tavily),
(3) Contactors dataset; then builds a canonical backbone schema with structural classification,
and projects supply chain and ecommerce views from that backbone.

All pipeline activity is logged to a timestamped file under ``logs/``.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd

from normalisation_rules.config import (
    get_openai_client,
    PROJECT_ROOT,
    get_attribute_resolver_log_path_for_run,
    load_domain_backbone,
    get_backbone_attributes_summary,
)
from normalisation_rules.prompts.attribute_resolver_prompt import (
    build_standards_extraction_prompt,
    build_manufacturer_extraction_prompt,
    build_backbone_modeling_prompt,
    build_lens_projection_prompt,
)


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def _log_block(log_path: Path | None, label: str, body: str) -> None:
    """Append a timestamped block to the run log file."""
    if not log_path:
        return
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    block = (
        f"\n{'=' * 72}\n"
        f"[{ts}]  {label}\n"
        f"{'-' * 72}\n"
        f"{body}\n"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(block)


# ---------------------------------------------------------------------------
# Tavily search helper
# ---------------------------------------------------------------------------

def _get_tavily_client():
    """Return TavilyClient; raises if TAVILY_API_KEY not set."""
    key = os.getenv("TAVILY_API_KEY")
    if not key or not str(key).strip():
        raise ValueError("TAVILY_API_KEY not set. Add it to .env or environment.")
    from tavily import TavilyClient
    return TavilyClient(api_key=key)


def _tavily_search(
    query: str,
    max_results: int = 5,
    log_path: Path | None = None,
) -> str:
    """Run Tavily search and return concatenated context text."""
    _log_block(log_path, "TAVILY SEARCH", f"Query: {query}\nMax results: {max_results}")
    client = _get_tavily_client()
    response = client.search(
        query=query,
        max_results=max_results,
        include_raw_content=True,
        search_depth="advanced",
    )
    parts = []
    for r in response.get("results", []):
        url = r.get("url", "")
        title = r.get("title", "")
        content = r.get("raw_content") or r.get("content") or ""
        if content:
            parts.append(f"## {title}\nURL: {url}\n\n{content[:15000]}")
    text = "\n\n---\n\n".join(parts) if parts else ""
    _log_block(
        log_path,
        "TAVILY RESULT",
        f"Query: {query}\nResults count: {len(parts)}\n\n{text[:3000]}{'...(truncated)' if len(text) > 3000 else ''}",
    )
    return text


# ---------------------------------------------------------------------------
# 1. Attributes from Contactors dataset
# ---------------------------------------------------------------------------

def get_attributes_from_dataset(
    dataset_path: str,
    log_path: Path | None = None,
) -> Dict[str, Any]:
    """Load Contactors_Dataset.xlsx and extract column names as attributes."""
    _log_block(log_path, "DATASET LOAD – START", f"Path: {dataset_path}")
    if not os.path.isfile(dataset_path):
        err = f"Dataset file not found: {dataset_path}"
        _log_block(log_path, "DATASET LOAD – ERROR", err)
        return {
            "attributes": [],
            "columns": [],
            "raw_excerpt": "",
            "error": err,
        }
    try:
        df = pd.read_excel(dataset_path)
    except Exception as e:
        _log_block(log_path, "DATASET LOAD – ERROR", str(e))
        return {"attributes": [], "columns": [], "raw_excerpt": "", "error": str(e)}

    columns = list(df.columns)
    attributes = []
    sample_parts = []
    for col in columns:
        sample = ""
        for v in df[col].dropna().head(1):
            sample = str(v).strip()[:200]
            break
        attributes.append({"name": col, "source": "Contactors_Dataset", "sample": sample or ""})
        if sample:
            sample_parts.append(f"{col}: {sample}")

    _log_block(
        log_path,
        "DATASET LOAD – DONE",
        f"Columns ({len(columns)}): {columns}\n\nSample excerpt:\n" + "\n".join(sample_parts[:30]),
    )
    return {
        "attributes": attributes,
        "columns": columns,
        "raw_excerpt": "\n".join(sample_parts[:50]) if sample_parts else "",
    }


# ---------------------------------------------------------------------------
# 2. Attributes from standards (UNSPSC, IEC, NEMA) via Tavily
# ---------------------------------------------------------------------------

STANDARD_SEARCH_QUERIES = [
    "UNSPSC electrical equipment contactors attributes properties",
    "IEC 60947 contactor specifications attributes list",
    "IEC 60947-4-1 contactor rated voltage current attributes",
    "NEMA contactor specifications attributes ratings",
]


def get_attributes_from_standards(
    category: str,
    timeout: int = 15,
    max_results_per_query: int = 3,
    log_path: Path | None = None,
) -> Dict[str, Any]:
    """Use Tavily search for UNSPSC/IEC/NEMA attribute context, then AI extraction."""
    _log_block(log_path, "STANDARDS SEARCH – START", f"Category: {category}")
    combined_text = []
    for q in STANDARD_SEARCH_QUERIES:
        try:
            text = _tavily_search(q, max_results=max_results_per_query, log_path=log_path)
            if text:
                combined_text.append(f"### Query: {q}\n\n{text}")
        except Exception as e:
            _log_block(log_path, "STANDARDS SEARCH – QUERY ERROR", f"Query: {q}\nError: {e}")
            combined_text.append(f"### Query: {q}\nError: {e}")
    raw_excerpt = "\n\n---\n\n".join(combined_text)[:50000]

    if not raw_excerpt.strip():
        _log_block(log_path, "STANDARDS SEARCH – NO CONTENT", "All queries returned empty.")
        return {"attributes": [], "raw_excerpt": "", "error": "No content from standards search."}

    client = get_openai_client()
    prompt = build_standards_extraction_prompt(raw_excerpt)
    _log_block(log_path, "STANDARDS AI EXTRACTION – PROMPT", prompt[:5000] + ("...(truncated)" if len(prompt) > 5000 else ""))
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        _log_block(log_path, "STANDARDS AI EXTRACTION – RAW RESPONSE", content or "(empty)")
        if not content:
            return {"attributes": [], "raw_excerpt": raw_excerpt[:2000]}
        out = json.loads(content)
        out.setdefault("attributes", [])
        out["raw_excerpt"] = raw_excerpt[:2000]
        _log_block(log_path, "STANDARDS AI EXTRACTION – PARSED", f"Attributes extracted: {len(out['attributes'])}")
        return out
    except (json.JSONDecodeError, TypeError) as e:
        _log_block(log_path, "STANDARDS AI EXTRACTION – ERROR", str(e))
        return {"attributes": [], "raw_excerpt": raw_excerpt[:2000], "error": str(e)}


# ---------------------------------------------------------------------------
# 3. Attributes from manufacturer sites via Tavily
# ---------------------------------------------------------------------------

MANUFACTURER_SEARCH_QUERIES = [
    "contactors technical specifications datasheet attributes Schneider Siemens Eaton Rockwell",
    "contactor product attributes specifications site:se.com",
]


def get_attributes_from_manufacturer_sites(
    category: str,
    max_search_results: int = 5,
    log_path: Path | None = None,
) -> Dict[str, Any]:
    """Use Tavily search for manufacturer content, then AI extraction."""
    _log_block(log_path, "MANUFACTURER SEARCH – START", f"Category: {category}")
    combined_text = []
    for q in MANUFACTURER_SEARCH_QUERIES:
        try:
            text = _tavily_search(q, max_results=max_search_results, log_path=log_path)
            if text:
                combined_text.append(f"### Query: {q}\n\n{text}")
        except Exception as e:
            _log_block(log_path, "MANUFACTURER SEARCH – QUERY ERROR", f"Query: {q}\nError: {e}")
            combined_text.append(f"### Query: {q}\nError: {e}")
    raw_excerpt = "\n\n---\n\n".join(combined_text)[:50000]

    if not raw_excerpt.strip():
        _log_block(log_path, "MANUFACTURER SEARCH – NO CONTENT", "All queries returned empty.")
        return {"attributes": [], "raw_excerpt": "", "error": "No content from manufacturer search."}

    client = get_openai_client()
    prompt = build_manufacturer_extraction_prompt(raw_excerpt)
    _log_block(log_path, "MANUFACTURER AI EXTRACTION – PROMPT", prompt[:5000] + ("...(truncated)" if len(prompt) > 5000 else ""))
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        _log_block(log_path, "MANUFACTURER AI EXTRACTION – RAW RESPONSE", content or "(empty)")
        if not content:
            return {"attributes": [], "raw_excerpt": raw_excerpt[:2000]}
        out = json.loads(content)
        out.setdefault("attributes", [])
        out["raw_excerpt"] = raw_excerpt[:2000]
        _log_block(log_path, "MANUFACTURER AI EXTRACTION – PARSED", f"Attributes extracted: {len(out['attributes'])}")
        return out
    except (json.JSONDecodeError, TypeError) as e:
        _log_block(log_path, "MANUFACTURER AI EXTRACTION – ERROR", str(e))
        return {"attributes": [], "raw_excerpt": raw_excerpt[:2000], "error": str(e)}


# ---------------------------------------------------------------------------
# 4. Backbone modeling: canonical schema with structural classification
# ---------------------------------------------------------------------------

_VALID_STRUCTURAL_ROLES = {"identity", "variant-defining", "descriptive", "contextual"}
_VALID_DATA_TYPES = {"scalar", "range", "enumeration", "boolean", "conditional", "composite"}
_VALID_STABILITY = {"high", "medium", "low"}


def _validate_backbone_attribute(attr: dict) -> dict:
    """Ensure all required backbone fields exist with valid defaults."""
    attr.setdefault("name", "")
    attr.setdefault("description", "")
    if attr.get("structural_role") not in _VALID_STRUCTURAL_ROLES:
        attr["structural_role"] = "descriptive"
    if attr.get("data_type") not in _VALID_DATA_TYPES:
        attr["data_type"] = "scalar"
    attr.setdefault("unit", None)
    attr.setdefault("dependencies", [])
    attr.setdefault("intrinsic", True)
    attr.setdefault("standards_defined", False)
    if attr.get("cross_manufacturer_stability") not in _VALID_STABILITY:
        attr["cross_manufacturer_stability"] = "medium"

    conf = attr.get("confidence")
    if not isinstance(conf, dict):
        conf = {}
    for key in ("ontological_necessity", "cross_manufacturer_stability", "standards_coverage"):
        try:
            conf[key] = max(0.0, min(1.0, float(conf.get(key, 0.5))))
        except (TypeError, ValueError):
            conf[key] = 0.5
    conf["composite"] = round(
        0.5 * conf["ontological_necessity"]
        + 0.3 * conf["cross_manufacturer_stability"]
        + 0.2 * conf["standards_coverage"],
        3,
    )
    attr["confidence"] = conf

    attr.setdefault("sources", [])
    attr.setdefault("rationale", "")
    return attr


def model_backbone_schema(
    attributes_from_standards: Dict[str, Any],
    attributes_from_manufacturers: Dict[str, Any],
    attributes_from_dataset: Dict[str, Any],
    category: str,
    model: str = "gpt-4o-mini",
    log_path: Path | None = None,
) -> Dict[str, Any]:
    """
    Build the canonical backbone schema from gathered evidence.
    Returns dict with 'reasoning' and 'backbone' (list of structurally classified attributes).
    """
    _log_block(log_path, "BACKBONE MODELING – START", f"Category: {category} | Model: {model}")
    standards_attrs = attributes_from_standards.get("attributes", [])
    standards_preview = json.dumps(standards_attrs, indent=2) if standards_attrs else "None"
    manu_attrs = attributes_from_manufacturers.get("attributes", [])
    manu_preview = json.dumps(manu_attrs, indent=2) if manu_attrs else "None"
    dataset_attrs = attributes_from_dataset.get("attributes", [])
    dataset_preview = json.dumps(dataset_attrs, indent=2) if dataset_attrs else "None"
    dataset_excerpt = (attributes_from_dataset.get("raw_excerpt") or "")[:1500]

    _log_block(
        log_path,
        "BACKBONE MODELING – EVIDENCE SUMMARY",
        f"Standards attributes: {len(standards_attrs)}\n"
        f"Manufacturer attributes: {len(manu_attrs)}\n"
        f"Dataset attributes: {len(dataset_attrs)}",
    )

    prompt = build_backbone_modeling_prompt(
        standards_preview, manu_preview, dataset_preview, dataset_excerpt,
    )
    _log_block(log_path, "BACKBONE MODELING – PROMPT", prompt[:8000] + ("...(truncated)" if len(prompt) > 8000 else ""))
    client = get_openai_client()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        _log_block(log_path, "BACKBONE MODELING – RAW RESPONSE", content or "(empty)")
        if not content:
            _log_block(log_path, "BACKBONE MODELING – ERROR", "Empty response from LLM")
            return {"error": "Empty response", "reasoning": "", "backbone": []}
        out = json.loads(content)
        out.setdefault("reasoning", "")
        out.setdefault("backbone", [])
        out["backbone"] = [_validate_backbone_attribute(a) for a in out["backbone"]]
        _log_block(
            log_path,
            "BACKBONE MODELING – DONE",
            f"Attributes modeled: {len(out['backbone'])}\n"
            f"Reasoning (excerpt): {out['reasoning'][:1000]}",
        )
        return out
    except (json.JSONDecodeError, TypeError) as e:
        _log_block(log_path, "BACKBONE MODELING – ERROR", f"JSON parse failed: {e}")
        return {"error": f"JSON parse failed: {e}", "reasoning": "", "backbone": []}


# ---------------------------------------------------------------------------
# 5. Lens projection: derive supply chain and ecommerce views from backbone
# ---------------------------------------------------------------------------

def project_lenses(
    backbone: list[dict],
    model: str = "gpt-4o-mini",
    log_path: Path | None = None,
) -> Dict[str, Any]:
    """
    Project the canonical backbone into supply chain and ecommerce views.
    Returns dict with 'supply_chain' and 'ecommerce' lists.
    """
    _log_block(log_path, "LENS PROJECTION – START", f"Backbone size: {len(backbone)} | Model: {model}")
    if not backbone:
        _log_block(log_path, "LENS PROJECTION – SKIP", "Empty backbone; nothing to project.")
        return {"supply_chain": [], "ecommerce": []}

    backbone_json = json.dumps(backbone, indent=2)
    prompt = build_lens_projection_prompt(backbone_json)
    _log_block(log_path, "LENS PROJECTION – PROMPT", prompt[:8000] + ("...(truncated)" if len(prompt) > 8000 else ""))
    client = get_openai_client()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        _log_block(log_path, "LENS PROJECTION – RAW RESPONSE", content or "(empty)")
        if not content:
            _log_block(log_path, "LENS PROJECTION – ERROR", "Empty response from LLM")
            return {"supply_chain": [], "ecommerce": []}
        out = json.loads(content)
        out.setdefault("supply_chain", [])
        out.setdefault("ecommerce", [])
        _log_block(
            log_path,
            "LENS PROJECTION – DONE",
            f"Supply chain attributes: {len(out['supply_chain'])}\n"
            f"Ecommerce attributes: {len(out['ecommerce'])}",
        )
        return out
    except (json.JSONDecodeError, TypeError) as e:
        _log_block(log_path, "LENS PROJECTION – ERROR", f"JSON parse failed: {e}")
        return {"supply_chain": [], "ecommerce": []}


# ---------------------------------------------------------------------------
# 6. Main workflow and outputs
# ---------------------------------------------------------------------------

def standardize_attributes(
    category: str = "contactors",
    dataset_path: str | None = None,
    output_dir: str = ".",
    output_json_path: str | None = None,
    output_csv_path: str | None = None,
    max_search_results: int = 5,
) -> tuple[Dict[str, Any], List[Dict[str, Any]], Path]:
    """
    Run the full workflow: gather evidence -> backbone modeling -> lens projection.
    Returns (full_result_dict, list of backbone rows for CSV, log_file_path).
    """
    log_path = get_attribute_resolver_log_path_for_run()
    _log_block(log_path, "PIPELINE START", f"Category: {category}\nLog file: {log_path}")

    bb = load_domain_backbone()
    bb_attrs = bb.get("attributes", [])
    bb_inv = bb.get("invariants", [])
    if bb_attrs:
        summary = get_backbone_attributes_summary()
        _log_block(
            log_path,
            "BACKBONE LOADED",
            f"Attributes: {len(bb_attrs)} | Invariants: {len(bb_inv)}\n\n{summary}",
        )
        print(f"  [Backbone] Loaded {len(bb_attrs)} canonical attributes, {len(bb_inv)} invariants from domain_backbone.yaml")
    else:
        _log_block(log_path, "BACKBONE", "domain_backbone.yaml not found or empty — running without canonical grounding.")
        print("  [Backbone] domain_backbone.yaml not found — running without canonical grounding")

    config_path = PROJECT_ROOT / "config.yaml"
    if config_path.is_file():
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            attrs_cfg = cfg.get("attributes") or {}
            if not dataset_path:
                dataset_path = attrs_cfg.get("contactors_dataset_path")
            if max_search_results == 5:
                max_search_results = attrs_cfg.get("max_search_results", 5)
            if not output_json_path:
                output_json_path = attrs_cfg.get("output_json_path")
            if not output_csv_path:
                output_csv_path = attrs_cfg.get("output_csv_path")
            _log_block(log_path, "CONFIG", f"Loaded overrides from {config_path}")
        except Exception as exc:
            _log_block(log_path, "CONFIG WARNING", f"Failed to load config.yaml: {exc}")

    default_dataset = str(PROJECT_ROOT / "Contactors_Dataset.xlsx")
    dataset_path = dataset_path or default_dataset
    output_json_path = output_json_path or "recommended_attributes.json"
    output_csv_path = output_csv_path or "standardized_attributes.csv"

    _log_block(
        log_path,
        "RESOLVED PARAMETERS",
        f"dataset_path: {dataset_path}\n"
        f"output_json_path: {output_json_path}\n"
        f"output_csv_path: {output_csv_path}\n"
        f"max_search_results: {max_search_results}",
    )

    # Step 1-3: evidence gathering
    print(f"  [Log] {log_path}")
    print("  [Standards] Searching UNSPSC, IEC, NEMA via Tavily...")
    from_standards = get_attributes_from_standards(
        category, max_results_per_query=max_search_results, log_path=log_path,
    )

    print("  [Manufacturers] Searching manufacturer sites via Tavily...")
    from_manufacturers = get_attributes_from_manufacturer_sites(
        category, max_search_results=max_search_results, log_path=log_path,
    )

    print(f"  [Dataset] Loading from: {dataset_path}")
    from_dataset = get_attributes_from_dataset(dataset_path, log_path=log_path)

    # Step 4: backbone modeling
    print("  [Backbone] Building canonical schema with structural classification...")
    backbone_result = model_backbone_schema(
        from_standards, from_manufacturers, from_dataset, category, log_path=log_path,
    )
    backbone = backbone_result.get("backbone", [])
    print(f"  [Backbone] {len(backbone)} attributes modeled")

    # Step 5: lens projection
    print("  [Lenses] Projecting supply chain and ecommerce views...")
    lenses = project_lenses(backbone, log_path=log_path)
    print(f"  [Lenses] Supply chain: {len(lenses.get('supply_chain', []))} | "
          f"Ecommerce: {len(lenses.get('ecommerce', []))}")

    # Build backbone name lookup for lens enrichment
    backbone_by_name = {a["name"]: a for a in backbone}

    full_result = {
        "category": category,
        "backbone": backbone,
        "lenses": lenses,
        "reasoning": backbone_result.get("reasoning", ""),
        "from_standards": from_standards,
        "from_manufacturer_sites": from_manufacturers,
        "from_dataset": from_dataset,
        "error": backbone_result.get("error"),
    }

    # Build CSV rows: one row per backbone attribute with lens relevance columns
    sc_names = {e.get("name") for e in lenses.get("supply_chain", [])}
    ec_names = {e.get("name") for e in lenses.get("ecommerce", [])}

    rows = []
    for a in backbone:
        conf = a.get("confidence", {})
        deps = a.get("dependencies", [])
        deps_str = "; ".join(
            f"{d.get('attribute', '?')} ({d.get('type', '?')})" for d in deps
        ) if deps else ""
        unit = a.get("unit")
        unit_str = unit.get("base_unit", "") if isinstance(unit, dict) else ""
        sources = a.get("sources", [])
        sources_str = ", ".join(sources) if isinstance(sources, list) else str(sources)

        rows.append({
            "name": a.get("name", ""),
            "structural_role": a.get("structural_role", ""),
            "data_type": a.get("data_type", ""),
            "intrinsic": a.get("intrinsic", ""),
            "unit": unit_str,
            "dependencies": deps_str,
            "confidence_composite": conf.get("composite", ""),
            "confidence_necessity": conf.get("ontological_necessity", ""),
            "confidence_stability": conf.get("cross_manufacturer_stability", ""),
            "confidence_standards": conf.get("standards_coverage", ""),
            "supply_chain_relevant": a.get("name", "") in sc_names,
            "ecommerce_relevant": a.get("name", "") in ec_names,
            "rationale": a.get("rationale", ""),
            "sources": sources_str,
        })

    # Write outputs
    output_dir = os.path.abspath(output_dir)
    if output_json_path:
        out_json = os.path.join(output_dir, output_json_path) if not os.path.isabs(output_json_path) else output_json_path
        os.makedirs(os.path.dirname(out_json) or ".", exist_ok=True)
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(full_result, f, indent=2, ensure_ascii=False)
        _log_block(log_path, "OUTPUT – JSON", f"Written to: {out_json}")

    if output_csv_path:
        out_csv = os.path.join(output_dir, output_csv_path) if not os.path.isabs(output_csv_path) else output_csv_path
        os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
        if rows:
            pd.DataFrame(rows).to_csv(out_csv, index=False, encoding="utf-8")
        else:
            pd.DataFrame(columns=[
                "name", "structural_role", "data_type", "intrinsic", "unit",
                "dependencies", "confidence_composite", "confidence_necessity",
                "confidence_stability", "confidence_standards",
                "supply_chain_relevant", "ecommerce_relevant", "rationale", "sources",
            ]).to_csv(out_csv, index=False)
        _log_block(log_path, "OUTPUT – CSV", f"Written to: {out_csv} ({len(rows)} rows)")

    _log_block(
        log_path,
        "PIPELINE COMPLETE",
        f"Backbone: {len(backbone)} attributes\n"
        f"Supply chain lens: {len(lenses.get('supply_chain', []))} attributes\n"
        f"Ecommerce lens: {len(lenses.get('ecommerce', []))} attributes\n"
        f"Errors: {full_result.get('error') or 'None'}",
    )

    return full_result, rows, log_path


def main() -> None:
    """Entrypoint for standalone attribute resolution."""
    result, rows, run_log = standardize_attributes(
        category="contactors",
        dataset_path=None,
        output_dir=str(PROJECT_ROOT),
        output_json_path="recommended_attributes.json",
        output_csv_path="standardized_attributes.csv",
        max_search_results=5,
    )
    print("Saved recommended_attributes.json and standardized_attributes.csv")
    print(f"Log file: {run_log}")
    reasoning_preview = (result.get("reasoning") or "")[:500]
    if reasoning_preview:
        print(f"Reasoning (excerpt): {reasoning_preview}...")
    backbone = result.get("backbone", [])
    print(f"Backbone attributes: {len(backbone)}")
    for a in backbone[:3]:
        conf = a.get("confidence", {})
        print(f"  - {a['name']} [{a.get('structural_role')}] "
              f"composite={conf.get('composite', '?')}")
    lenses = result.get("lenses", {})
    print(f"Supply chain view: {len(lenses.get('supply_chain', []))} attributes")
    print(f"Ecommerce view: {len(lenses.get('ecommerce', []))} attributes")


if __name__ == "__main__":
    main()
