"""Prompt builders for hierarchy resolution."""

from typing import List


def build_extract_hierarchy_prompt(
    raw_text: str,
    category: str,
    customer_hierarchy_paths: List[str] | None = None,
) -> str:
    """Build the prompt for AI-based hierarchy extraction from UNSPSC/manufacturer text."""
    customer_block = ""
    if customer_hierarchy_paths:
        paths_preview = " | ".join(customer_hierarchy_paths[:30])
        if len(customer_hierarchy_paths) > 30:
            paths_preview += " ..."
        customer_block = f"""
    The customer dataset uses these hierarchy paths (e.g. from RS Product Overview). Use them to align your recommendations where relevant:
    {paths_preview}
    """

    return f"""
    You are an expert in electrical equipment standards (UNSPSC, IEC 60947, NEMA) and in product taxonomy for both supply chain and ecommerce.

    Most organizations think about product data through two lenses:
    1) Supply chain lens (ERP): procurement, inventory, logistics, standards (UNSPSC, IEC, NEMA). Paths are often segment > family > class, aligned to how items are sourced and stored.
    2) Selling/commerce lens (ecommerce, channel, assortment): how products are presented and sold to buyers (e.g. web taxonomy, category navigation, merchandising).

    From the text below (UNSPSC/manufacturer catalog/commerce site), extract for '{category}' TWO recommended hierarchy paths:
    - hierarchy_path: recommended path from a SUPPLY CHAIN (ERP) perspective.
    - ecommerce_hierarchy_path: recommended path from an ECOMMERCE/SELLING (channel, assortment) perspective.
    {customer_block}

    Examples (contactors):
    - Supply chain: "Electrical Equipment > Electrical equipment and components and supplies > Electrical controls and accessories > Contactors" (UNSPSC-aligned)
    - Ecommerce: "Industrial Controls > Contactors & Accessories > Contactors" or similar customer-facing navigation

    Output ONLY valid JSON:
    {{
        "hierarchy_path": "Main > Category > Subcategory",
        "ecommerce_hierarchy_path": "Commerce > Category > Subcategory",
        "unspsc_code": "39121529",
        "standard": "IEC/NEMA/UNSPSC/Manufacturer",
        "confidence": 0.95
    }}
    Text: {raw_text[:8000]}
    """


def build_recommend_paths_prompt(
    category: str,
    customer_hierarchy_paths: List[str] | None,
    unspsc_excerpt: str,
    unspsc_hierarchy_path: str | None,
    manufacturer_crawled_paths: list,
) -> str:
    """Build the prompt for the single AI step that compares all sources and recommends paths."""
    customer_block = ""
    if customer_hierarchy_paths:
        paths_preview = " | ".join(customer_hierarchy_paths[:30])
        if len(customer_hierarchy_paths) > 30:
            paths_preview += " ..."
        customer_block = f"""
    Customer dataset hierarchy paths (e.g. RS Product Overview):
    {paths_preview}
    """

    unspsc_path_line = (
        f"- UNSPSC hierarchy path: {unspsc_hierarchy_path}"
        if unspsc_hierarchy_path
        else "    - UNSPSC hierarchy path: (none)"
    )
    manufacturer_block = "\n    ".join(
        f"- {c.get('source_name', 'Unknown')}: {c.get('crawled_path', '') or '(no path)'}"
        for c in manufacturer_crawled_paths
    )

    return f"""
    You are an expert in product taxonomy for supply chain (ERP) and ecommerce (channel, assortment).

    Available inputs for category "{category}":
    {unspsc_path_line}
    - UNSPSC excerpt (segment/family/class context): {unspsc_excerpt[:2800]}
    {customer_block}
    - Manufacturer/ecommerce site paths (crawled from real sites):
    {manufacturer_block}

    You must REASON and CHOOSE — do not default supply_chain to UNSPSC or ecommerce to manufacturer without explicit reasoning.

    1) supply_chain_recommended_path (ERP/procurement):
       Which single path best supports procurement, inventory, and standards (e.g. sourcing, P2P)? Consider: UNSPSC is the global standard for spend classification; customer paths may match how the organization already codes items; manufacturer paths reflect vendor taxonomies. Pick the path that best fits supply chain use (it may be UNSPSC, customer, or manufacturer — decide and justify). Output that exact path string.

    2) ecommerce_recommended_path (selling/channel/assortment):
       Which single path best supports how buyers navigate and how products are merchandised? Consider: ecommerce sites and customer data often use channel/assortment language; UNSPSC is rarely used on storefronts. Pick the path that best fits selling and discovery (it may be customer, manufacturer, or a cleaned UNSPSC-style path — decide and justify). Output that exact path string.

    3) global_generalized_hierarchy_path:
       One canonical path using strict priority: if UNSPSC path is available use it; else use the first/primary customer path; else use the best available manufacturer path. Output that single path.

    4) supply_chain_reason:
       One or two clear sentences: which path you chose for supply_chain_recommended_path, why it fits ERP/procurement better than the others, and which source it came from (UNSPSC / customer / manufacturer). No vague or generic phrases.

    5) ecommerce_reason:
       One or two clear sentences: which path you chose for ecommerce_recommended_path, why it fits selling/channel better than the others, and which source it came from. No vague or generic phrases.

    Output ONLY valid JSON. Use real paths from the inputs above; reasons must be specific and non-generic.
    {{
        "supply_chain_recommended_path": "exact path string you chose for supply chain",
        "ecommerce_recommended_path": "exact path string you chose for ecommerce",
        "global_generalized_hierarchy_path": "one path by priority UNSPSC then customer then manufacturer",
        "supply_chain_reason": "specific reason naming the chosen path and why it fits supply chain",
        "ecommerce_reason": "specific reason naming the chosen path and why it fits ecommerce",
        "unspsc_code": "39121529",
        "confidence": 0.95
    }}
    """
