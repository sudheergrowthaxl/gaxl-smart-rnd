"""Attribute resolver for any product category (Electrical equipment domain).

Gathers attributes from: (1) Standards via Tavily, (2) Manufacturer sites via Tavily,
(3) User-uploaded dataset; then builds a canonical backbone schema with structural
classification and projects supply chain, ecommerce, and analytical views.

All search queries are generated dynamically by the LLM at runtime — no hardcoded
query lists. Category is passed through every function call.
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
    get_domain_model_context,
    get_manufacturers_for_category,
)
from normalisation_rules.prompts.attribute_resolver_prompt import (
    build_standards_extraction_prompt,
    build_manufacturer_extraction_prompt,
    build_backbone_modeling_prompt,
    build_lens_projection_prompt,
)
from normalisation_rules.prompts.search_query_generation_prompt import (
    build_search_query_generation_prompt,
)


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def _log_block(log_path: Path | None, label: str, body: str) -> None:
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
# LLM-generated search queries (replaces hardcoded query lists)
# ---------------------------------------------------------------------------

def _generate_search_queries(
    category: str,
    query_type: str,
    model: str = "gpt-4o-mini",
    log_path: Path | None = None,
) -> list[str]:
    """Use the LLM to generate optimal search queries for a category."""
    prompt = build_search_query_generation_prompt(category, query_type)
    _log_block(log_path, f"QUERY GENERATION ({query_type.upper()})", f"Category: {category}")
    client = get_openai_client()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or ""
        result = json.loads(content)
        queries = result.get("queries", [])
        _log_block(log_path, f"QUERY GENERATION ({query_type.upper()}) — RESULT",
                   f"Generated {len(queries)} queries:\n" + "\n".join(f"  - {q}" for q in queries))
        return queries if queries else _fallback_queries(category, query_type)
    except Exception as e:
        _log_block(log_path, f"QUERY GENERATION ({query_type.upper()}) — ERROR", str(e))
        return _fallback_queries(category, query_type)


def _fallback_queries(category: str, query_type: str) -> list[str]:
    """Minimal fallback queries when LLM query generation fails."""
    cat = category.lower()
    if query_type == "standards":
        return [
            f"UNSPSC {cat} attributes properties classification",
            f"IEC standards {cat} specifications attributes",
            f"NEMA {cat} ratings specifications",
        ]
    return [
        f"{cat} technical specifications datasheet attributes",
        f"{cat} product catalog specifications manufacturers",
    ]


# ---------------------------------------------------------------------------
# 1. Attributes from user dataset (or from persisted profiling JSON)
# ---------------------------------------------------------------------------

def get_attributes_from_profiling(
    profiling: Dict[str, Any],
    category: str,
    log_path: Path | None = None,
) -> Dict[str, Any]:
    """Extract attribute evidence from an already-profiled dataset.

    Accepts the profiling dict (column name -> stats) that was persisted
    to the data/ folder by ``data_loader.profile_and_save()``.
    """
    _log_block(log_path, "PROFILING LOAD – START",
               f"Category: {category} | Columns: {len(profiling)}")

    columns = list(profiling.keys())
    attributes = []
    sample_parts = []
    for col, stats in profiling.items():
        vals = stats.get("distinct_values") or []
        sample = vals[0]["value"] if vals else ""
        attributes.append({"name": col, "source": "user_dataset_profiling", "sample": sample})
        if sample:
            sample_parts.append(f"{col}: {sample}")

    _log_block(
        log_path,
        "PROFILING LOAD – DONE",
        f"Columns ({len(columns)}): {columns}\n\nSample excerpt:\n" + "\n".join(sample_parts[:30]),
    )
    return {
        "attributes": attributes,
        "columns": columns,
        "raw_excerpt": "\n".join(sample_parts[:50]) if sample_parts else "",
    }


def get_attributes_from_dataset(
    dataset_path: str,
    category: str,
    log_path: Path | None = None,
) -> Dict[str, Any]:
    """Load the user's dataset from disk and extract column names as attributes.

    Prefer ``get_attributes_from_profiling()`` when a profiling JSON is
    already available in the data/ folder.
    """
    _log_block(log_path, "DATASET LOAD – START", f"Path: {dataset_path}\nCategory: {category}")
    if not os.path.isfile(dataset_path):
        err = f"Dataset file not found: {dataset_path}"
        _log_block(log_path, "DATASET LOAD – ERROR", err)
        return {"attributes": [], "columns": [], "raw_excerpt": "", "error": err}
    try:
        ext = os.path.splitext(dataset_path)[1].lower()
        if ext == ".csv":
            df = pd.read_csv(dataset_path)
        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(dataset_path)
        elif ext == ".json":
            df = pd.read_json(dataset_path)
        else:
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
        attributes.append({"name": col, "source": "user_dataset", "sample": sample or ""})
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
# 2. Attributes from standards via Tavily (LLM-generated queries)
# ---------------------------------------------------------------------------

def get_attributes_from_standards(
    category: str,
    timeout: int = 15,
    max_results_per_query: int = 3,
    log_path: Path | None = None,
) -> Dict[str, Any]:
    _log_block(log_path, "STANDARDS SEARCH – START", f"Category: {category}")

    queries = _generate_search_queries(category, "standards", log_path=log_path)

    combined_text = []
    for q in queries:
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
    prompt = build_standards_extraction_prompt(raw_excerpt, category)
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
# 3. Attributes from manufacturer sites via Tavily (LLM-generated queries)
# ---------------------------------------------------------------------------

def get_attributes_from_manufacturer_sites(
    category: str,
    max_search_results: int = 5,
    log_path: Path | None = None,
) -> Dict[str, Any]:
    _log_block(log_path, "MANUFACTURER SEARCH – START", f"Category: {category}")

    queries = _generate_search_queries(category, "manufacturer", log_path=log_path)

    combined_text = []
    for q in queries:
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
    prompt = build_manufacturer_extraction_prompt(raw_excerpt, category)
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
    model: str = "gpt-4o",
    log_path: Path | None = None,
    domain_model: dict | None = None,
) -> Dict[str, Any]:
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

    dm_context = ""
    if domain_model:
        dm_context = get_domain_model_context(domain_model)

    prompt = build_backbone_modeling_prompt(
        standards_preview, manu_preview, dataset_preview, dataset_excerpt,
        category=category, domain_model_context=dm_context,
    )
    _log_block(log_path, "BACKBONE MODELING – PROMPT", prompt[:8000] + ("...(truncated)" if len(prompt) > 8000 else ""))
    client = get_openai_client()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=16000,
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
# 5. Lens projection: derive supply chain, ecommerce, and analytical views
# ---------------------------------------------------------------------------

def project_lenses(
    backbone: list[dict],
    category: str,
    model: str = "gpt-4o",
    log_path: Path | None = None,
) -> Dict[str, Any]:
    _log_block(log_path, "LENS PROJECTION – START", f"Category: {category} | Backbone size: {len(backbone)} | Model: {model}")
    if not backbone:
        _log_block(log_path, "LENS PROJECTION – SKIP", "Empty backbone; nothing to project.")
        return {"supply_chain": [], "ecommerce": [], "analytical": []}

    backbone_json = json.dumps(backbone, indent=2)
    prompt = build_lens_projection_prompt(backbone_json, category=category)
    _log_block(log_path, "LENS PROJECTION – PROMPT", prompt[:8000] + ("...(truncated)" if len(prompt) > 8000 else ""))
    client = get_openai_client()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=8000,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        _log_block(log_path, "LENS PROJECTION – RAW RESPONSE", content or "(empty)")
        if not content:
            _log_block(log_path, "LENS PROJECTION – ERROR", "Empty response from LLM")
            return {"supply_chain": [], "ecommerce": [], "analytical": []}
        out = json.loads(content)
        out.setdefault("supply_chain", [])
        out.setdefault("ecommerce", [])
        out.setdefault("analytical", [])
        _log_block(
            log_path,
            "LENS PROJECTION – DONE",
            f"Supply chain: {len(out['supply_chain'])} | "
            f"Ecommerce: {len(out['ecommerce'])} | "
            f"Analytical: {len(out.get('analytical', []))}",
        )
        return out
    except (json.JSONDecodeError, TypeError) as e:
        _log_block(log_path, "LENS PROJECTION – ERROR", f"JSON parse failed: {e}")
        return {"supply_chain": [], "ecommerce": [], "analytical": []}


# ---------------------------------------------------------------------------
# 6. Main workflow and outputs
# ---------------------------------------------------------------------------

def standardize_attributes(
    category: str,
    dataset_path: str | None = None,
    profiling_data: Dict[str, Any] | None = None,
    output_dir: str = ".",
    output_json_path: str | None = None,
    output_csv_path: str | None = None,
    max_search_results: int = 5,
    domain_model: dict | None = None,
) -> tuple[Dict[str, Any], List[Dict[str, Any]], Path]:
    """Run the full workflow: gather evidence -> backbone modeling -> lens projection.

    If *profiling_data* is provided (the dict from ``data_loader.profile_and_save``),
    it is used directly instead of re-loading the raw dataset from *dataset_path*.

    If *domain_model* is provided (the runtime LLM-generated 7-section model),
    it is used as additional context for backbone modeling.
    """
    log_path = get_attribute_resolver_log_path_for_run()
    _log_block(log_path, "PIPELINE START", f"Category: {category}\nLog file: {log_path}")

    if domain_model:
        dm_ctx = get_domain_model_context(domain_model)
        _log_block(log_path, "DOMAIN MODEL CONTEXT", f"Using runtime domain model\n{dm_ctx[:2000]}")
        print(f"  [Domain Model] Using runtime domain model as context for '{category}'")
    else:
        _log_block(log_path, "DOMAIN MODEL", f"No domain model for '{category}' — reasoning from first principles.")
        print(f"  [Domain Model] No domain model for '{category}' — reasoning from first principles")

    output_json_path = output_json_path or "recommended_attributes.json"
    output_csv_path = output_csv_path or "standardized_attributes.csv"

    _log_block(
        log_path,
        "RESOLVED PARAMETERS",
        f"dataset_path: {dataset_path}\n"
        f"profiling_data: {'provided (' + str(len(profiling_data)) + ' columns)' if profiling_data else 'None'}\n"
        f"output_json_path: {output_json_path}\n"
        f"output_csv_path: {output_csv_path}\n"
        f"max_search_results: {max_search_results}",
    )

    print(f"  [Log] {log_path}")
    print(f"  [Standards] Searching standards via Tavily for '{category}'...")
    from_standards = get_attributes_from_standards(
        category, max_results_per_query=max_search_results, log_path=log_path,
    )

    print(f"  [Manufacturers] Searching manufacturer sites via Tavily for '{category}'...")
    from_manufacturers = get_attributes_from_manufacturer_sites(
        category, max_search_results=max_search_results, log_path=log_path,
    )

    from_dataset: Dict[str, Any] = {"attributes": [], "columns": [], "raw_excerpt": ""}
    if profiling_data:
        print(f"  [Dataset] Loading from profiling data ({len(profiling_data)} columns)")
        from_dataset = get_attributes_from_profiling(profiling_data, category, log_path=log_path)
    elif dataset_path:
        print(f"  [Dataset] Loading from: {dataset_path}")
        from_dataset = get_attributes_from_dataset(dataset_path, category, log_path=log_path)

    print("  [Backbone] Building canonical schema with structural classification...")
    backbone_result = model_backbone_schema(
        from_standards, from_manufacturers, from_dataset, category,
        log_path=log_path, domain_model=domain_model,
    )
    backbone = backbone_result.get("backbone", [])
    print(f"  [Backbone] {len(backbone)} attributes modeled")

    print("  [Lenses] Projecting supply chain, ecommerce, and analytical views...")
    lenses = project_lenses(backbone, category, log_path=log_path)
    print(f"  [Lenses] Supply chain: {len(lenses.get('supply_chain', []))} | "
          f"Ecommerce: {len(lenses.get('ecommerce', []))} | "
          f"Analytical: {len(lenses.get('analytical', []))}")

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

    sc_names = {e.get("name") for e in lenses.get("supply_chain", [])}
    ec_names = {e.get("name") for e in lenses.get("ecommerce", [])}
    an_names = {e.get("name") for e in lenses.get("analytical", [])}

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
            "analytical_relevant": a.get("name", "") in an_names,
            "rationale": a.get("rationale", ""),
            "sources": sources_str,
        })

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
                "supply_chain_relevant", "ecommerce_relevant", "analytical_relevant",
                "rationale", "sources",
            ]).to_csv(out_csv, index=False)
        _log_block(log_path, "OUTPUT – CSV", f"Written to: {out_csv} ({len(rows)} rows)")

    _log_block(
        log_path,
        "PIPELINE COMPLETE",
        f"Backbone: {len(backbone)} attributes\n"
        f"Supply chain lens: {len(lenses.get('supply_chain', []))} attributes\n"
        f"Ecommerce lens: {len(lenses.get('ecommerce', []))} attributes\n"
        f"Analytical lens: {len(lenses.get('analytical', []))} attributes\n"
        f"Errors: {full_result.get('error') or 'None'}",
    )

    return full_result, rows, log_path


def main() -> None:
    """Entrypoint for standalone attribute resolution (defaults to user prompt)."""
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m normalisation_rules.attribute_resolver.resolver <category>")
        sys.exit(1)
    category = sys.argv[1]
    result, rows, run_log = standardize_attributes(
        category=category,
        dataset_path=None,
        output_dir=str(PROJECT_ROOT),
        output_json_path="recommended_attributes.json",
        output_csv_path="standardized_attributes.csv",
        max_search_results=5,
    )
    print(f"Saved recommended_attributes.json and standardized_attributes.csv")
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
    print(f"Analytical view: {len(lenses.get('analytical', []))} attributes")


if __name__ == "__main__":
    main()
