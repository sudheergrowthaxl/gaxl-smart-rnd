"""Metadata extraction from PDF documents."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


class MetadataExtractor:
    """Extract metadata from PDF documents."""

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the metadata extractor.

        Args:
            config: Configuration dictionary for extraction settings.
        """
        self.config = config or {}

    def extract(self, doc: fitz.Document, pdf_path: Path) -> dict[str, Any]:
        """
        Extract metadata from a PDF document.

        Args:
            doc: PyMuPDF document object.
            pdf_path: Path to the PDF file.

        Returns:
            Dictionary containing document metadata.
        """
        metadata = {
            "file_name": pdf_path.name,
            "file_path": str(pdf_path.absolute()),
            "file_size_bytes": pdf_path.stat().st_size,
            "page_count": len(doc),
            "extracted_at": datetime.utcnow().isoformat(),
        }

        # Extract PDF metadata
        pdf_metadata = doc.metadata
        if pdf_metadata:
            metadata.update({
                "title": pdf_metadata.get("title", ""),
                "author": pdf_metadata.get("author", ""),
                "subject": pdf_metadata.get("subject", ""),
                "creator": pdf_metadata.get("creator", ""),
                "producer": pdf_metadata.get("producer", ""),
                "creation_date": self._parse_pdf_date(
                    pdf_metadata.get("creationDate", "")
                ),
                "modification_date": self._parse_pdf_date(
                    pdf_metadata.get("modDate", "")
                ),
                "keywords": pdf_metadata.get("keywords", ""),
            })

        # Add document structure info
        metadata["has_toc"] = len(doc.get_toc()) > 0
        metadata["is_encrypted"] = doc.is_encrypted

        # Extract table of contents
        toc = doc.get_toc()
        if toc:
            metadata["table_of_contents"] = [
                {"level": item[0], "title": item[1], "page": item[2]} for item in toc
            ]

        # Infer document type from filename
        metadata["inferred_type"] = self._infer_document_type(pdf_path.name)

        return metadata

    def _parse_pdf_date(self, date_str: str) -> str | None:
        """
        Parse PDF date format to ISO format.

        Args:
            date_str: PDF date string (e.g., "D:20240101120000").

        Returns:
            ISO formatted date string or None.
        """
        if not date_str:
            return None

        try:
            # Remove "D:" prefix if present
            if date_str.startswith("D:"):
                date_str = date_str[2:]

            # Parse basic format: YYYYMMDDHHmmSS
            if len(date_str) >= 14:
                dt = datetime.strptime(date_str[:14], "%Y%m%d%H%M%S")
                return dt.isoformat()
            elif len(date_str) >= 8:
                dt = datetime.strptime(date_str[:8], "%Y%m%d")
                return dt.isoformat()

        except ValueError as e:
            logger.debug(f"Failed to parse PDF date '{date_str}': {e}")

        return None

    def _infer_document_type(self, filename: str) -> str:
        """
        Infer document type from filename.

        Args:
            filename: Name of the PDF file.

        Returns:
            Inferred document type.
        """
        filename_lower = filename.lower()

        type_keywords = {
            "datasheet": ["datasheet", "data sheet", "data_sheet"],
            "catalog": ["catalog", "catalogue"],
            "manual": ["manual", "guide", "instruction"],
            "specification": ["specification", "spec", "technical"],
            "brochure": ["brochure", "flyer"],
        }

        for doc_type, keywords in type_keywords.items():
            for keyword in keywords:
                if keyword in filename_lower:
                    return doc_type

        return "unknown"

    def extract_abb_specific(self, doc: fitz.Document) -> dict[str, Any]:
        """
        Extract ABB-specific metadata from the document.

        Args:
            doc: PyMuPDF document object.

        Returns:
            Dictionary containing ABB-specific metadata.
        """
        abb_metadata = {
            "product_series": None,
            "document_number": None,
            "revision": None,
        }

        # Try to extract from first page text
        if len(doc) > 0:
            first_page_text = doc[0].get_text("text")

            # Look for ABB product patterns
            import re

            # Product series patterns (e.g., A-line, AF, AX)
            series_patterns = [
                r"\b(A[F|X]?\d+)",  # AF26, AX09, etc.
                r"\b(A-Line)\b",
                r"\b(AX)\d+",
            ]

            for pattern in series_patterns:
                match = re.search(pattern, first_page_text)
                if match:
                    abb_metadata["product_series"] = match.group(1)
                    break

            # Document number pattern
            doc_num_match = re.search(
                r"\b(\d{4}[A-Z]{2,3}\d{4,})\b", first_page_text
            )
            if doc_num_match:
                abb_metadata["document_number"] = doc_num_match.group(1)

        return abb_metadata
