"""Embedding generation using OpenAI API."""

import logging
import os
from typing import Any

from openai import OpenAI

from src.utils.exceptions import EmbeddingError

logger = logging.getLogger(__name__)


class Embedder:
    """Generate embeddings using OpenAI's embedding models."""

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the embedder.

        Args:
            config: Configuration dictionary with OpenAI settings.
        """
        self.config = config or {}
        openai_config = self.config.get("openai", {})

        api_key = openai_config.get("api_key") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise EmbeddingError(
                "OpenAI API key not found",
                details={"hint": "Set OPENAI_API_KEY environment variable"},
            )

        self.client = OpenAI(api_key=api_key)
        self.model = openai_config.get("embedding_model", "text-embedding-3-small")
        self.dimensions = openai_config.get("embedding_dimensions", 1536)

    def embed_text(self, text: str) -> list[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed.

        Returns:
            List of embedding floats.

        Raises:
            EmbeddingError: If embedding generation fails.
        """
        if not text or not text.strip():
            raise EmbeddingError(
                "Cannot embed empty text",
                details={"text": text},
            )

        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=text,
                dimensions=self.dimensions,
            )
            return response.data[0].embedding

        except Exception as e:
            raise EmbeddingError(
                f"Failed to generate embedding: {e}",
                details={"model": self.model, "error": str(e)},
            )

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a batch of texts.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding lists.

        Raises:
            EmbeddingError: If embedding generation fails.
        """
        if not texts:
            return []

        # Filter empty texts and track indices
        valid_texts = []
        valid_indices = []

        for i, text in enumerate(texts):
            if text and text.strip():
                valid_texts.append(text)
                valid_indices.append(i)

        if not valid_texts:
            raise EmbeddingError(
                "No valid texts to embed",
                details={"input_count": len(texts)},
            )

        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=valid_texts,
                dimensions=self.dimensions,
            )

            # Map embeddings back to original indices
            embeddings = [None] * len(texts)
            for j, embedding_obj in enumerate(response.data):
                original_index = valid_indices[j]
                embeddings[original_index] = embedding_obj.embedding

            # Fill None entries with zero vectors
            zero_vector = [0.0] * self.dimensions
            embeddings = [
                emb if emb is not None else zero_vector for emb in embeddings
            ]

            return embeddings

        except Exception as e:
            raise EmbeddingError(
                f"Failed to generate batch embeddings: {e}",
                details={"model": self.model, "batch_size": len(texts), "error": str(e)},
            )

    def embed_chunks(
        self, chunks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Add embeddings to chunk dictionaries.

        Args:
            chunks: List of chunk dictionaries with 'content' field.

        Returns:
            Chunks with 'embedding' field added.
        """
        texts = [chunk.get("content", "") for chunk in chunks]
        embeddings = self.embed_batch(texts)

        for chunk, embedding in zip(chunks, embeddings):
            chunk["embedding"] = embedding

        logger.info(f"Generated embeddings for {len(chunks)} chunks")
        return chunks
