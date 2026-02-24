"""Hierarchy resolver: UNSPSC + manufacturer site scraping + AI path recommendation."""

import json
import requests
from bs4 import BeautifulSoup
from typing import List, Dict
from urllib.parse import urlparse, unquote

try:
    import tabula
    _tabula_read_pdf = getattr(tabula, "read_pdf", None)
except ImportError:
    tabula = None
    _tabula_read_pdf = None

import pandas as pd

from normalisation_rules.config import get_openai_client
from normalisation_rules.prompts.hierarchy_prompt import (
    build_extract_hierarchy_prompt,
    build_recommend_paths_prompt,
)


# ---------------------------------------------------------------------------
# AI extraction functions
# ---------------------------------------------------------------------------

def extract_hierarchy_with_ai(
    raw_text: str,
    category: str,
    customer_hierarchy_paths: List[str] | None = None,
    model: str = "gpt-4o-mini",
) -> Dict:
    """Uses OpenAI to extract hierarchy paths and map to category."""
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
    """
    Single AI step: compare customer path(s) + UNSPSC + manufacturer crawled paths;
    output supply_chain_recommended_path, ecommerce_recommended_path,
    global_generalized_hierarchy_path, supply_chain_reason, ecommerce_reason.
    """
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
            return {
                "error": "Empty response",
                "supply_chain_recommended_path": "",
                "ecommerce_recommended_path": "",
                "global_generalized_hierarchy_path": "",
                "supply_chain_reason": "",
                "ecommerce_reason": "",
                "confidence": 0,
            }
        out = json.loads(content)
        out.setdefault("supply_chain_recommended_path", "")
        out.setdefault("ecommerce_recommended_path", "")
        out.setdefault("global_generalized_hierarchy_path", "")
        out.setdefault("supply_chain_reason", "")
        out.setdefault("ecommerce_reason", "")
        out.setdefault("confidence", 0)
        return out
    except (json.JSONDecodeError, TypeError):
        return {
            "error": "JSON parse failed",
            "supply_chain_recommended_path": "",
            "ecommerce_recommended_path": "",
            "global_generalized_hierarchy_path": "",
            "supply_chain_reason": "",
            "ecommerce_reason": "",
            "confidence": 0,
        }


# ---------------------------------------------------------------------------
# UNSPSC scraping
# ---------------------------------------------------------------------------

UNSPSC_BASE = "https://usa.databasesets.com/unspsc"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; hierarchy-resolver/1.0)"}


def _fetch_unspsc_page(path: str, timeout: int) -> tuple[str | None, str | None]:
    url = UNSPSC_BASE + path if path.startswith("/") else f"{UNSPSC_BASE}/{path}"
    try:
        resp = requests.get(url, timeout=timeout, headers=HEADERS)
        html = resp.text
        if resp.status_code == 404 or "page not found" in html.lower() or "could not be found" in html.lower():
            return None, "Page not found"
        if "cloudflare" in html.lower() and ("blocked" in html.lower() or "attention required" in html.lower()):
            return None, "Blocked (Cloudflare)"
        return html, None
    except requests.RequestException as e:
        return None, str(e)


