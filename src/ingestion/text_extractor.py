"""Text extraction from PDF pages."""

import logging
import re
from typing import Any

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


class TextExtractor:
    """Extract and clean text content from PDF pages."""

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the text extractor.

        Args:
            config: Configuration dictionary for extraction settings.
        """
        self.config = config or {}

    def extract_from_page(self, page: fitz.Page) -> str:
        """
        Extract text from a PDF page.

        Args:
            page: PyMuPDF page object.

        Returns:
            Extracted and cleaned text content.
        """
        # Try different extraction methods
        text = self._extract_text_blocks(page)

        if not text.strip():
            # Fallback to simple text extraction
            text = page.get_text("text")

        # Clean and normalize the text
        text = self._clean_text(text)

        return text

    def _extract_text_blocks(self, page: fitz.Page) -> str:
        """
        Extract text using block-based extraction for better layout handling.

        Args:
            page: PyMuPDF page object.

        Returns:
            Extracted text from blocks.
        """
        blocks = page.get_text("blocks")
        text_parts = []

        # Sort blocks by position (top to bottom, left to right)
        sorted_blocks = sorted(blocks, key=lambda b: (b[1], b[0]))

        for block in sorted_blocks:
            if block[6] == 0:  # Text block (not image)
                text_parts.append(block[4])

        return "\n\n".join(text_parts)

    def _clean_text(self, text: str) -> str:
        """
        Clean and normalize extracted text.

        Args:
            text: Raw extracted text.

        Returns:
            Cleaned text.
        """
        # Remove excessive whitespace
        text = re.sub(r"\s+", " ", text)

        # Fix common OCR issues
        text = text.replace("ﬁ", "fi")
        text = text.replace("ﬂ", "fl")
        text = text.replace("ﬀ", "ff")

        # Remove page numbers (common patterns)
        text = re.sub(r"\b\d+\s*/\s*\d+\b", "", text)

        # Normalize unicode
        text = text.strip()

        return text

    def extract_structured(self, page: fitz.Page) -> dict[str, Any]:
        """
        Extract text with structural information.

        Args:
            page: PyMuPDF page object.

        Returns:
            Dictionary with structured text content.
        """
        dict_content = page.get_text("dict")

        result = {
            "blocks": [],
            "fonts": set(),
        }

        for block in dict_content.get("blocks", []):
            if block.get("type") == 0:  # Text block
                block_info = {
                    "bbox": block.get("bbox"),
                    "lines": [],
                }

                for line in block.get("lines", []):
                    line_text = ""
                    for span in line.get("spans", []):
                        line_text += span.get("text", "")
                        result["fonts"].add(span.get("font", ""))

                    block_info["lines"].append(line_text)

                result["blocks"].append(block_info)

        result["fonts"] = list(result["fonts"])
        return result
