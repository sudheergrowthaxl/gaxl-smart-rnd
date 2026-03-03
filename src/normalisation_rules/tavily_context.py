"""Tavily web search to build domain context per attribute for normalisation rules.

No hardcoded domain strings or skip-keyword lists. The domain is passed by
callers based on the detected category, and skip logic uses data profiling
statistics rather than keyword matching.
"""

from typing import Any

from normalisation_rules.config import TAVILY_API_KEY

_tavily_client: Any = None


def get_tavily_client():
    global _tavily_client
    if _tavily_client is None:
        try:
            from tavily import TavilyClient
            _tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
        except Exception as e:
            raise RuntimeError("Tavily client could not be created. Set TAVILY_API_KEY.") from e
    return _tavily_client


def should_skip_tavily(attribute: dict) -> bool:
    """Determine from data statistics whether Tavily search would add value.

    Uses the attribute's profiling data (semantic_type, distinct_count, etc.)
    instead of a hardcoded keyword list.
    """
    semantic = (attribute.get("semantic_type") or "").strip()
    if semantic in ("ID", "Constant", "Empty/NA"):
        return True

    name_lower = attribute.get("name", "").lower()
    # Skip obvious non-searchable fields based on structural patterns
    if any(pattern in name_lower for pattern in ("row number", "row_number", "index", "unnamed:")):
        return True

    return False


def search_attribute_context(
    attribute_name: str,
    domain: str,
    max_results: int = 5,
    max_content_chars: int = 8000,
    search_depth: str = "basic",
    sample_values: list[str] | None = None,
) -> tuple[str, str]:
    """Search the web for domain context about this attribute.

    Args:
        domain: Required — the domain string for search queries
                (e.g., "electrical contactors", "electrical relays").
    """
    if not TAVILY_API_KEY:
        return ("", "")

    client = get_tavily_client()
    label = attribute_name.strip()

    if sample_values:
        top_vals = ", ".join(f"'{v}'" for v in sample_values[:5])
        query = (
            f"Standard accepted values for '{label}' in {domain}. "
            f"Observed variations: {top_vals}. "
            f"What are the canonical forms per IEC or NEMA standards?"
        )
    else:
        query = (
            f"Standard values and classifications for '{label}' in {domain} "
            f"according to IEC and NEMA standards. "
            f"List all allowed values and common abbreviations."
        )

    if search_depth == "advanced":
        max_results = max(max_results, 10)
        max_content_chars = max(max_content_chars, 15000)

    try:
        response = client.search(
            query=query,
            search_depth=search_depth,
            max_results=max_results,
            include_answer=True,
        )
    except Exception:
        return ("", query)

    parts = []
    if response.get("answer"):
        parts.append(response["answer"])
    for r in (response.get("results") or [])[:max_results]:
        content = (r.get("content") or "").strip()
        if content:
            if len(content) > 1200:
                content = content[:1200] + "..."
            parts.append(content)
    combined = "\n\n".join(parts)
    if len(combined) > max_content_chars:
        combined = combined[:max_content_chars] + "..."
    return (combined.strip(), query)


def search_manufacturer_values(
    attribute_name: str,
    manufacturers: list[str],
    domain: str,
    max_results: int = 5,
    max_content_chars: int = 8000,
    search_depth: str | None = None,
    sample_values: list[str] | None = None,
) -> tuple[str, str]:
    """Search manufacturer catalogs for values of this attribute.

    Args:
        manufacturers: Required — list of manufacturer names to search.
        domain: Required — the domain string for search queries.
    """
    if not TAVILY_API_KEY:
        return ("", "")

    client = get_tavily_client()
    label = attribute_name.strip()
    mfr_names = ", ".join(manufacturers)

    if sample_values:
        top_vals = ", ".join(f"'{v}'" for v in sample_values[:5])
        query = (
            f"Product catalog values for '{label}' in {domain} from manufacturers: {mfr_names}. "
            f"Customer data shows variations: {top_vals}. "
            f"What specific values and formats do these manufacturers use in their datasheets and catalogs?"
        )
    else:
        query = (
            f"Product catalog values for '{label}' in {domain} from manufacturers: {mfr_names}. "
            f"What specific values and formats do these manufacturers use in their datasheets and catalogs?"
        )

    if search_depth == "advanced":
        max_results = max(max_results, 10)
        max_content_chars = max(max_content_chars, 15000)

    try:
        response = client.search(
            query=query,
            search_depth=search_depth,
            max_results=max_results,
            include_answer=True,
        )
    except Exception:
        return ("", query)

    parts = []
    if response.get("answer"):
        parts.append(response["answer"])
    for r in (response.get("results") or [])[:max_results]:
        content = (r.get("content") or "").strip()
        if content:
            if len(content) > 1200:
                content = content[:1200] + "..."
            parts.append(content)
    combined = "\n\n".join(parts)
    if len(combined) > max_content_chars:
        combined = combined[:max_content_chars] + "..."
    return (combined.strip(), query)
