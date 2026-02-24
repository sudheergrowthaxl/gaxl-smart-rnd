"""
Attribute resolver for Contactors category (Electrical equipment domain).
Gathers attributes from: (1) Standards (UNSPSC, IEC, NEMA), (2) Manufacturer sites (Tavily),
(3) Contactors dataset; then uses Chain-of-Thought (CoT) with OpenAI to derive the recommended list.
"""

import json
import os
from typing import List, Dict, Any

import pandas as pd

from normalisation_rules.config import get_openai_client, PROJECT_ROOT
from normalisation_rules.prompts.attribute_resolver_prompt import (
    build_standards_extraction_prompt,
    build_manufacturer_extraction_prompt,
    build_cot_derivation_prompt,
)


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


def _tavily_search(query: str, max_results: int = 5) -> str:
    """Run Tavily search and return concatenated context text."""
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
    return "\n\n---\n\n".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# 1. Attributes from Contactors dataset
# ---------------------------------------------------------------------------

def get_attributes_from_dataset(dataset_path: str) -> Dict[str, Any]:
    """Load Contactors_Dataset.xlsx and extract column names as attributes."""
    if not os.path.isfile(dataset_path):
        return {
            "attributes": [],
            "columns": [],
            "raw_excerpt": "",
            "error": f"Dataset file not found: {dataset_path}",
        }
    try:
        df = pd.read_excel(dataset_path)
    except Exception as e:
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
    category: str, timeout: int = 15, max_results_per_query: int = 3
) -> Dict[str, Any]:
    """Use Tavily search for UNSPSC/IEC/NEMA attribute context, then AI extraction."""
    combined_text = []
    for q in STANDARD_SEARCH_QUERIES:
        try:
            text = _tavily_search(q, max_results=max_results_per_query)
            if text:
                combined_text.append(f"### Query: {q}\n\n{text}")
        except Exception as e:
            combined_text.append(f"### Query: {q}\nError: {e}")
    raw_excerpt = "\n\n---\n\n".join(combined_text)[:50000]

    if not raw_excerpt.strip():
        return {"attributes": [], "raw_excerpt": "", "error": "No content from standards search."}

    client = get_openai_client()
    prompt = build_standards_extraction_prompt(raw_excerpt)
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            return {"attributes": [], "raw_excerpt": raw_excerpt[:2000]}
        out = json.loads(content)
        out.setdefault("attributes", [])
        out["raw_excerpt"] = raw_excerpt[:2000]
        return out
    except (json.JSONDecodeError, TypeError) as e:
        return {"attributes": [], "raw_excerpt": raw_excerpt[:2000], "error": str(e)}


# ---------------------------------------------------------------------------
# 3. Attributes from manufacturer sites via Tavily
# ---------------------------------------------------------------------------

MANUFACTURER_SEARCH_QUERIES = [
    "contactors technical specifications datasheet attributes Schneider Siemens Eaton Rockwell",
    "contactor product attributes specifications site:se.com",
]


def get_attributes_from_manufacturer_sites(
    category: str, max_search_results: int = 5
) -> Dict[str, Any]:
    """Use Tavily search for manufacturer content, then AI extraction."""
    combined_text = []
    for q in MANUFACTURER_SEARCH_QUERIES:
        try:
            text = _tavily_search(q, max_results=max_search_results)
            if text:
                combined_text.append(f"### Query: {q}\n\n{text}")
        except Exception as e:
            combined_text.append(f"### Query: {q}\nError: {e}")
    raw_excerpt = "\n\n---\n\n".join(combined_text)[:50000]

    if not raw_excerpt.strip():
        return {"attributes": [], "raw_excerpt": "", "error": "No content from manufacturer search."}

    client = get_openai_client()
    prompt = build_manufacturer_extraction_prompt(raw_excerpt)
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            return {"attributes": [], "raw_excerpt": raw_excerpt[:2000]}
        out = json.loads(content)
        out.setdefault("attributes", [])
        out["raw_excerpt"] = raw_excerpt[:2000]
        return out
    except (json.JSONDecodeError, TypeError) as e:
        return {"attributes": [], "raw_excerpt": raw_excerpt[:2000], "error": str(e)}


# ---------------------------------------------------------------------------
# 4. Chain-of-Thought derivation
# ---------------------------------------------------------------------------

