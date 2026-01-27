"""Table extraction from PDF documents."""

import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


class TableExtractor:
    """Extract tables from PDF documents using pdfplumber."""

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the table extractor.

        Args:
            config: Configuration dictionary for extraction settings.
        """
        self.config = config or {}

    def extract_from_page(
        self, pdf_path: str | Path, page_num: int
    ) -> list[dict[str, Any]]:
        """
        Extract tables from a specific PDF page.

        Args:
            pdf_path: Path to the PDF file.
            page_num: Zero-indexed page number.

        Returns:
            List of extracted tables with metadata.
        """
        try:
            import pdfplumber
        except ImportError:
            logger.warning("pdfplumber not installed. Table extraction disabled.")
            return []

        tables = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                if page_num >= len(pdf.pages):
                    return []

                page = pdf.pages[page_num]
                extracted_tables = page.extract_tables()

                for idx, table in enumerate(extracted_tables):
                    if table and len(table) > 0:
                        processed_table = self._process_table(table)
                        if processed_table is not None:
                            tables.append({
                                "table_index": idx,
                                "data": processed_table,
                                "raw_data": table,
                                "row_count": len(table),
                                "col_count": len(table[0]) if table else 0,
                            })

        except Exception as e:
            logger.warning(f"Failed to extract tables from page {page_num}: {e}")

        return tables

    def _process_table(self, raw_table: list[list]) -> dict[str, Any] | None:
        """
        Process raw table data into structured format.

        Args:
            raw_table: Raw table data as list of lists.

        Returns:
            Processed table dictionary or None if invalid.
        """
        if not raw_table or len(raw_table) < 2:
            return None

        # Clean cells
        cleaned_table = []
        for row in raw_table:
            cleaned_row = []
            for cell in row:
                if cell is None:
                    cleaned_row.append("")
                else:
                    cleaned_row.append(str(cell).strip())
            cleaned_table.append(cleaned_row)

        # Try to identify headers
        headers = cleaned_table[0]
        data_rows = cleaned_table[1:]

        # Convert to records format
        records = []
        for row in data_rows:
            record = {}
            for i, value in enumerate(row):
                header = headers[i] if i < len(headers) else f"col_{i}"
                record[header] = value
            records.append(record)

        return {
            "headers": headers,
            "records": records,
            "as_text": self._table_to_text(headers, data_rows),
        }

    def _table_to_text(self, headers: list[str], rows: list[list[str]]) -> str:
        """
        Convert table to readable text format.

        Args:
            headers: Table headers.
            rows: Table data rows.

        Returns:
            Text representation of the table.
        """
        lines = []

        # Add header
        if headers:
            lines.append(" | ".join(headers))
            lines.append("-" * len(lines[0]))

        # Add rows
        for row in rows:
            lines.append(" | ".join(row))

        return "\n".join(lines)

    def extract_all(self, pdf_path: str | Path) -> list[dict[str, Any]]:
        """
        Extract all tables from a PDF document.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            List of all extracted tables.
        """
        try:
            import pdfplumber
        except ImportError:
            logger.warning("pdfplumber not installed. Table extraction disabled.")
            return []

        all_tables = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    page_tables = self.extract_from_page(pdf_path, page_num)
                    for table in page_tables:
                        table["page_number"] = page_num + 1
                    all_tables.extend(page_tables)

        except Exception as e:
            logger.error(f"Failed to extract tables from PDF: {e}")

        return all_tables
