"""Batch processing for embedding generation with rate limiting."""

import logging
import time
from typing import Any, Callable

from src.embedding.embedder import Embedder

logger = logging.getLogger(__name__)


class BatchProcessor:
    """
    Process chunks in batches for embedding generation with rate limiting
    and progress tracking.
    """

    def __init__(
        self,
        embedder: Embedder,
        batch_size: int = 100,
        rate_limit_pause: float = 0.5,
    ):
        """
        Initialize the batch processor.

        Args:
            embedder: Embedder instance for generating embeddings.
            batch_size: Number of texts to process per batch.
            rate_limit_pause: Pause between batches in seconds.
        """
        self.embedder = embedder
        self.batch_size = batch_size
        self.rate_limit_pause = rate_limit_pause

    def process_chunks(
        self,
        chunks: list[dict[str, Any]],
        progress_callback: Callable | None = None,
    ) -> list[dict[str, Any]]:
        """
        Process chunks in batches with rate limiting.

        Args:
            chunks: List of chunk dictionaries.
            progress_callback: Optional callback for progress updates.

        Returns:
            Chunks with embeddings added.
        """
        total = len(chunks)
        processed = []

        for i in range(0, total, self.batch_size):
            batch = chunks[i : i + self.batch_size]
            batch_num = (i // self.batch_size) + 1
            total_batches = (total + self.batch_size - 1) // self.batch_size

            logger.debug(f"Processing batch {batch_num}/{total_batches}")

            # Generate embeddings for batch
            texts = [chunk.get("content", "") for chunk in batch]

            try:
                embeddings = self.embedder.embed_batch(texts)

                for chunk, embedding in zip(batch, embeddings):
                    chunk["embedding"] = embedding
                    processed.append(chunk)

            except Exception as e:
                logger.error(f"Failed to process batch {batch_num}: {e}")
                # Add chunks without embeddings
                for chunk in batch:
                    chunk["embedding"] = None
                    chunk["embedding_error"] = str(e)
                    processed.append(chunk)

            # Progress callback
            if progress_callback:
                progress = (i + len(batch)) / total
                progress_callback(progress, batch_num, total_batches)

            # Rate limiting pause
            if i + self.batch_size < total:
                time.sleep(self.rate_limit_pause)

        logger.info(f"Completed processing {len(processed)} chunks")
        return processed

    def process_with_retry(
        self,
        chunks: list[dict[str, Any]],
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> list[dict[str, Any]]:
        """
        Process chunks with automatic retry on failure.

        Args:
            chunks: List of chunk dictionaries.
            max_retries: Maximum retry attempts per batch.
            retry_delay: Delay between retries in seconds.

        Returns:
            Chunks with embeddings added.
        """
        total = len(chunks)
        processed = []
        failed_chunks = []

        for i in range(0, total, self.batch_size):
            batch = chunks[i : i + self.batch_size]
            success = False

            for attempt in range(max_retries):
                try:
                    texts = [chunk.get("content", "") for chunk in batch]
                    embeddings = self.embedder.embed_batch(texts)

                    for chunk, embedding in zip(batch, embeddings):
                        chunk["embedding"] = embedding
                        processed.append(chunk)

                    success = True
                    break

                except Exception as e:
                    logger.warning(
                        f"Batch {i // self.batch_size + 1} attempt "
                        f"{attempt + 1} failed: {e}"
                    )
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay * (attempt + 1))

            if not success:
                logger.error(f"Batch starting at index {i} failed after {max_retries} attempts")
                failed_chunks.extend(batch)

            time.sleep(self.rate_limit_pause)

        if failed_chunks:
            logger.warning(f"{len(failed_chunks)} chunks failed to embed")
            for chunk in failed_chunks:
                chunk["embedding"] = None
                chunk["embedding_error"] = "Max retries exceeded"
                processed.append(chunk)

        return processed
