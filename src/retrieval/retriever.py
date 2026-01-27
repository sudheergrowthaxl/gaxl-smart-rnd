"""Main retriever for RAG pipeline."""

import logging
from typing import Any

from src.embedding.embedder import Embedder
from src.retrieval.hybrid_search import HybridSearch
from src.retrieval.query_expander import QueryExpander
from src.retrieval.reranker import Reranker
from src.vectordb.collection_manager import CollectionManager
from src.utils.exceptions import RetrievalError

logger = logging.getLogger(__name__)


class Retriever:
    """
    Main retriever that orchestrates query expansion, hybrid search,
    and reranking for optimal retrieval.
    """

    def __init__(
        self,
        embedder: Embedder,
        collection_manager: CollectionManager,
        config: dict[str, Any] | None = None,
    ):
        """
        Initialize the retriever.

        Args:
            embedder: Embedder instance for query embedding.
            collection_manager: Collection manager for vector search.
            config: Configuration dictionary with retrieval settings.
        """
        self.embedder = embedder
        self.collection_manager = collection_manager
        self.config = config or {}

        retrieval_config = self.config.get("retrieval", {})

        self.top_k = retrieval_config.get("top_k", 10)
        self.similarity_threshold = retrieval_config.get("similarity_threshold", 0.75)

        # Initialize components
        self.query_expander = QueryExpander(config)
        self.hybrid_search = HybridSearch(config)
        self.reranker = Reranker(config)

    def retrieve(
        self,
        query: str,
        n_results: int | None = None,
        collection_types: list[str] | None = None,
        use_expansion: bool = True,
        use_reranking: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Retrieve relevant documents for a query.

        Args:
            query: Search query.
            n_results: Number of results to return.
            collection_types: Types of collections to search.
            use_expansion: Whether to use query expansion.
            use_reranking: Whether to use reranking.

        Returns:
            List of retrieved document dictionaries.

        Raises:
            RetrievalError: If retrieval fails.
        """
        n_results = n_results or self.top_k

        try:
            # Query expansion
            queries = [query]
            if use_expansion:
                expanded = self.query_expander.expand(query)
                queries.extend(expanded)
                logger.debug(f"Expanded to {len(queries)} queries")

            # Get embeddings for all queries
            query_embeddings = self.embedder.embed_batch(queries)

            # Perform vector search for each query
            all_results = []
            for q_embedding in query_embeddings:
                results = self.collection_manager.search(
                    query_embedding=q_embedding,
                    collection_types=collection_types,
                    n_results=n_results * 2,  # Get more for reranking
                )
                all_results.extend(results)

            # Deduplicate results
            seen = set()
            unique_results = []
            for result in all_results:
                content_hash = hash(result["content"][:100])
                if content_hash not in seen:
                    seen.add(content_hash)
                    unique_results.append(result)

            # Filter by similarity threshold
            filtered = [
                r
                for r in unique_results
                if self._distance_to_similarity(r["distance"]) >= self.similarity_threshold
            ]

            if not filtered:
                logger.warning("No results above similarity threshold")
                filtered = unique_results[:n_results]

            # Reranking
            if use_reranking and len(filtered) > 1:
                filtered = self.reranker.rerank(query, filtered)

            # Return top results
            results = filtered[:n_results]

            logger.info(f"Retrieved {len(results)} documents for query: {query[:50]}...")
            return results

        except Exception as e:
            raise RetrievalError(
                f"Failed to retrieve documents: {e}",
                details={"query": query, "error": str(e)},
            )

    def retrieve_for_attribute(
        self, attribute_name: str, synonyms: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """
        Retrieve documents relevant to a specific attribute.

        Args:
            attribute_name: Canonical attribute name.
            synonyms: Optional list of synonyms for the attribute.

        Returns:
            List of relevant documents.
        """
        # Build comprehensive query
        queries = [attribute_name]
        if synonyms:
            queries.extend(synonyms)

        # Add common context words
        context_words = ["specification", "range", "value", "technical"]
        expanded_queries = []
        for q in queries:
            for ctx in context_words:
                expanded_queries.append(f"{q} {ctx}")

        all_queries = queries + expanded_queries

        # Retrieve for all queries
        all_results = []
        for query in all_queries[:10]:  # Limit to prevent too many API calls
            try:
                results = self.retrieve(
                    query,
                    n_results=5,
                    use_expansion=False,
                    use_reranking=False,
                )
                all_results.extend(results)
            except Exception as e:
                logger.warning(f"Failed to retrieve for query '{query}': {e}")

        # Deduplicate and score
        scored_results = {}
        for result in all_results:
            content_key = result["content"][:100]
            if content_key in scored_results:
                scored_results[content_key]["score"] += 1
            else:
                result["score"] = 1
                scored_results[content_key] = result

        # Sort by score
        final_results = sorted(
            scored_results.values(),
            key=lambda x: x["score"],
            reverse=True,
        )

        return final_results[: self.top_k]

    def _distance_to_similarity(self, distance: float) -> float:
        """
        Convert distance to similarity score.

        Args:
            distance: Distance value (0 = identical for cosine).

        Returns:
            Similarity score (0-1).
        """
        # For cosine distance: similarity = 1 - distance
        return max(0, 1 - distance)
