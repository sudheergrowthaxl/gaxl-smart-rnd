"""Tavily web search to build domain context per attribute for normalisation rules."""

from typing import Any

from normalisation_rules.config import TAVILY_API_KEY

# Lazy client to avoid import errors if tavily not used
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


def search_attribute_context(
    attribute_name: str,
    domain: str = "electrical contactors",
    max_results: int = 5,
    max_content_chars: int = 8000,
) -> tuple[str, str]:
    """
    Search the web for domain context about this attribute (e.g. standard terms, normalisation).
    Returns (context_string, query_used) to pass to the LLM and optionally log.
    """
    if not TAVILY_API_KEY:
        return ("", "")
    client = get_tavily_client()
    # Clean attribute label for search (e.g. zz_Number of Poles -> number of poles contactor)
    label = attribute_name.replace("zz_", "").strip()
    query = f"What is {label} in {domain} & get the standard values from NEMA or IEC standards for the same attribute."
    try:
        response = client.search(
            query=query,
            search_depth="basic",
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


def search_standards_context(
    attribute_name: str,
    domain: str = "electrical contactors",
    max_results: int = 5,
    max_content_chars: int = 6000,
) -> tuple[str, str]:
    """
    Search the web for NEMA and IEC standards context about this attribute.
    Returns (context_string, query_used).
    """
    if not TAVILY_API_KEY:
        return ("", "")
    client = get_tavily_client()
    label = attribute_name.replace("zz_", "").strip()
    query = f"Fetch the standard definitions & values from  NEMA, IEC  for the Attribute: {label} from the following domain: {domain} "
    try:
        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=max_results,
            include_answer=True,
            chunks_per_source=5,
            include_domains=["https://www.nema.org/", "https://www.iec.ch/"]    
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


def search_manufacturers_context(
    attribute_name: str,
    domain: str = "electrical contactors",
    max_results: int = 5,
    max_content_chars: int = 6000,
) -> tuple[str, str]:
    """
    Search the web for manufacturer/vendor catalog and datasheet values for this attribute.
    Returns (context_string, query_used).
    """
    if not TAVILY_API_KEY:
        return ("", "")
    client = get_tavily_client()
    label = attribute_name.replace("zz_", "").strip()
    query = f"{domain} {label} manufacturer catalog Siemens ABB Schneider Eaton possible values datasheet"
    try:
        response = client.search(
            query=query,
            search_depth="basic",
            max_results=max_results,
            include_answer=True,
            chunks_per_source=5,
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
