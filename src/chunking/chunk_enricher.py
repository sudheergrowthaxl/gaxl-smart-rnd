"""Chunk enrichment with additional metadata and context."""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class ChunkEnricher:
    """
    Enrich chunks with additional metadata, context, and semantic annotations.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the chunk enricher.

        Args:
            config: Configuration dictionary with enrichment settings.
        """
        self.config = config or {}
        self.abb_mapping = self.config.get("abb_mapping", {})

    def enrich_chunks(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Enrich a list of chunks with additional metadata.

        Args:
            chunks: List of chunk dictionaries.

        Returns:
            List of enriched chunk dictionaries.
        """
        enriched = []

        for i, chunk in enumerate(chunks):
            enriched_chunk = self._enrich_single_chunk(chunk, i)
            enriched.append(enriched_chunk)

        logger.info(f"Enriched {len(enriched)} chunks")
        return enriched

    def _enrich_single_chunk(
        self, chunk: dict[str, Any], index: int
    ) -> dict[str, Any]:
        """
        Enrich a single chunk with metadata.

        Args:
            chunk: Chunk dictionary.
            index: Chunk index.

        Returns:
            Enriched chunk dictionary.
        """
        content = chunk.get("content", "")
        metadata = chunk.get("metadata", {}).copy()

        # Add chunk ID
        metadata["chunk_id"] = f"chunk_{index:04d}"

        # Extract and add technical attributes
        attributes = self._extract_attributes(content)
        if attributes:
            metadata["detected_attributes"] = attributes

        # Add ABB product references
        products = self._extract_abb_products(content)
        if products:
            metadata["abb_products"] = products

        # Add numerical ranges
        ranges = self._extract_numerical_ranges(content)
        if ranges:
            metadata["numerical_ranges"] = ranges

        # Classify content type
        metadata["content_category"] = self._classify_content(content)

        return {
            "content": content,
            "token_count": chunk.get("token_count", 0),
            "metadata": metadata,
        }

    def _extract_attributes(self, content: str) -> list[str]:
        """
        Extract technical attribute mentions from content.

        Args:
            content: Chunk content.

        Returns:
            List of detected attribute names.
        """
        attributes = []
        content_lower = content.lower()

        # Check for ABB-specific terms
        abb_terms = {
            "rated_current": ["ie", "rated operational current", "rated current"],
            "rated_voltage": ["ue", "rated operational voltage", "rated voltage"],
            "coil_voltage": ["control circuit voltage", "coil voltage"],
            "utilization_category": ["ac-1", "ac-3", "ac-4", "utilization category"],
            "mechanical_durability": ["mechanical life", "mechanical durability"],
            "electrical_durability": ["electrical life", "electrical durability"],
        }

        for attr, terms in abb_terms.items():
            for term in terms:
                if term in content_lower:
                    if attr not in attributes:
                        attributes.append(attr)
                    break

        return attributes

    def _extract_abb_products(self, content: str) -> list[str]:
        """
        Extract ABB product references from content.

        Args:
            content: Chunk content.

        Returns:
            List of ABB product codes.
        """
        # ABB contactor patterns
        patterns = [
            r"\bA[FX]?\d{2,3}\b",  # AF26, AX09, A16
            r"\bA-Line\b",
            r"\bAF\s?\d+\b",
        ]

        products = set()
        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            products.update(matches)

        return list(products)

    def _extract_numerical_ranges(self, content: str) -> list[dict[str, Any]]:
        """
        Extract numerical ranges and values from content.

        Args:
            content: Chunk content.

        Returns:
            List of numerical range dictionaries.
        """
        ranges = []

        # Patterns for common electrical specifications
        patterns = [
            # Voltage patterns: 24V, 230 V, 400VAC
            (r"(\d+(?:\.\d+)?)\s*(?:V|VAC|VDC)", "voltage"),
            # Current patterns: 9A, 26 A
            (r"(\d+(?:\.\d+)?)\s*A\b", "current"),
            # Power patterns: 5.5kW, 7.5 kW
            (r"(\d+(?:\.\d+)?)\s*(?:kW|MW|W)\b", "power"),
            # Frequency: 50Hz, 60 Hz
            (r"(\d+(?:\.\d+)?)\s*Hz\b", "frequency"),
            # Operations/cycles
            (r"(\d+(?:,\d+)*)\s*(?:operations|cycles)", "durability"),
        ]

        for pattern, attr_type in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                value = match.replace(",", "")
                try:
                    ranges.append({
                        "type": attr_type,
                        "value": float(value),
                        "raw": match,
                    })
                except ValueError:
                    continue

        return ranges

    def _classify_content(self, content: str) -> str:
        """
        Classify the content type of a chunk.

        Args:
            content: Chunk content.

        Returns:
            Content category string.
        """
        content_lower = content.lower()

        # Check for specification indicators
        if any(
            term in content_lower
            for term in ["rated", "specification", "technical data", "parameters"]
        ):
            return "specification"

        # Check for table indicators
        if "|" in content and content.count("|") > 3:
            return "table"

        # Check for application notes
        if any(
            term in content_lower
            for term in ["application", "usage", "installation", "wiring"]
        ):
            return "application"

        # Check for safety/standards
        if any(
            term in content_lower
            for term in ["iec", "ul", "ce", "safety", "standard", "compliance"]
        ):
            return "standards"

        return "general"

    def add_hierarchical_context(
        self, chunks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Add hierarchical context linking chunks to parent sections.

        Args:
            chunks: List of chunk dictionaries.

        Returns:
            Chunks with hierarchical context added.
        """
        # Group chunks by page
        pages: dict[int, list] = {}
        for chunk in chunks:
            page_num = chunk.get("metadata", {}).get("page_number", 0)
            if page_num not in pages:
                pages[page_num] = []
            pages[page_num].append(chunk)

        # Add context
        for page_num, page_chunks in pages.items():
            for i, chunk in enumerate(page_chunks):
                chunk["metadata"]["position_in_page"] = i + 1
                chunk["metadata"]["chunks_in_page"] = len(page_chunks)

                # Add previous/next chunk references
                if i > 0:
                    chunk["metadata"]["prev_chunk_id"] = page_chunks[i - 1][
                        "metadata"
                    ].get("chunk_id")
                if i < len(page_chunks) - 1:
                    chunk["metadata"]["next_chunk_id"] = page_chunks[i + 1][
                        "metadata"
                    ].get("chunk_id")

        return chunks
