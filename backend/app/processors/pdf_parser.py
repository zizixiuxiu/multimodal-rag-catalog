"""PDF parser using PyMuPDF — splits pages into images, text, and table regions."""

import hashlib
import os
from pathlib import Path
from typing import List, Optional

import fitz  # PyMuPDF
from PIL import Image

from app.core.config import settings
from app.core.logging import get_logger
from app.processors.schemas import (
    ExtractedImage,
    ExtractedPage,
    ExtractedTable,
    ExtractedTextBlock,
    ImageType,
    PageType,
)

logger = get_logger(__name__)


class PDFParser:
    """Parse PDF documents into structured page elements."""

    def __init__(
        self,
        dpi: int = 200,
        extract_images: bool = True,
        extract_text: bool = True,
    ) -> None:
        self.dpi = dpi
        self.extract_images = extract_images
        self.extract_text = extract_text
        self.output_dir = Path(settings.EXTRACTED_DIR)
        self.image_dir = Path(settings.IMAGE_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.image_dir.mkdir(parents=True, exist_ok=True)

    def parse(self, pdf_path: str) -> List[ExtractedPage]:
        """Parse a PDF file and return structured page data."""
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        doc = fitz.open(str(pdf_path))
        pages: List[ExtractedPage] = []

        logger.info("Parsing PDF", file=pdf_path.name, pages=len(doc))

        for page_idx in range(len(doc)):
            page = doc.load_page(page_idx)
            page_no = page_idx + 1

            # Render full page as image
            raw_image_path = self._render_page_image(page, pdf_path.stem, page_no)

            # Extract text blocks
            text_blocks: List[ExtractedTextBlock] = []
            if self.extract_text:
                text_blocks = self._extract_text_blocks(page, page_no)

            # Extract embedded images
            images: List[ExtractedImage] = []
            if self.extract_images:
                images = self._extract_page_images(page, pdf_path.stem, page_no)

            # Detect table regions (basic heuristic, refined by table extractor later)
            tables: List[ExtractedTable] = self._detect_table_regions(page, page_no)

            page_data = ExtractedPage(
                page_no=page_no,
                page_type=PageType.UNKNOWN,  # Will be classified later
                images=images,
                tables=tables,
                text_blocks=text_blocks,
                raw_image_path=raw_image_path,
            )
            pages.append(page_data)
            logger.debug("Parsed page", page_no=page_no, texts=len(text_blocks), images=len(images))

        doc.close()
        logger.info("PDF parsing complete", file=pdf_path.name, total_pages=len(pages))
        return pages

    def _render_page_image(self, page: fitz.Page, doc_stem: str, page_no: int) -> str:
        """Render a PDF page as a high-resolution image."""
        mat = fitz.Matrix(self.dpi / 72, self.dpi / 72)
        pix = page.get_pixmap(matrix=mat)

        img_path = self.image_dir / f"{doc_stem}_page_{page_no:03d}.png"
        pix.save(str(img_path))
        return str(img_path)

    def _extract_text_blocks(self, page: fitz.Page, page_no: int) -> List[ExtractedTextBlock]:
        """Extract text blocks with position and style info."""
        blocks: List[ExtractedTextBlock] = []

        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:  # Skip non-text blocks
                continue

            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text:
                        continue

                    blocks.append(
                        ExtractedTextBlock(
                            text=text,
                            page_no=page_no,
                            bbox=span.get("bbox"),
                            font_size=span.get("size"),
                            is_bold=bool(span.get("flags", 0) & 2**4),
                        )
                    )

        return blocks

    def _extract_page_images(
        self, page: fitz.Page, doc_stem: str, page_no: int
    ) -> List[ExtractedImage]:
        """Extract embedded images from a page with spatial bounding boxes."""
        images: List[ExtractedImage] = []
        img_list = page.get_images(full=True)

        for img_index, img in enumerate(img_list, start=1):
            xref = img[0]
            base_image = page.parent.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]

            # Generate stable ID
            img_hash = hashlib.md5(image_bytes).hexdigest()[:8]
            img_id = f"{doc_stem}_p{page_no:03d}_img{img_index:02d}_{img_hash}"
            img_path = self.image_dir / f"{img_id}.{image_ext}"

            with open(img_path, "wb") as f:
                f.write(image_bytes)

            # Get image bbox (spatial position on page)
            bboxes = page.get_image_rects(xref)
            bbox = tuple(bboxes[0]) if bboxes else None

            images.append(
                ExtractedImage(
                    image_id=img_id,
                    image_type=ImageType.UNKNOWN,
                    local_path=str(img_path),
                    page_no=page_no,
                    bbox=bbox,
                )
            )

        return images

    def _detect_table_regions(self, page: fitz.Page, page_no: int) -> List[ExtractedTable]:
        """Detect potential table regions using drawing commands."""
        tables: List[ExtractedTable] = []

        drawings = page.get_drawings()
        if not drawings:
            return tables

        # Simple heuristic: many horizontal/vertical lines in a region = table
        # This is a placeholder; real table detection uses PP-Structure or similar
        # We create a placeholder table entry for the table extractor to refine
        logger.debug("Drawings detected on page", page_no=page_no, count=len(drawings))

        # TODO: Integrate with PP-Structure or Marker for real table detection
        return tables
