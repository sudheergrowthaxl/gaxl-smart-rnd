"""Prompt builders for hierarchy resolution.

Uses runtime-generated domain model for context — no static YAML backbone.
"""

from typing import List


def _get_domain_model_hierarchy_context(domain_model: dict | None) -> str:
    """Extract hierarchy-relevant context from the runtime domain model."""
    if not domain_model:
        return ""

    lines = []
    ov = domain_model.get("domain_overview", {})
    if ov:
        lines.append(
            f"Domain: {ov.get('domain', '?')} > {ov.get('sub_domain', '?')} > {ov.get('category', '?')}"
        )
        if ov.get("functional_purpose"):
            lines.append(f"Functional purpose: {ov['functional_purpose']}")
        if ov.get("system_boundaries"):
            lines.append(f"System boundaries: {ov['system_boundaries']}")

    entities = domain_model.get("entities", {})
    for group, items in entities.items():
        if items:
            names = [e.get("name", "") for e in items[:8]]
            lines.append(f"{group.replace('_', ' ').title()}: {', '.join(names)}")

    triplets = domain_model.get("ontology", {}).get("triplets", [])
    containment = [t for t in triplets if any(kw in str(t[1]).lower() for kw in ("partof", "contains", "classifiedas", "typeof", "type"))]
    if containment:
        lines.append("Key hierarchy relationships:")
        for t in containment[:10]:
            lines.append(f"  ({t[0]}, {t[1]}, {t[2]})")

    return "\n".join(lines)


def build_extract_hierarchy_prompt(
    raw_text: str,
    category: str,
    customer_hierarchy_paths: List[str] | None = None,
    domain_model: dict | None = None,
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

    dm_ctx = _get_domain_model_hierarchy_context(domain_model)
    backbone_block = ""
    if dm_ctx:
        backbone_block = f"""
    Domain model context (use as PRIMARY context to guide reasoning):
    {dm_ctx}
    """

    return f"""
    You are an expert in electrical equipment standards (UNSPSC, IEC 60947, NEMA) and in product taxonomy for both supply chain and ecommerce.

    Most organizations think about product data through two lenses:
    1) Supply chain lens (ERP): procurement, inventory, logistics, standards (UNSPSC, IEC, NEMA). Paths are often segment > family > class, aligned to how items are sourced and stored.
    2) Selling/commerce lens (ecommerce, channel, assortment): how products are presented and sold to buyers (e.g. web taxonomy, category navigation, merchandising).
    {backbone_block}
    From the text below (UNSPSC/manufacturer catalog/commerce site), extract for '{category}' TWO recommended hierarchy paths:
    - hierarchy_path: recommended path from a SUPPLY CHAIN (ERP) perspective.
    - ecommerce_hierarchy_path: recommended path from an ECOMMERCE/SELLING (channel, assortment) perspective.
    {customer_block}

    Examples (contactors):
    - Supply chain: "Electrical Equipment > Electrical equipment and components and supplies > Electrical controls and accessories > Contactors" (UNSPSC-aligned)
    - Ecommerce: "Industrial Controls > Contactors & Accessories > Contactors" or similar customer-facing navigation

    Chain of Thought: Briefly reason about the best fit for supply chain vs ecommerce before outputting JSON.

    Output ONLY valid JSON:
    {{
        "reasoning": "Supply chain path chosen because... Ecommerce path chosen because...",
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
    domain_model: dict | None = None,
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

    dm_ctx = _get_domain_model_hierarchy_context(domain_model)
    dm_block = ""
    if dm_ctx:
        dm_block = f"""
    **PRIMARY CONTEXT — Domain Model** (use this as the primary source for the global generalized hierarchy):
    {dm_ctx}
    """

    return f"""
    You are an expert in product taxonomy for supply chain (ERP) and ecommerce (channel, assortment).

    Available inputs for category "{category}":
    {dm_block}
    {unspsc_path_line}
    - UNSPSC excerpt (segment/family/class context): {unspsc_excerpt[:2800]}
    {customer_block}
    - Manufacturer/ecommerce site paths (REFERENCE ONLY — shown if user asks for them):
    {manufacturer_block}

    You must REASON and CHOOSE — do not default supply_chain to UNSPSC or ecommerce to manufacturer without explicit reasoning.

    1) global_generalized_hierarchy_path:
       The PRIMARY canonical taxonomy path derived from the DOMAIN MODEL context above.
       Use the domain model's domain > sub-domain > category structure, entity hierarchy,
       and functional purpose as the primary source. UNSPSC and manufacturer paths are
       references only. Output a clean, generalized hierarchy path.

    2) supply_chain_recommended_path (ERP/procurement):
       Which single path best supports procurement, inventory, and standards? Consider UNSPSC
       as the global standard for spend classification. Output that exact path string.

    3) ecommerce_recommended_path (selling/channel/assortment):
       Which single path best supports how buyers navigate and products are merchandised?
       Consider ecommerce sites and customer data. Output that exact path string.

    4) supply_chain_reason:
       One or two clear sentences: which path you chose for supply_chain_recommended_path,
       why it fits ERP/procurement, and which source it came from.

    5) ecommerce_reason:
       One or two clear sentences: which path you chose for ecommerce_recommended_path,
       why it fits selling/channel, and which source it came from.

    Output ONLY valid JSON. Reasons must be specific and non-generic.
    {{
        "global_generalized_hierarchy_path": "domain model derived canonical hierarchy path",
        "supply_chain_recommended_path": "exact path string for supply chain",
        "ecommerce_recommended_path": "exact path string for ecommerce",
        "supply_chain_reason": "specific reason",
        "ecommerce_reason": "specific reason",
        "unspsc_code": "39121529",
        "confidence": 0.95
    }}
    """
