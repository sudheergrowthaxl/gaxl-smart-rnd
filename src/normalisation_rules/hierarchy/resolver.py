"""Hierarchy resolver: dynamic UNSPSC + manufacturer site discovery + AI path recommendation.

All manufacturer URLs and UNSPSC paths are discovered at runtime via Tavily and LLM
reasoning — no hardcoded URLs or segment codes.
"""

import json
import os
import requests
from bs4 import BeautifulSoup
from typing import List, Dict
from urllib.parse import urlparse, unquote

import pandas as pd

from normalisation_rules.config import (
    get_openai_client,
    load_domain_backbone,
    get_manufacturers_for_category,
)
from normalisation_rules.prompts.hierarchy_prompt import (
    build_extract_hierarchy_prompt,
    build_recommend_paths_prompt,
)

HEADERS_HTTP = {"User-Agent": "Mozilla/5.0 (compatible; hierarchy-resolver/1.0)"}


# ---------------------------------------------------------------------------
# Dynamic manufacturer URL discovery via Tavily
# ---------------------------------------------------------------------------

def discover_manufacturer_urls(
    category: str,
    max_manufacturers: int = 5,
) -> List[Dict]:
    """Discover manufacturer product page URLs for a category via Tavily.

    Returns list of dicts: [{name, url, known_path (optional)}].
    """
    manufacturers = get_manufacturers_for_category(category)[:max_manufacturers]
    results = []

    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        return [{"name": m, "url": "", "known_path": None} for m in manufacturers]

    from tavily import TavilyClient
    client = TavilyClient(api_key=tavily_key)

    for mfr in manufacturers:
        query = f"{mfr} {category} product catalog page official site"
        try:
            response = client.search(
                query=query,
                max_results=3,
                search_depth="basic",
            )
            best_url = ""
            for r in response.get("results", []):
                url = r.get("url", "")
                url_lower = url.lower()
                mfr_lower = mfr.lower().replace(" ", "")
                if any(frag in url_lower for frag in [mfr_lower, mfr_lower.split()[0]]):
                    best_url = url
                    break
            if not best_url and response.get("results"):
                best_url = response["results"][0].get("url", "")
            results.append({"name": mfr, "url": best_url, "known_path": None})
        except Exception:
            results.append({"name": mfr, "url": "", "known_path": None})

    return results


# ---------------------------------------------------------------------------
# Dynamic UNSPSC discovery via Tavily
# ---------------------------------------------------------------------------

def discover_unspsc_context(category: str) -> str:
    """Discover UNSPSC classification context for a category via Tavily.

    Returns text containing UNSPSC segment/family/class information.
    """
    # Check backbone for UNSPSC hint
    bb = load_domain_backbone(category)
    standards = bb.get("domain", {}).get("standards_basis", [])
    unspsc_hint = ""
    for s in standards:
        if isinstance(s, str) and "unspsc" in s.lower():
            unspsc_hint = s

    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        return f"UNSPSC classification for {category}: {unspsc_hint or 'unknown'}"

    from tavily import TavilyClient
    client = TavilyClient(api_key=tavily_key)

    query = f"UNSPSC code for {category} electrical equipment classification"
    if unspsc_hint:
        query += f" {unspsc_hint}"

    try:
        response = client.search(
            query=query,
            max_results=5,
            search_depth="advanced",
            include_answer=True,
        )
        parts = []
        if response.get("answer"):
            parts.append(response["answer"])
        for r in response.get("results", [])[:5]:
            content = (r.get("content") or "").strip()
            if content:
                parts.append(content[:2000])
        return "\n\n".join(parts) if parts else f"UNSPSC for {category}: {unspsc_hint or 'not found'}"
    except Exception as e:
        return f"UNSPSC discovery failed: {e}. Hint: {unspsc_hint or 'none'}"


# ---------------------------------------------------------------------------
# AI extraction functions
# ---------------------------------------------------------------------------

def extract_hierarchy_with_ai(
    raw_text: str,
    category: str,
    customer_hierarchy_paths: List[str] | None = None,
    model: str = "gpt-4o-mini",
) -> Dict:
    prompt = build_extract_hierarchy_prompt(raw_text, category, customer_hierarchy_paths)
    client = get_openai_client()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    try:
        content = response.choices[0].message.content
        if not content:
            return {"error": "Empty response", "confidence": 0}
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return {"error": "JSON parse failed", "confidence": 0}