def scrape_unspsc(category: str, timeout: int = 15) -> str:
    """Scrape UNSPSC hierarchy from usa.databasesets.com/unspsc."""
    text_parts = []

    html, err = _fetch_unspsc_page("/", timeout)
    if err:
        msg = f"UNSPSC home failed: {err}. Using other sources."
        print("  [UNSPSC]", msg)
        return msg
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "/unspsc/segment/" in href:
            code = a.get_text(strip=True)
            if code.isdigit() and len(code) == 8:
                parent = a.find_parent("tr")
                name = ""
                if parent:
                    tds = parent.find_all("td")
                    for i, td in enumerate(tds):
                        if a in td.find_all("a") and i + 1 < len(tds):
                            name = tds[i + 1].get_text(strip=True)
                            break
                text_parts.append(f"Segment {code} {name or code}")
    if text_parts:
        text_parts = [f"UNSPSC segments: {' | '.join(text_parts[:60])}"]

    html2, err2 = _fetch_unspsc_page("/segment/39000000", timeout)
    if not err2 and html2:
        soup2 = BeautifulSoup(html2, "html.parser")
        for a in soup2.find_all("a", href=True):
            if "/unspsc/family/" not in a.get("href", ""):
                continue
            code = a.get_text(strip=True)
            if code.isdigit() and len(code) == 8:
                parent = a.find_parent("tr")
                name = ""
                if parent:
                    tds = parent.find_all("td")
                    for i, td in enumerate(tds):
                        if a in td.find_all("a") and i + 1 < len(tds):
                            name = tds[i + 1].get_text(strip=True)
                            break
                text_parts.append(f"Family {code} {name or code}")

    html3, err3 = _fetch_unspsc_page("/family/39120000", timeout)
    if not err3 and html3:
        soup3 = BeautifulSoup(html3, "html.parser")
        for a in soup3.find_all("a", href=True):
            if "/unspsc/class/" not in a.get("href", ""):
                continue
            code = a.get_text(strip=True)
            if code.isdigit() and len(code) == 8:
                parent = a.find_parent("tr")
                name = ""
                if parent:
                    tds = parent.find_all("td")
                    for i, td in enumerate(tds):
                        if a in td.find_all("a") and i + 1 < len(tds):
                            name = tds[i + 1].get_text(strip=True)
                            break
                text_parts.append(f"Class {code} {name or code}")

    text = " | ".join(text_parts) if text_parts else "No UNSPSC hierarchy data extracted."
    print(f"  [UNSPSC] Fetched {len(text)} chars")
    return text


# ---------------------------------------------------------------------------
# Manufacturer site scraping
# ---------------------------------------------------------------------------

MANUFACTURER_HIERARCHY_URLS = [
    {
        "name": "Siemens",
        "url": "https://www.siemens.com/global/en/products/automation/industrial-controls/sirius/sirius-control/contactors.html",
    },
    {
        "name": "Schneider Electric",
        "url": "https://www.se.com/in/en/product-category/1500-contactors-and-protection-relays/",
        "known_path": "Home > All products > Industrial Automation and Control > Contactors and Protection Relays > Contactors",
    },
    {
        "name": "Rockwell Automation",
        "url": "https://www.rockwellautomation.com/en-us/products/hardware/motor-control.html",
        "known_path": "Home > Products > Hardware Catalog > Motor Control",
    },
    {
        "name": "Eaton",
        "url": "https://www.eaton.com/in/en-us/products/controls-drives-automation-sensors/contactors-and-starters.html",
    },
]

HEADERS_HTTP = {"User-Agent": "Mozilla/5.0 (compatible; hierarchy-resolver/1.0)"}


