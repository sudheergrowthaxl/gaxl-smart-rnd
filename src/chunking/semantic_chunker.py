"""Semantic chunking for document content."""

import logging
import re
from typing import Any

import tiktoken

logger = logging.getLogger(__name__)


class SemanticChunker:
    """
    Semantic chunker that splits text into meaningful chunks based on
    content boundaries and token limits.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the semantic chunker.

        Args:
            config: Configuration dictionary with chunking settings.
        """
        self.config = config or {}
        chunking_config = self.config.get("chunking", {})

        self.target_tokens = chunking_config.get("target_tokens", 512)
        self.overlap_tokens = chunking_config.get("overlap_tokens", 50)
        self.min_chunk_size = chunking_config.get("min_chunk_size", 100)
        self.max_chunk_size = chunking_config.get("max_chunk_size", 1000)

        # Initialize tokenizer
        self.encoding = tiktoken.get_encoding("cl100k_base")

    def chunk_document(self, document: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Chunk a processed document into semantic units.

        Args:
            document: Processed document dictionary with pages, tables, etc.

        Returns:
            List of chunk dictionaries with content and metadata.
        """
        chunks = []

        # Chunk text from pages
        for page in document.get("pages", []):
            page_chunks = self.chunk_text(
                page["text"],
                metadata={
                    "page_number": page["page_number"],
                    "source": document.get("metadata", {}).get("file_name", "unknown"),
                    "chunk_type": "text",
                },
            )
            chunks.extend(page_chunks)

        # Add table chunks
        for table in document.get("tables", []):
            table_text = table.get("data", {}).get("as_text", "")
            if table_text:
                chunks.append({
                    "content": table_text,
                    "token_count": len(self.encoding.encode(table_text)),
                    "metadata": {
                        "page_number": table.get("page_number"),
                        "source": document.get("metadata", {}).get(
                            "file_name", "unknown"
                        ),
                        "chunk_type": "table",
                        "table_index": table.get("table_index"),
                    },
                })

        logger.info(f"Created {len(chunks)} chunks from document")
        return chunks

    def chunk_text(
        self, text: str, metadata: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """
        Chunk text into semantic units.

        Args:
            text: Text content to chunk.
            metadata: Optional metadata to attach to chunks.

        Returns:
            List of chunk dictionaries.
        """
        if not text or not text.strip():
            return []

        metadata = metadata or {}
        chunks = []

        # Split into paragraphs first
        paragraphs = self._split_into_paragraphs(text)

        current_chunk = ""
        current_tokens = 0

        for para in paragraphs:
            para_tokens = len(self.encoding.encode(para))

            # If single paragraph exceeds max, split it further
            if para_tokens > self.max_chunk_size:
                # Save current chunk if exists
                if current_chunk:
                    chunks.append(self._create_chunk(current_chunk, metadata))
                    current_chunk = ""
                    current_tokens = 0

                # Split large paragraph
                sub_chunks = self._split_large_text(para)
                for sub_chunk in sub_chunks:
                    chunks.append(self._create_chunk(sub_chunk, metadata))
                continue

            # Check if adding paragraph exceeds target
            if current_tokens + para_tokens > self.target_tokens:
                if current_chunk:
                    chunks.append(self._create_chunk(current_chunk, metadata))

                    # Create overlap from end of current chunk
                    overlap = self._get_overlap(current_chunk)
                    current_chunk = overlap + "\n\n" + para
                    current_tokens = len(self.encoding.encode(current_chunk))
                else:
                    current_chunk = para
                    current_tokens = para_tokens
            else:
                current_chunk = (
                    current_chunk + "\n\n" + para if current_chunk else para
                )
                current_tokens += para_tokens

        # Add final chunk
        if current_chunk and len(self.encoding.encode(current_chunk)) >= self.min_chunk_size:
            chunks.append(self._create_chunk(current_chunk, metadata))

        return chunks

    def _split_into_paragraphs(self, text: str) -> list[str]:
        """Split text into paragraphs."""
        # Split on double newlines or multiple spaces
        paragraphs = re.split(r"\n\s*\n|\n{2,}", text)
        return [p.strip() for p in paragraphs if p.strip()]

    def _split_large_text(self, text: str) -> list[str]:
        """Split large text into smaller chunks by sentences."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks = []
        current = ""
        current_tokens = 0

        for sentence in sentences:
            sent_tokens = len(self.encoding.encode(sentence))

            if current_tokens + sent_tokens > self.target_tokens:
                if current:
                    chunks.append(current.strip())
                current = sentence
                current_tokens = sent_tokens
            else:
                current = current + " " + sentence if current else sentence
                current_tokens += sent_tokens

        if current:
            chunks.append(current.strip())

        return chunks

    def _get_overlap(self, text: str) -> str:
        """Get overlap text from the end of a chunk."""
        tokens = self.encoding.encode(text)
        if len(tokens) <= self.overlap_tokens:
            return text

        overlap_tokens = tokens[-self.overlap_tokens :]
        return self.encoding.decode(overlap_tokens)

    def _create_chunk(
        self, content: str, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a chunk dictionary."""
        return {
            "content": content.strip(),
            "token_count": len(self.encoding.encode(content)),
            "metadata": metadata.copy(),
        }