def recommend_paths_from_crawled_and_customer(
    category: str,
    customer_hierarchy_paths: List[str] | None,
    unspsc_excerpt: str,
    unspsc_hierarchy_path: str | None,
    manufacturer_crawled_paths: List[Dict],
    model: str = "gpt-4o-mini",
) -> Dict:
    prompt = build_recommend_paths_prompt(
        category,
        customer_hierarchy_paths,
        unspsc_excerpt,
        unspsc_hierarchy_path,
        manufacturer_crawled_paths,
    )
    client = get_openai_client()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    try:
        content = response.choices[0].message.content
        if not content:
            return _empty_recommendation()
        out = json.loads(content)
        for key in ("supply_chain_recommended_path", "ecommerce_recommended_path",
                     "global_generalized_hierarchy_path", "supply_chain_reason",
                     "ecommerce_reason"):
            out.setdefault(key, "")
        out.setdefault("confidence", 0)
        return out
    except (json.JSONDecodeError, TypeError):
        return _empty_recommendation()


def _empty_recommendation() -> Dict:
    return {
        "error": "Parse failed",
        "supply_chain_recommended_path": "",
        "ecommerce_recommended_path": "",
        "global_generalized_hierarchy_path": "",
        "supply_chain_reason": "",
        "ecommerce_reason": "",
        "confidence": 0,
    }


# ---------------------------------------------------------------------------
# Breadcrumb/nav extraction from crawled pages
# ---------------------------------------------------------------------------

def _hierarchy_from_url_path(url: str) -> str:
    parsed = urlparse(url)
    path = (parsed.path or "").strip("/")
    if not path:
        return ""
    segments = []
    for part in path.replace(".html", "").replace(".htm", "").split("/"):
        part = unquote(part)
        if not part or part.lower() in ("en", "us", "en-us", "www", "in", "global"):
            continue
        readable = part.replace("-", " ").replace("_", " ").title()
        if len(readable) > 2 and readable not in segments:
            segments.append(readable)
    return " > ".join(segments) if segments else ""


def _extract_breadcrumb_and_nav(soup: BeautifulSoup, page_url: str = "") -> str:
    parts = []

    for elem in soup.find_all(attrs={"itemtype": lambda v: v and "BreadcrumbList" in str(v)}):
        items = elem.find_all(attrs={"itemprop": "name"})
        if items:
            path = " > ".join([i.get_text(strip=True) for i in items if i.get_text(strip=True)])
            if 5 < len(path) < 300:
                parts.append(path)

    for elem in soup.find_all(["nav", "ol", "ul"]):
        aria = (elem.get("aria-label") or "").lower()
        cls = (elem.get("class") or [])
        cls_str = " ".join(cls).lower() if isinstance(cls, list) else str(cls).lower()
        if "breadcrumb" in aria or "breadcrumb" in cls_str:
            text = elem.get_text(separator=" > ", strip=True)
            if 8 < len(text) < 400:
                parts.append(text)

    for ol in soup.find_all("ol"):
        links = ol.find_all("a", href=True)
        if 2 <= len(links) <= 8:
            path = " > ".join([a.get_text(strip=True) for a in links if a.get_text(strip=True)])
            if 10 < len(path) < 350:
                parts.append(path)

    if page_url:
        url_path = _hierarchy_from_url_path(page_url)
        if url_path and url_path not in parts:
            parts.append(url_path)

    for tag in soup.find_all(["h1", "h2"], limit=5):
        t = tag.get_text(strip=True)
        if t and 2 < len(t) < 200:
            parts.append(t)

    seen = set()
    unique = []
    for p in parts:
        pnorm = " > ".join(x.strip() for x in p.split(">") if x.strip())
        if pnorm and pnorm not in seen and len(pnorm) > 3:
            seen.add(pnorm)
            unique.append(pnorm)
    return " | ".join(unique[:10]) if unique else ""


def _first_path_from_snippet(snippet: str) -> str:
    if not snippet or not snippet.strip():
        return ""
    first = snippet.split("|")[0].strip()
    return " > ".join(x.strip() for x in first.split(">") if x.strip()) if first else ""