def derive_attributes_with_cot(
    attributes_from_standards: Dict[str, Any],
    attributes_from_manufacturers: Dict[str, Any],
    attributes_from_dataset: Dict[str, Any],
    category: str,
    model: str = "gpt-4o-mini",
) -> Dict[str, Any]:
    """Use Chain-of-Thought prompting to derive the recommended attribute list."""
    standards_attrs = attributes_from_standards.get("attributes", [])
    standards_preview = json.dumps(standards_attrs, indent=2) if standards_attrs else "None"
    manu_attrs = attributes_from_manufacturers.get("attributes", [])
    manu_preview = json.dumps(manu_attrs, indent=2) if manu_attrs else "None"
    dataset_attrs = attributes_from_dataset.get("attributes", [])
    dataset_preview = json.dumps(dataset_attrs, indent=2) if dataset_attrs else "None"
    dataset_excerpt = (attributes_from_dataset.get("raw_excerpt") or "")[:1500]

    prompt = build_cot_derivation_prompt(standards_preview, manu_preview, dataset_preview, dataset_excerpt)
    client = get_openai_client()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            return {
                "error": "Empty response",
                "reasoning": "",
                "supply_chain_attributes": [],
                "ecommerce_attributes": [],
                "recommended_attributes": [],
                "confidence": 0,
            }
        out = json.loads(content)
        out.setdefault("reasoning", "")
        out.setdefault("supply_chain_attributes", [])
        out.setdefault("ecommerce_attributes", [])
        if not out.get("supply_chain_attributes") and out.get("recommended_attributes"):
            out["supply_chain_attributes"] = out["recommended_attributes"]
        if not out.get("ecommerce_attributes") and out.get("recommended_attributes"):
            out["ecommerce_attributes"] = out["recommended_attributes"]
        out.setdefault(
            "recommended_attributes",
            out.get("supply_chain_attributes", []) + out.get("ecommerce_attributes", []),
        )
        out.setdefault("confidence", 0)
        return out
    except (json.JSONDecodeError, TypeError) as e:
        return {
            "error": f"JSON parse failed: {e}",
            "reasoning": "",
            "supply_chain_attributes": [],
            "ecommerce_attributes": [],
            "recommended_attributes": [],
            "confidence": 0,
        }


# ---------------------------------------------------------------------------
# 5. Main workflow
# ---------------------------------------------------------------------------

def standardize_attributes(
    category: str = "contactors",
    dataset_path: str | None = None,
    output_json_path: str | None = None,
    output_csv_path: str | None = None,
    max_search_results: int = 5,
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Run the full workflow: gather from standards, manufacturer sites, dataset;
    then derive attributes with CoT.
    Returns (full_result_dict, list of attribute rows for CSV).
    """
    default_dataset = str(PROJECT_ROOT / "Contactors_Dataset.xlsx")
    dataset_path = dataset_path or default_dataset

    print(f"  [Standards] Searching UNSPSC, IEC, NEMA via Tavily...")
    from_standards = get_attributes_from_standards(category, max_results_per_query=max_search_results)

    print(f"  [Manufacturers] Searching manufacturer sites via Tavily...")
    from_manufacturers = get_attributes_from_manufacturer_sites(category, max_search_results=max_search_results)

    print(f"  [Dataset] Loading from: {dataset_path}")
    from_dataset = get_attributes_from_dataset(dataset_path)

    print(f"  [CoT] Deriving attributes with Chain-of-Thought reasoning...")
    derived = derive_attributes_with_cot(from_standards, from_manufacturers, from_dataset, category)

    supply_chain_attrs = derived.get("supply_chain_attributes", [])
    ecommerce_attrs = derived.get("ecommerce_attributes", [])

    full_result = {
        "category": category,
        "from_standards": from_standards,
        "from_manufacturer_sites": from_manufacturers,
        "from_dataset": from_dataset,
        "reasoning": derived.get("reasoning", ""),
        "supply_chain_attributes": supply_chain_attrs,
        "ecommerce_attributes": ecommerce_attrs,
        "recommended_attributes": derived.get("recommended_attributes", []),
        "confidence": derived.get("confidence", 0),
        "error": derived.get("error"),
    }

    rows = []
    for a in supply_chain_attrs:
        rows.append({
            "lens": "supply_chain",
            "attribute_name": a.get("name", ""),
            "description": a.get("description", ""),
            "rationale": a.get("rationale", ""),
            "confidence": derived.get("confidence", 0),
            "sources": a.get("sources", ""),
        })
    for a in ecommerce_attrs:
        rows.append({
            "lens": "ecommerce",
            "attribute_name": a.get("name", ""),
            "description": a.get("description", ""),
            "rationale": a.get("rationale", ""),
            "confidence": derived.get("confidence", 0),
            "sources": a.get("sources", ""),
        })

    if output_json_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_json_path)), exist_ok=True)
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(full_result, f, indent=2, ensure_ascii=False)

    if output_csv_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_csv_path)), exist_ok=True)
        if rows:
            pd.DataFrame(rows).to_csv(output_csv_path, index=False, encoding="utf-8")
        else:
            pd.DataFrame(
                columns=["lens", "attribute_name", "description", "rationale", "confidence", "sources"]
            ).to_csv(output_csv_path, index=False)

    return full_result, rows