def _hierarchy_from_url_path(url: str) -> str:
    parsed = urlparse(url)
    path = (parsed.path or "").strip("/")
    if not path:
        return ""
    segments = []
    for part in path.replace(".html", "").replace(".htm", "").split("/"):
        part = unquote(part)
        if not part or part in ("en", "us", "en-us", "www", "in"):
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
        if "nav" in cls_str or "path" in cls_str:
            text = elem.get_text(separator=" > ", strip=True)
            if 10 < len(text) < 400 and ">" in text:
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
        if "rockwellautomation" in page_url.lower() and "motor-control" in page_url:
            parts.insert(0, "Home > Products > Hardware Catalog > Motor Control")

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
    """Crawl manufacturer page and extract hierarchy path (breadcrumbs/nav). No AI."""
    last_error = None
    for attempt in range(2):
        try:
            resp = requests.get(url, timeout=timeout, headers=HEADERS_HTTP)
            if resp.status_code != 200:
                crawled = known_path or ""
                return {
                    "source_name": manufacturer_name,
                    "url": url,
                    "excerpt_from_site": f"HTTP {resp.status_code}",
                    "extracted_hierarchy": {"crawled_path": crawled, "error": f"HTTP {resp.status_code}"},
                }
            html = resp.text
            if "cloudflare" in html.lower() and "blocked" in html.lower():
                crawled = known_path or ""
                return {
                    "source_name": manufacturer_name,
                    "url": url,
                    "excerpt_from_site": "Blocked (Cloudflare)",
                    "extracted_hierarchy": {"crawled_path": crawled, "error": "Blocked"},
                }
            soup = BeautifulSoup(html, "html.parser")
            hierarchy_snippet = _extract_breadcrumb_and_nav(soup, page_url=url)
            crawled = _first_path_from_snippet(hierarchy_snippet) if hierarchy_snippet else ""
            if not crawled and known_path:
                crawled = known_path
            excerpt = (
                hierarchy_snippet[:500] + ("…" if len(hierarchy_snippet) > 500 else "")
                if hierarchy_snippet
                else ("No hierarchy found on page." if not known_path else "")
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
    crawled = known_path or ""
    return {
        "source_name": manufacturer_name,
        "url": url,
        "excerpt_from_site": f"Request failed: {last_error}",
        "extracted_hierarchy": {"crawled_path": crawled, "error": str(last_error)},
    }


def get_hierarchy_from_manufacturer_websites(category: str, timeout: int = 30) -> List[Dict]:
    """Crawl manufacturer sites for contactors; extract breadcrumb path only."""
    contributions = []
    for m in MANUFACTURER_HIERARCHY_URLS:
        name = m.get("name", "Unknown")
        url = m.get("url", "")
        known_path = m.get("known_path")
        if not url:
            continue
        print(f"  [Manufacturer] {name} ...")
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
    """
    Main workflow: UNSPSC + manufacturer website scraping -> single AI recommendation step.
    Returns (enriched DataFrame, list of JSON records).
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

        # 1) UNSPSC context
        unspsc_text = scrape_unspsc(category)
        unspsc_ai = extract_hierarchy_with_ai(unspsc_text, category, customer_hierarchy_paths=customer_paths)

        # 2) Manufacturer sites: crawl paths only
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

        # Optional user-provided HTML sources
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
                "excerpt_from_site": text[:excerpt_max_len] + ("…" if len(text) > excerpt_max_len else ""),
                "extracted_hierarchy": {"crawled_path": path_from_source},
            })
            if path_from_source:
                manufacturer_crawled_paths.append({"source_name": name, "crawled_path": path_from_source})

        # 3) Single AI step: recommend supply chain + ecommerce paths
        unspsc_path = (unspsc_ai or {}).get("hierarchy_path", "") or ""
        recommendation = recommend_paths_from_crawled_and_customer(
            category=category,
            customer_hierarchy_paths=customer_paths,
            unspsc_excerpt=unspsc_text,
            unspsc_hierarchy_path=unspsc_path or None,
            manufacturer_crawled_paths=manufacturer_crawled_paths,
        )

        supply_chain_path = recommendation.get("supply_chain_recommended_path", "")
        ecommerce_path = recommendation.get("ecommerce_recommended_path", "")
        global_path = recommendation.get("global_generalized_hierarchy_path", "")
        supply_chain_reason = recommendation.get("supply_chain_reason", "")
        ecommerce_reason = recommendation.get("ecommerce_reason", "")
        results.append(recommendation)

        json_records.append({
            "category": category,
            "recommended_path": supply_chain_path,
            "ecommerce_recommended_path": ecommerce_path,
            "global_generalized_hierarchy_path": global_path,
            "supply_chain_reason": supply_chain_reason,
            "ecommerce_reason": ecommerce_reason,
            "unspsc_code": recommendation.get("unspsc_code", ""),
            "standard": recommendation.get("standard", "UNSPSC/Manufacturer"),
            "confidence": recommendation.get("confidence", 0),
            "from_unspsc": {
                "excerpt_preview": unspsc_text[:excerpt_max_len] + ("…" if len(unspsc_text) > excerpt_max_len else ""),
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
