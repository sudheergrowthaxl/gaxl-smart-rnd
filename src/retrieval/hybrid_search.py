"""Hybrid search combining vector and keyword-based retrieval."""

import logging
from typing import Any

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


class HybridSearch:
    """
    Hybrid search combining dense vector search with sparse BM25 retrieval.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the hybrid search.

        Args:
            config: Configuration dictionary with search settings.
        """
        self.config = config or {}
        hybrid_config = self.config.get("retrieval", {}).get("hybrid_search", {})

        self.enabled = hybrid_config.get("enabled", True)
        self.vector_weight = hybrid_config.get("vector_weight", 0.7)
        self.bm25_weight = hybrid_config.get("bm25_weight", 0.3)

        self.corpus: list[str] = []
        self.bm25: BM25Okapi | None = None

    def index_documents(self, documents: list[str]) -> None:
        """
        Index documents for BM25 search.

        Args:
            documents: List of document texts.
        """
        self.corpus = documents
        tokenized_corpus = [self._tokenize(doc) for doc in documents]
        self.bm25 = BM25Okapi(tokenized_corpus)
        logger.info(f"Indexed {len(documents)} documents for BM25 search")

    def search(
        self,
        query: str,
        vector_results: list[dict[str, Any]],
        n_results: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Perform hybrid search combining vector and BM25 results.

        Args:
            query: Search query.
            vector_results: Results from vector search.
            n_results: Number of results to return.

        Returns:
            Combined and scored results.
        """
        if not self.enabled or self.bm25 is None:
            return vector_results[:n_results]

        # Get BM25 scores
        tokenized_query = self._tokenize(query)
        bm25_scores = self.bm25.get_scores(tokenized_query)

        # Create document index map
        doc_to_idx = {doc[:100]: i for i, doc in enumerate(self.corpus)}

        # Score vector results
        scored_results = []
        for result in vector_results:
            doc_key = result["content"][:100]

            # Vector score (convert distance to similarity)
            vector_score = 1 - result.get("distance", 0)

            # BM25 score (normalized)
            bm25_score = 0
            if doc_key in doc_to_idx:
                idx = doc_to_idx[doc_key]
                if bm25_scores[idx] > 0:
                    bm25_score = bm25_scores[idx] / max(bm25_scores)

            # Combined score
            combined_score = (
                self.vector_weight * vector_score + self.bm25_weight * bm25_score
            )

            result["hybrid_score"] = combined_score
            result["vector_score"] = vector_score
            result["bm25_score"] = bm25_score
            scored_results.append(result)

        # Sort by hybrid score
        scored_results.sort(key=lambda x: x["hybrid_score"], reverse=True)

        return scored_results[:n_results]

    def _tokenize(self, text: str) -> list[str]:
        """
        Tokenize text for BM25.

        Args:
            text: Text to tokenize.

        Returns:
            List of tokens.
        """
        # Simple whitespace tokenization with lowercasing
        return text.lower().split()

    def add_documents(self, documents: list[str]) -> None:
        """
        Add new documents to the BM25 index.

        Args:
            documents: List of new document texts.
        """
        self.corpus.extend(documents)
        tokenized_corpus = [self._tokenize(doc) for doc in self.corpus]
        self.bm25 = BM25Okapi(tokenized_corpus)
        logger.debug(f"Added {len(documents)} documents, total: {len(self.corpus)}")

    def get_bm25_scores(
        self, query: str, documents: list[str]
    ) -> list[tuple[str, float]]:
        """
        Get BM25 scores for documents against a query.

        Args:
            query: Search query.
            documents: List of documents to score.

        Returns:
            List of (document, score) tuples.
        """
        # Create temporary BM25 index
        tokenized_docs = [self._tokenize(doc) for doc in documents]
        temp_bm25 = BM25Okapi(tokenized_docs)

        tokenized_query = self._tokenize(query)
        scores = temp_bm25.get_scores(tokenized_query)

        return list(zip(documents, scores))
