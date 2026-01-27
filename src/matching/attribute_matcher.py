"""Attribute matching between cross-tab and RAG specifications."""

import logging
from typing import Any

from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)


class AttributeMatcher:
    """
    Match attributes between cross-tab ontology and RAG-retrieved specifications.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the attribute matcher.

        Args:
            config: Configuration dictionary with matching settings.
        """
        self.config = config or {}
        self.abb_mapping = self.config.get("abb_mapping", {})

        # Matching thresholds
        self.exact_threshold = 100
        self.fuzzy_threshold = 70  # Lowered for better matching

        # Prefixes to strip from attribute names
        self.prefixes_to_strip = ["zz_", "dr_", "xx_"]

        # Extended semantic mappings (crosstab term -> RAG canonical)
        self.semantic_mapping = {
            "control voltage": "coil_voltage",
            "coil voltage": "coil_voltage",
            "current rating": "rated_current",
            "rated current": "rated_current",
            "load current": "rated_current",
            "continuous current": "rated_current",
            "voltage rating": "rated_voltage",
            "rated voltage": "rated_voltage",
            "maximum voltage": "rated_voltage",
            "operating voltage": "rated_voltage",
            "supply voltage": "rated_voltage",
            "input voltage": "rated_voltage",
            "utilization category": "utilization_category",
            "category": "utilization_category",
            "mechanical life": "mechanical_durability",
            "mechanical durability": "mechanical_durability",
            "electrical life": "electrical_durability",
            "electrical durability": "electrical_durability",
        }

        # Build reverse mapping (ABB terms -> canonical)
        self.reverse_mapping = {}
        for canonical, terms in self.abb_mapping.items():
            for term in terms:
                self.reverse_mapping[term.lower()] = canonical

    def match_attributes(
        self,
        crosstab_attributes: list[str],
        rag_attributes: list[str],
    ) -> dict[str, Any]:
        """
        Match attributes between cross-tab and RAG sources.

        Args:
            crosstab_attributes: List of canonical attribute names from cross-tab.
            rag_attributes: List of attribute names extracted from RAG specs.

        Returns:
            Dictionary with matched, crosstab_only, and rag_only attributes.
        """
        logger.info(
            f"Matching {len(crosstab_attributes)} crosstab attributes "
            f"with {len(rag_attributes)} RAG attributes"
        )

        matched = []
        crosstab_only = []
        rag_only = list(rag_attributes)  # Start with all RAG attributes

        for ct_attr in crosstab_attributes:
            match_result = self._find_match(ct_attr, rag_attributes)

            if match_result:
                matched.append({
                    "canonical": ct_attr,
                    "rag_term": match_result["term"],
                    "match_type": match_result["type"],
                    "confidence": match_result["confidence"],
                })

                # Remove from rag_only list
                if match_result["term"] in rag_only:
                    rag_only.remove(match_result["term"])
            else:
                crosstab_only.append(ct_attr)

        result = {
            "matched": matched,
            "crosstab_only": crosstab_only,
            "rag_only": rag_only,
            "statistics": {
                "total_crosstab": len(crosstab_attributes),
                "total_rag": len(rag_attributes),
                "matched_count": len(matched),
                "crosstab_only_count": len(crosstab_only),
                "rag_only_count": len(rag_only),
                "match_rate": len(matched) / len(crosstab_attributes)
                if crosstab_attributes
                else 0,
            },
        }

        logger.info(
            f"Matched {len(matched)} attributes, "
            f"{len(crosstab_only)} crosstab-only, "
            f"{len(rag_only)} RAG-only"
        )

        return result

    def _normalize_attribute(self, attr: str) -> str:
        """
        Normalize an attribute name by stripping prefixes and formatting.

        Args:
            attr: Raw attribute name.

        Returns:
            Normalized attribute name.
        """
        normalized = attr.lower()

        # Strip common prefixes
        for prefix in self.prefixes_to_strip:
            if normalized.startswith(prefix.lower()):
                normalized = normalized[len(prefix):]
                break

        # Replace underscores with spaces
        normalized = normalized.replace("_", " ").strip()

        return normalized

    def _find_match(
        self, canonical_attr: str, rag_attributes: list[str]
    ) -> dict[str, Any] | None:
        """
        Find a matching RAG attribute for a canonical attribute.

        Args:
            canonical_attr: Canonical attribute name.
            rag_attributes: List of RAG attribute names.

        Returns:
            Match result dictionary or None.
        """
        # Normalize the crosstab attribute
        normalized_crosstab = self._normalize_attribute(canonical_attr)

        # 1. Check semantic mapping first (highest priority)
        if normalized_crosstab in self.semantic_mapping:
            mapped_rag = self.semantic_mapping[normalized_crosstab]
            if mapped_rag in rag_attributes:
                return {
                    "term": mapped_rag,
                    "type": "semantic_mapping",
                    "confidence": 0.98,
                    "original": canonical_attr,
                    "normalized": normalized_crosstab,
                }

        # 2. Check exact match (after normalization)
        for rag_attr in rag_attributes:
            normalized_rag = self._normalize_attribute(rag_attr)
            if normalized_rag == normalized_crosstab:
                return {
                    "term": rag_attr,
                    "type": "exact",
                    "confidence": 1.0,
                }

        # 3. Check ABB mapping
        for abb_canonical, abb_terms in self.abb_mapping.items():
            # Check if crosstab attribute matches ABB canonical
            if normalized_crosstab == abb_canonical.replace("_", " "):
                if abb_canonical in rag_attributes:
                    return {
                        "term": abb_canonical,
                        "type": "abb_canonical",
                        "confidence": 0.95,
                    }

            # Check if any ABB term matches
            for abb_term in abb_terms:
                if abb_term.lower() in normalized_crosstab:
                    if abb_canonical in rag_attributes:
                        return {
                            "term": abb_canonical,
                            "type": "abb_term_match",
                            "confidence": 0.90,
                            "matched_term": abb_term,
                        }

        # 4. Fuzzy matching with normalized names
        normalized_rag_list = [
            self._normalize_attribute(attr) for attr in rag_attributes
        ]

        result = process.extractOne(
            normalized_crosstab, normalized_rag_list, scorer=fuzz.token_sort_ratio
        )

        if result and result[1] >= self.fuzzy_threshold:
            original_idx = normalized_rag_list.index(result[0])
            return {
                "term": rag_attributes[original_idx],
                "type": "fuzzy",
                "confidence": result[1] / 100,
                "score": result[1],
            }

        # 5. Partial keyword matching
        crosstab_words = set(normalized_crosstab.split())
        for rag_attr in rag_attributes:
            rag_words = set(self._normalize_attribute(rag_attr).split())
            common_words = crosstab_words & rag_words
            if len(common_words) >= 1 and any(
                w in ["current", "voltage", "power", "rating", "category"]
                for w in common_words
            ):
                return {
                    "term": rag_attr,
                    "type": "keyword_match",
                    "confidence": 0.75,
                    "common_words": list(common_words),
                }

        return None

    def get_canonical_name(self, term: str) -> str | None:
        """
        Get the canonical name for an ABB term.

        Args:
            term: Term to look up.

        Returns:
            Canonical name if found, None otherwise.
        """
        term_lower = term.lower()

        # Check reverse mapping
        if term_lower in self.reverse_mapping:
            return self.reverse_mapping[term_lower]

        # Check if it's already canonical
        if term_lower in self.abb_mapping:
            return term_lower

        return None

    def extract_attributes_from_chunks(
        self, chunks: list[dict[str, Any]]
    ) -> list[str]:
        """
        Extract attribute names from RAG chunks.

        Args:
            chunks: List of chunk dictionaries.

        Returns:
            List of unique attribute names found.
        """
        attributes = set()

        for chunk in chunks:
            # Check metadata for detected attributes
            detected = chunk.get("metadata", {}).get("detected_attributes", [])
            if isinstance(detected, list):
                attributes.update(detected)
            elif isinstance(detected, str):
                attributes.update(detected.split(", "))

            # Also scan content for known patterns
            content = chunk.get("content", "").lower()
            for canonical, terms in self.abb_mapping.items():
                for term in terms:
                    if term.lower() in content:
                        attributes.add(canonical)
                        break

        return list(attributes)

    def create_matching_report(
        self, matching_result: dict[str, Any]
    ) -> str:
        """
        Create a human-readable matching report.

        Args:
            matching_result: Result from match_attributes().

        Returns:
            Formatted report string.
        """
        lines = ["=" * 60]
        lines.append("ATTRIBUTE MATCHING REPORT")
        lines.append("=" * 60)

        stats = matching_result["statistics"]
        lines.append(f"\nTotal Crosstab Attributes: {stats['total_crosstab']}")
        lines.append(f"Total RAG Attributes: {stats['total_rag']}")
        lines.append(f"Match Rate: {stats['match_rate']:.1%}")

        lines.append("\n--- MATCHED ATTRIBUTES ---")
        for match in matching_result["matched"]:
            lines.append(
                f"  {match['canonical']} <-> {match['rag_term']} "
                f"({match['match_type']}, {match['confidence']:.0%})"
            )

        lines.append("\n--- CROSSTAB ONLY (No Rules Generated) ---")
        for attr in matching_result["crosstab_only"]:
            lines.append(f"  - {attr}")

        lines.append("\n--- RAG ONLY (No Rules Generated) ---")
        for attr in matching_result["rag_only"]:
            lines.append(f"  - {attr}")

        lines.append("\n" + "=" * 60)

        return "\n".join(lines)
