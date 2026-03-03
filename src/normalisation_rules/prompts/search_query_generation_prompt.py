"""Prompt for LLM-generated Tavily search queries (replaces hardcoded query lists)."""


def build_search_query_generation_prompt(category: str, query_type: str) -> str:
    """Generate optimal search queries for a given category and purpose.

    Args:
        category: The product category (e.g., 'Contactors', 'Relays').
        query_type: Either 'standards' or 'manufacturer'.
    """
    if query_type == "standards":
        return f"""You are an expert in industrial electrical equipment standards and product classification.

**Task**: Generate 3–5 optimal web search queries to find standards-based attribute
definitions for the product category **{category}**.

**Chain of Thought:**
1. What IS a {category.lower()}? What is its primary function?
2. Which international standards govern this category? (IEC, NEMA, UNSPSC, UL, etc.)
3. What search queries would return the most useful attribute/specification lists
   from these standards bodies and technical references?

**Requirements:**
- Queries should target UNSPSC classification, IEC/NEMA specifications, and
  technical attribute lists.
- Include the category name in each query.
- Make queries specific enough to return attribute/property lists, not general info.

**Output ONLY valid JSON:**
{{
  "reasoning": "A {category.lower()} is ... governed by standards ... key queries target ...",
  "queries": [
    "UNSPSC {category.lower()} attributes properties classification",
    "..."
  ]
}}
"""
    else:
        return f"""You are an expert in industrial electrical equipment and manufacturer product catalogs.

**Task**: Generate 3–5 optimal web search queries to find manufacturer-specific
attribute definitions and datasheet specifications for **{category}**.

**Chain of Thought:**
1. What IS a {category.lower()}? How do manufacturers specify and differentiate variants?
2. Which major manufacturers produce {category.lower()}s?
3. What search queries would return the most useful datasheet attributes and
   catalog specifications from these manufacturers?

**Requirements:**
- Queries should target manufacturer datasheets, product catalogs, and technical specs.
- Include the category name and at least one manufacturer name per query.
- Make queries specific enough to return attribute lists, not marketing pages.

**Output ONLY valid JSON:**
{{
  "reasoning": "A {category.lower()} is manufactured by ... key datasheet attributes include ... queries target ...",
  "queries": [
    "{category.lower()} technical specifications datasheet attributes",
    "..."
  ]
}}
"""
