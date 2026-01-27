"""Reranking for improved retrieval precision."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class Reranker:
    """
    Rerank retrieved documents using cross-encoder or other scoring methods.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the reranker.

        Args:
            config: Configuration dictionary with reranking settings.
        """
        self.config = config or {}
        rerank_config = self.config.get("retrieval", {}).get("reranking", {})

        self.enabled = rerank_config.get("enabled", True)
        self.model_name = rerank_config.get(
            "model", "cross-encoder/ms-marco-MiniLM-L-6-v2"
        )

        self.cross_encoder = None
        self._initialize_model()

    def _initialize_model(self) -> None:
        """Initialize the cross-encoder model."""
        if not self.enabled:
            return

        try:
            from sentence_transformers import CrossEncoder

            self.cross_encoder = CrossEncoder(self.model_name)
            logger.info(f"Initialized cross-encoder: {self.model_name}")
        except ImportError:
            logger.warning(
                "sentence-transformers not installed. Reranking disabled."
            )
            self.enabled = False
        except Exception as e:
            logger.warning(f"Failed to load cross-encoder: {e}. Reranking disabled.")
            self.enabled = False

    def rerank(
        self, query: str, documents: list[dict[str, Any]], top_k: int | None = None
    ) -> list[dict[str, Any]]:
        """
        Rerank documents based on relevance to query.

        Args:
            query: Search query.
            documents: List of document dictionaries.
            top_k: Number of top documents to return.

        Returns:
            Reranked list of documents.
        """
        if not documents:
            return documents

        if not self.enabled or self.cross_encoder is None:
            return self._simple_rerank(query, documents)

        try:
            # Prepare query-document pairs
            pairs = [(query, doc["content"]) for doc in documents]

            # Get cross-encoder scores
            scores = self.cross_encoder.predict(pairs)

            # Add scores to documents
            for doc, score in zip(documents, scores):
                doc["rerank_score"] = float(score)

            # Sort by rerank score
            documents.sort(key=lambda x: x["rerank_score"], reverse=True)

            if top_k:
                documents = documents[:top_k]

            logger.debug(f"Reranked {len(documents)} documents")
            return documents

        except Exception as e:
            logger.warning(f"Reranking failed: {e}. Using simple rerank.")
            return self._simple_rerank(query, documents)

    def _simple_rerank(
        self, query: str, documents: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Simple reranking based on keyword matching.

        Args:
            query: Search query.
            documents: List of document dictionaries.

        Returns:
            Reranked list of documents.
        """
        query_terms = set(query.lower().split())

        for doc in documents:
            content_lower = doc["content"].lower()
            content_terms = set(content_lower.split())

            # Score based on term overlap
            overlap = len(query_terms & content_terms)
            total_terms = len(query_terms)

            # Exact phrase bonus
            phrase_bonus = 1.0 if query.lower() in content_lower else 0.0

            # Calculate simple score
            score = (overlap / total_terms if total_terms > 0 else 0) + phrase_bonus

            doc["simple_rerank_score"] = score

        documents.sort(key=lambda x: x.get("simple_rerank_score", 0), reverse=True)
        return documents

    def rerank_for_attribute(
        self, attribute_name: str, documents: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Rerank documents specifically for attribute retrieval.

        Args:
            attribute_name: Attribute being searched.
            documents: List of document dictionaries.

        Returns:
            Reranked documents.
        """
        # Create attribute-focused query
        query = f"What is the {attribute_name.replace('_', ' ')} specification?"

        # Add attribute-specific scoring
        for doc in documents:
            content_lower = doc["content"].lower()
            attr_lower = attribute_name.lower().replace("_", " ")

            # Check for attribute mention
            attr_mention = attr_lower in content_lower
            doc["attribute_mention"] = attr_mention

            # Check for numerical values (likely specifications)
            import re

            has_numbers = bool(re.search(r"\d+", doc["content"]))
            doc["has_values"] = has_numbers

        # Rerank with cross-encoder
        reranked = self.rerank(query, documents)

        # Boost documents with attribute mentions and values
        for doc in reranked:
            boost = 0
            if doc.get("attribute_mention"):
                boost += 0.2
            if doc.get("has_values"):
                boost += 0.1

            if "rerank_score" in doc:
                doc["rerank_score"] += boost
            elif "simple_rerank_score" in doc:
                doc["simple_rerank_score"] += boost

        # Re-sort with boosts applied
        score_key = "rerank_score" if "rerank_score" in reranked[0] else "simple_rerank_score"
        reranked.sort(key=lambda x: x.get(score_key, 0), reverse=True)

        return reranked
