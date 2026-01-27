"""Table-specific chunking for structured data."""

import logging
from typing import Any

import tiktoken

logger = logging.getLogger(__name__)


class TableChunker:
    """
    Specialized chunker for table content that preserves structure
    and context.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the table chunker.

        Args:
            config: Configuration dictionary with chunking settings.
        """
        self.config = config or {}
        self.max_rows_per_chunk = self.config.get("max_rows_per_chunk", 20)
        self.encoding = tiktoken.get_encoding("cl100k_base")

    def chunk_table(
        self, table: dict[str, Any], metadata: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """
        Chunk a table into manageable pieces while preserving context.

        Args:
            table: Table dictionary with headers and records.
            metadata: Optional metadata to attach to chunks.

        Returns:
            List of chunk dictionaries.
        """
        metadata = metadata or {}
        chunks = []

        data = table.get("data", {})
        headers = data.get("headers", [])
        records = data.get("records", [])

        if not records:
            return []

        # Create header context that will be included in each chunk
        header_text = " | ".join(headers)
        header_line = "-" * len(header_text)

        # Split records into chunks
        for i in range(0, len(records), self.max_rows_per_chunk):
            chunk_records = records[i : i + self.max_rows_per_chunk]

            # Build chunk content
            rows = []
            for record in chunk_records:
                row_values = [str(record.get(h, "")) for h in headers]
                rows.append(" | ".join(row_values))

            content = f"{header_text}\n{header_line}\n" + "\n".join(rows)

            chunk = {
                "content": content,
                "token_count": len(self.encoding.encode(content)),
                "metadata": {
                    **metadata,
                    "chunk_type": "table",
                    "row_range": f"{i + 1}-{i + len(chunk_records)}",
                    "total_rows": len(records),
                    "headers": headers,
                },
            }
            chunks.append(chunk)

        logger.debug(f"Created {len(chunks)} chunks from table with {len(records)} rows")
        return chunks

    def chunk_specification_table(
        self, table: dict[str, Any], metadata: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """
        Chunk a specification table by grouping related specifications.

        Args:
            table: Specification table with attribute-value pairs.
            metadata: Optional metadata to attach to chunks.

        Returns:
            List of chunk dictionaries.
        """
        metadata = metadata or {}
        chunks = []

        data = table.get("data", {})
        records = data.get("records", [])

        if not records:
            return []

        # Group specifications by category if possible
        grouped = self._group_specifications(records)

        for group_name, specs in grouped.items():
            content_lines = [f"[{group_name}]"]
            for spec in specs:
                # Format as key-value pairs
                for key, value in spec.items():
                    if value:
                        content_lines.append(f"{key}: {value}")
                content_lines.append("")  # Separator

            content = "\n".join(content_lines)

            chunk = {
                "content": content,
                "token_count": len(self.encoding.encode(content)),
                "metadata": {
                    **metadata,
                    "chunk_type": "specification",
                    "specification_group": group_name,
                },
            }
            chunks.append(chunk)

        return chunks

    def _group_specifications(
        self, records: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Group specifications by category.

        Args:
            records: List of specification records.

        Returns:
            Dictionary of grouped specifications.
        """
        # Define common specification categories
        categories = {
            "electrical": [
                "voltage",
                "current",
                "power",
                "frequency",
                "impedance",
            ],
            "mechanical": [
                "dimension",
                "weight",
                "size",
                "mounting",
                "terminal",
            ],
            "environmental": [
                "temperature",
                "humidity",
                "altitude",
                "ip rating",
            ],
            "performance": [
                "durability",
                "life",
                "operations",
                "switching",
            ],
        }

        grouped: dict[str, list] = {"general": []}

        for record in records:
            categorized = False
            record_text = str(record).lower()

            for category, keywords in categories.items():
                if any(kw in record_text for kw in keywords):
                    if category not in grouped:
                        grouped[category] = []
                    grouped[category].append(record)
                    categorized = True
                    break

            if not categorized:
                grouped["general"].append(record)

        # Remove empty categories
        return {k: v for k, v in grouped.items() if v}
