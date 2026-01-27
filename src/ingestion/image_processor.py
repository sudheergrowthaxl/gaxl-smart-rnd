"""Image extraction and OCR processing from PDF documents."""

import io
import logging
from typing import Any

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Extract and process images from PDF pages with optional OCR."""

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the image processor.

        Args:
            config: Configuration dictionary for processing settings.
        """
        self.config = config or {}
        self.min_width = self.config.get("min_image_width", 100)
        self.min_height = self.config.get("min_image_height", 100)
        self._ocr_available = self._check_ocr_available()

    def _check_ocr_available(self) -> bool:
        """Check if OCR capability is available."""
        try:
            import pytesseract
            from PIL import Image

            return True
        except ImportError:
            logger.warning(
                "pytesseract or PIL not installed. OCR functionality disabled."
            )
            return False

    def extract_from_page(
        self, page: fitz.Page, page_num: int
    ) -> list[dict[str, Any]]:
        """
        Extract images from a PDF page.

        Args:
            page: PyMuPDF page object.
            page_num: Page number (zero-indexed).

        Returns:
            List of extracted images with metadata.
        """
        images = []
        image_list = page.get_images()

        for img_index, img_info in enumerate(image_list):
            try:
                xref = img_info[0]
                base_image = page.parent.extract_image(xref)

                if base_image:
                    width = base_image.get("width", 0)
                    height = base_image.get("height", 0)

                    # Skip small images (likely icons or decorations)
                    if width < self.min_width or height < self.min_height:
                        continue

                    image_data = {
                        "page_number": page_num + 1,
                        "image_index": img_index,
                        "width": width,
                        "height": height,
                        "colorspace": base_image.get("colorspace", ""),
                        "bpc": base_image.get("bpc", 0),
                        "xref": xref,
                    }

                    # Perform OCR if available
                    if self._ocr_available:
                        ocr_text = self._perform_ocr(base_image["image"])
                        image_data["ocr_text"] = ocr_text

                    images.append(image_data)

            except Exception as e:
                logger.warning(
                    f"Failed to extract image {img_index} from page {page_num}: {e}"
                )
                continue

        return images

    def _perform_ocr(self, image_bytes: bytes) -> str:
        """
        Perform OCR on image bytes.

        Args:
            image_bytes: Raw image bytes.

        Returns:
            Extracted text from the image.
        """
        if not self._ocr_available:
            return ""

        try:
            import pytesseract
            from PIL import Image

            image = Image.open(io.BytesIO(image_bytes))
            text = pytesseract.image_to_string(image)
            return text.strip()

        except Exception as e:
            logger.warning(f"OCR failed: {e}")
            return ""

    def extract_diagrams(self, page: fitz.Page) -> list[dict[str, Any]]:
        """
        Extract diagram-like images (larger images likely to be technical diagrams).

        Args:
            page: PyMuPDF page object.

        Returns:
            List of diagram images with metadata.
        """
        diagrams = []
        min_diagram_size = 300  # Minimum dimension for diagrams

        image_list = page.get_images()

        for img_info in image_list:
            try:
                xref = img_info[0]
                base_image = page.parent.extract_image(xref)

                if base_image:
                    width = base_image.get("width", 0)
                    height = base_image.get("height", 0)

                    # Only include larger images likely to be diagrams
                    if width >= min_diagram_size and height >= min_diagram_size:
                        diagram_data = {
                            "width": width,
                            "height": height,
                            "aspect_ratio": width / height if height > 0 else 0,
                            "xref": xref,
                        }

                        if self._ocr_available:
                            diagram_data["ocr_text"] = self._perform_ocr(
                                base_image["image"]
                            )

                        diagrams.append(diagram_data)

            except Exception as e:
                logger.warning(f"Failed to extract diagram: {e}")
                continue

        return diagrams