def scrape_manufacturer_site_for_hierarchy(
    manufacturer_name: str,
    url: str,
    category: str,
    timeout: int = 30,
    known_path: str | None = None,
) -> Dict:
    """Crawl a manufacturer page and extract hierarchy path."""
    if not url:
        return {
            "source_name": manufacturer_name,
            "url": "",
            "excerpt_from_site": "No URL discovered",
            "extracted_hierarchy": {"crawled_path": known_path or ""},
        }

    last_error = None
    for attempt in range(2):
        try:
            resp = requests.get(url, timeout=timeout, headers=HEADERS_HTTP)
            if resp.status_code != 200:
                return {
                    "source_name": manufacturer_name,
                    "url": url,
                    "excerpt_from_site": f"HTTP {resp.status_code}",
                    "extracted_hierarchy": {"crawled_path": known_path or "", "error": f"HTTP {resp.status_code}"},
                }
            html = resp.text
            if "cloudflare" in html.lower() and "blocked" in html.lower():
                return {
                    "source_name": manufacturer_name,
                    "url": url,
                    "excerpt_from_site": "Blocked (Cloudflare)",
                    "extracted_hierarchy": {"crawled_path": known_path or "", "error": "Blocked"},
                }
            soup = BeautifulSoup(html, "html.parser")
            hierarchy_snippet = _extract_breadcrumb_and_nav(soup, page_url=url)
            crawled = _first_path_from_snippet(hierarchy_snippet) if hierarchy_snippet else ""
            if not crawled and known_path:
                crawled = known_path
            excerpt = (
                hierarchy_snippet[:500] + ("..." if len(hierarchy_snippet) > 500 else "")
                if hierarchy_snippet
                else ""
            )
            return {
                "source_name": manufacturer_name,
                "url": url,
                "excerpt_from_site": excerpt,
                "extracted_hierarchy": {"crawled_path": crawled},
            }
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout) as e:
            last_error = e
            if attempt == 0:
                continue
        except requests.RequestException as e:
            last_error = e
            break

    return {
        "source_name": manufacturer_name,
        "url": url,
        "excerpt_from_site": f"Request failed: {last_error}",
        "extracted_hierarchy": {"crawled_path": known_path or "", "error": str(last_error)},
    }


def get_hierarchy_from_manufacturer_websites(category: str, timeout: int = 30) -> List[Dict]:
    """Discover and crawl manufacturer sites for any category."""
    discovered = discover_manufacturer_urls(category)
    contributions = []
    for m in discovered:
        name = m.get("name", "Unknown")
        url = m.get("url", "")
        known_path = m.get("known_path")
        print(f"  [Manufacturer] {name} — {url or '(no URL found)'}")
        contributions.append(
            scrape_manufacturer_site_for_hierarchy(name, url, category, timeout, known_path=known_path)
        )
    return contributions


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------

