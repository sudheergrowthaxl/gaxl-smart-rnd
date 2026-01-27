"""Main PDF processor that orchestrates text, table, and image extraction."""

import logging
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from src.ingestion.text_extractor import TextExtractor
from src.ingestion.table_extractor import TableExtractor
from src.ingestion.image_processor import ImageProcessor
from src.ingestion.metadata_extractor import MetadataExtractor
from src.utils.exceptions import PDFProcessingError

logger = logging.getLogger(__name__)


class PDFProcessor:
    """
    Main PDF processor that coordinates extraction of text, tables, images, and metadata.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the PDF processor.

        Args:
            config: Configuration dictionary for extraction settings.
        """
        self.config = config or {}
        self.text_extractor = TextExtractor(config)
        self.table_extractor = TableExtractor(config)
        self.image_processor = ImageProcessor(config)
        self.metadata_extractor = MetadataExtractor(config)

    def process(self, pdf_path: str | Path) -> dict[str, Any]:
        """
        Process a PDF file and extract all content.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            Dictionary containing extracted content with keys:
                - metadata: Document metadata
                - pages: List of page contents
                - tables: Extracted tables
                - images: Processed images with OCR text

        Raises:
            PDFProcessingError: If PDF processing fails.
        """
        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            raise PDFProcessingError(
                f"PDF file not found: {pdf_path}",
                details={"path": str(pdf_path)},
            )

        logger.info(f"Processing PDF: {pdf_path}")

        try:
            doc = fitz.open(pdf_path)

            result = {
                "metadata": self.metadata_extractor.extract(doc, pdf_path),
                "pages": [],
                "tables": [],
                "images": [],
            }

            for page_num in range(len(doc)):
                logger.debug(f"Processing page {page_num + 1}/{len(doc)}")

                page = doc[page_num]

                # Extract text
                page_text = self.text_extractor.extract_from_page(page)
                result["pages"].append({
                    "page_number": page_num + 1,
                    "text": page_text,
                })

                # Extract tables
                page_tables = self.table_extractor.extract_from_page(
                    pdf_path, page_num
                )
                for table in page_tables:
                    table["page_number"] = page_num + 1
                result["tables"].extend(page_tables)

                # Extract and process images
                page_images = self.image_processor.extract_from_page(page, page_num)
                result["images"].extend(page_images)

            doc.close()

            logger.info(
                f"Completed processing {pdf_path.name}: "
                f"{len(result['pages'])} pages, "
                f"{len(result['tables'])} tables, "
                f"{len(result['images'])} images"
            )

            return result

        except Exception as e:
            raise PDFProcessingError(
                f"Failed to process PDF: {e}",
                details={"path": str(pdf_path), "error": str(e)},
            )

    def process_directory(self, directory: str | Path) -> list[dict[str, Any]]:
        """
        Process all PDF files in a directory.

        Args:
            directory: Path to directory containing PDF files.

        Returns:
            List of processed document dictionaries.
        """
        directory = Path(directory)
        results = []

        pdf_files = list(directory.glob("*.pdf"))
        logger.info(f"Found {len(pdf_files)} PDF files in {directory}")

        for pdf_path in pdf_files:
            try:
                result = self.process(pdf_path)
                results.append(result)
            except PDFProcessingError as e:
                logger.error(f"Failed to process {pdf_path}: {e}")
                continue

        return results
