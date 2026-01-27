"""Query expansion for improved retrieval."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class QueryExpander:
    """
    Expand queries with synonyms and related terms to improve recall.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the query expander.

        Args:
            config: Configuration dictionary with expansion settings.
        """
        self.config = config or {}

        # ABB-specific term mappings
        self.abb_synonyms = self.config.get("abb_mapping", {})

        # General electrical engineering synonyms
        self.general_synonyms = {
            "current": ["amperage", "amp", "A", "Ie"],
            "voltage": ["volt", "V", "Ue", "potential"],
            "power": ["watt", "W", "kW", "kilowatt"],
            "contactor": ["switch", "relay", "switching device"],
            "coil": ["control circuit", "electromagnet"],
            "durability": ["life", "lifespan", "endurance", "operations"],
            "rating": ["rated", "nominal", "specification"],
            "category": ["class", "type", "utilization"],
            "mechanical": ["physical", "mechanical life"],
            "electrical": ["electric", "electrical life"],
        }

        # Combine mappings
        self.synonyms = {**self.general_synonyms}
        for canonical, terms in self.abb_synonyms.items():
            if canonical in self.synonyms:
                self.synonyms[canonical].extend(terms)
            else:
                self.synonyms[canonical] = terms

    def expand(self, query: str, max_expansions: int = 3) -> list[str]:
        """
        Expand a query with synonyms and related terms.

        Args:
            query: Original query.
            max_expansions: Maximum number of expanded queries.

        Returns:
            List of expanded queries.
        """
        expanded = []
        query_lower = query.lower()

        # Find matching synonyms
        for term, synonyms in self.synonyms.items():
            if term in query_lower:
                for syn in synonyms[:2]:  # Limit synonyms per term
                    expanded_query = query_lower.replace(term, syn)
                    if expanded_query != query_lower:
                        expanded.append(expanded_query)

            # Also check if any synonym is in query
            for syn in synonyms:
                if syn.lower() in query_lower:
                    # Replace with canonical term
                    expanded_query = query_lower.replace(syn.lower(), term)
                    if expanded_query != query_lower:
                        expanded.append(expanded_query)

        # Add context-enhanced queries
        context_additions = self._add_context(query)
        expanded.extend(context_additions)

        # Deduplicate and limit
        seen = {query.lower()}
        unique_expanded = []
        for exp in expanded:
            if exp.lower() not in seen:
                seen.add(exp.lower())
                unique_expanded.append(exp)

        return unique_expanded[:max_expansions]

    def _add_context(self, query: str) -> list[str]:
        """
        Add contextual terms to query.

        Args:
            query: Original query.

        Returns:
            List of context-enhanced queries.
        """
        context_templates = [
            "{query} specification",
            "{query} ABB",
            "{query} contactor",
        ]

        return [template.format(query=query) for template in context_templates]

    def expand_attribute(self, attribute_name: str) -> list[str]:
        """
        Expand an attribute name with its known synonyms.

        Args:
            attribute_name: Canonical attribute name.

        Returns:
            List of attribute name variations.
        """
        # Check ABB mappings
        if attribute_name in self.abb_synonyms:
            return list(self.abb_synonyms[attribute_name])

        # Check general synonyms
        if attribute_name in self.synonyms:
            return list(self.synonyms[attribute_name])

        # Try partial matches
        variations = []
        attr_lower = attribute_name.lower().replace("_", " ")

        for term, syns in self.synonyms.items():
            if term in attr_lower:
                variations.extend(syns)

        return variations

    def get_canonical_name(self, term: str) -> str | None:
        """
        Get the canonical name for a term.

        Args:
            term: Term to look up.

        Returns:
            Canonical name if found, None otherwise.
        """
        term_lower = term.lower()

        # Direct match
        if term_lower in self.synonyms:
            return term_lower

        # Search in synonym lists
        for canonical, synonyms in self.synonyms.items():
            for syn in synonyms:
                if syn.lower() == term_lower:
                    return canonical

        return None