def standardize_hierarchy(
    df: pd.DataFrame,
    hierarchy_col: str,
    sources: List[Dict] | None = None,
    excerpt_max_len: int = 500,
    customer_hierarchy_col: str | None = None,
    crawled_paths_output_path: str | None = None,
) -> tuple[pd.DataFrame, List[Dict]]:
    """Main workflow: UNSPSC discovery + manufacturer crawling -> AI recommendation.

    Works with ANY product category — URLs and UNSPSC paths discovered dynamically.
    """
    sources = sources or []
    customer_paths: List[str] | None = None
    if customer_hierarchy_col and customer_hierarchy_col in df.columns:
        customer_paths = (
            df[customer_hierarchy_col].dropna().astype(str).str.strip()
            .replace("", None).dropna().unique().tolist()
        )
        customer_paths = [p for p in customer_paths if p and len(p) > 1][:100]

    results = []
    json_records = []

    for idx, row in df.iterrows():
        category = row[hierarchy_col]

        # 1) UNSPSC context via Tavily discovery
        print(f"  [UNSPSC] Discovering classification for '{category}'...")
        unspsc_text = discover_unspsc_context(category)
        unspsc_ai = extract_hierarchy_with_ai(unspsc_text, category, customer_hierarchy_paths=customer_paths)

        # 2) Manufacturer sites: discover URLs dynamically, then crawl
        manufacturer_contributions = get_hierarchy_from_manufacturer_websites(category)
        manufacturer_contributions_for_json = [
            {
                "source_name": c["source_name"],
                "url": c["url"],
                "excerpt_from_site": c["excerpt_from_site"],
                "extracted_hierarchy": c["extracted_hierarchy"],
            }
            for c in manufacturer_contributions
        ]
        manufacturer_crawled_paths = [
            {
                "source_name": c["source_name"],
                "crawled_path": (c.get("extracted_hierarchy") or {}).get("crawled_path", ""),
            }
            for c in manufacturer_contributions
        ]

        for source in sources:
            if source.get("type") == "pdf":
                continue
            name = source.get("name", "Unknown")
            url = source.get("url", "")
            try:
                resp = requests.get(url, timeout=15, headers=HEADERS_HTTP)
                text = resp.text
                if "cloudflare" in text.lower() and "blocked" in text.lower():
                    text = "Source blocked (Cloudflare)."
                else:
                    soup = BeautifulSoup(text, "html.parser")
                    text = soup.get_text(separator=" ", strip=True)[:8000]
            except requests.RequestException as e:
                text = f"HTML fetch failed: {e}"
            ai_from_source = extract_hierarchy_with_ai(text, category, customer_hierarchy_paths=customer_paths)
            path_from_source = ai_from_source.get("hierarchy_path", "")
            manufacturer_contributions_for_json.append({
                "source_name": name,
                "url": url,
                "excerpt_from_site": text[:excerpt_max_len] + ("..." if len(text) > excerpt_max_len else ""),
                "extracted_hierarchy": {"crawled_path": path_from_source},
            })
            if path_from_source:
                manufacturer_crawled_paths.append({"source_name": name, "crawled_path": path_from_source})

        # 3) AI recommendation: supply chain + ecommerce paths
        unspsc_path = (unspsc_ai or {}).get("hierarchy_path", "") or ""
        recommendation = recommend_paths_from_crawled_and_customer(
            category=category,
            customer_hierarchy_paths=customer_paths,
            unspsc_excerpt=unspsc_text,
            unspsc_hierarchy_path=unspsc_path or None,
            manufacturer_crawled_paths=manufacturer_crawled_paths,
        )

        results.append(recommendation)

        json_records.append({
            "category": category,
            "recommended_path": recommendation.get("supply_chain_recommended_path", ""),
            "ecommerce_recommended_path": recommendation.get("ecommerce_recommended_path", ""),
            "global_generalized_hierarchy_path": recommendation.get("global_generalized_hierarchy_path", ""),
            "supply_chain_reason": recommendation.get("supply_chain_reason", ""),
            "ecommerce_reason": recommendation.get("ecommerce_reason", ""),
            "unspsc_code": recommendation.get("unspsc_code", ""),
            "standard": recommendation.get("standard", "UNSPSC/Manufacturer"),
            "confidence": recommendation.get("confidence", 0),
            "from_unspsc": {
                "excerpt_preview": unspsc_text[:excerpt_max_len] + ("..." if len(unspsc_text) > excerpt_max_len else ""),
                "extracted_hierarchy": unspsc_ai,
            },
            "from_manufacturer_websites": manufacturer_contributions_for_json,
        })

    df = df.copy()
    df["ai_standard_hierarchy"] = [json.dumps(r) for r in results]
    df["recommended_path"] = [r.get("supply_chain_recommended_path", "") for r in results]
    df["ecommerce_recommended_path"] = [r.get("ecommerce_recommended_path", "") for r in results]
    df["global_generalized_hierarchy_path"] = [r.get("global_generalized_hierarchy_path", "") for r in results]
    df["supply_chain_reason"] = [r.get("supply_chain_reason", "") for r in results]
    df["ecommerce_reason"] = [r.get("ecommerce_reason", "") for r in results]

    if crawled_paths_output_path:
        crawled_paths_list = []
        for rec in json_records:
            for site in rec.get("from_manufacturer_websites", []):
                eh = site.get("extracted_hierarchy") or {}
                crawled_paths_list.append({
                    "category": rec.get("category", ""),
                    "source_name": site.get("source_name", ""),
                    "url": site.get("url", ""),
                    "crawled_path": eh.get("crawled_path", ""),
                })
        with open(crawled_paths_output_path, "w", encoding="utf-8") as f:
            json.dump(crawled_paths_list, f, indent=2, ensure_ascii=False)

    return df, json_records
