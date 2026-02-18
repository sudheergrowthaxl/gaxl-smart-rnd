"""Tavily web search to build domain context per attribute for normalisation rules."""

from typing import Any

from normalisation_rules.config import TAVILY_API_KEY, DEFAULT_MANUFACTURERS

# Lazy client to avoid import errors if tavily not used
_tavily_client: Any = None

# Attribute-name keywords that indicate Tavily search won't add value
# (dates, internal IDs, free-text descriptions, manufacturer-specific fields)
_SKIP_KEYWORDS = [
    "date",
    "expiry",
    "row number",
    "part number",
    "character description",
    "mfr part",
]


def get_tavily_client():
    global _tavily_client
    if _tavily_client is None:
        try:
            from tavily import TavilyClient
            _tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
        except Exception as e:
            raise RuntimeError("Tavily client could not be created. Set TAVILY_API_KEY.") from e
    return _tavily_client


def should_skip_tavily(attribute_name: str) -> bool:
    """Return True if this attribute is unlikely to benefit from web search."""
    label = attribute_name.replace("zz_", "").strip().lower()
    return any(kw in label for kw in _SKIP_KEYWORDS)


def search_attribute_context(
    attribute_name: str,
    domain: str = "electrical contactors",
    max_results: int = 5,
    max_content_chars: int = 8000,
    search_depth: str = "basic",
    sample_values: list[str] | None = None,
) -> tuple[str, str]:
    """
    Search the web for domain context about this attribute.
    Returns (context_string, query_used) to pass to the LLM and optionally log.

    Parameters
    ----------
    search_depth : "basic" or "advanced"
        basic  = faster, fewer results, lower cost
        advanced = deeper crawl, richer context, higher cost
    sample_values : list of top observed values (optional)
        Included in the query so Tavily returns format-specific results.
    """
    if not TAVILY_API_KEY:
        return ("", "")

    # Skip attributes where web search adds no value
    if should_skip_tavily(attribute_name):
        return ("", f"(skipped: '{attribute_name}' not suitable for web search)")

    client = get_tavily_client()
    label = attribute_name.replace("zz_", "").strip()

    # --- Build query with sample values for targeted results ---
    if sample_values:
        top_vals = ", ".join(f"'{v}'" for v in sample_values[:5])
        query = (
            f"Standard accepted values for '{label}' in {domain}. "
            f"Observed variations: {top_vals}. "
            f"What are the canonical forms per IEC 60947 or NEMA ICS standards?"
        )
    else:
        query = (
            f"Standard values and classifications for '{label}' in {domain} "
            f"according to IEC 60947 and NEMA ICS standards. "
            f"List all allowed values and common abbreviations."
        )

    # Adjust limits for advanced depth (richer context budget)
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
    manufacturers: list[str] | None = None,
    domain: str = "electrical contactors",
    max_results: int = 5,
    max_content_chars: int = 8000,
    search_depth: str = None,
    sample_values: list[str] | None = None,
) -> tuple[str, str]:
    """
    Search manufacturer websites/catalogs for values of this attribute.
    Returns (context_string, query_used).

    Makes a single consolidated Tavily query mentioning all manufacturers
    to find how they represent this attribute in their product catalogs.
    """
    if not TAVILY_API_KEY:
        return ("", "")

    if should_skip_tavily(attribute_name):
        return ("", f"(skipped: '{attribute_name}' not suitable for manufacturer search)")

    if manufacturers is None:
        manufacturers = DEFAULT_MANUFACTURERS

    client = get_tavily_client()
    label = attribute_name.replace("zz_", "").strip()
    mfr_names = ", ".join(manufacturers)

    # Build query targeting manufacturer catalog values
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

    # Adjust limits for advanced depth
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
