"""Table extractor — extracts structured tables from PDF pages.

Interface for PP-Structure / Unstructured / PaddleOCR Table OCR.
Provides a local fallback using text heuristics for development.
"""

import re
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import List, Optional

from app.core.logging import get_logger
from app.processors.schemas import (
    ExtractedPage,
    ExtractedProduct,
    ExtractedTable,
    PageType,
    ProductVariant,
)

logger = get_logger(__name__)


class TableExtractor(ABC):
    """Abstract base class for table extraction."""

    @abstractmethod
    def extract_from_page(self, page: ExtractedPage) -> List[ExtractedTable]:
        """Extract tables from a single page."""
        pass


class HeuristicTableExtractor(TableExtractor):
    """Heuristic table extractor using text layout analysis.

    Fallback for development. Uses whitespace alignment and regex
    to detect tabular data in text blocks.
    """

    def extract_from_page(self, page: ExtractedPage) -> List[ExtractedTable]:
        """Attempt to extract tables from text blocks."""
        if page.page_type != PageType.PRICE_TABLE:
            return []

        tables: List[ExtractedTable] = []
        text = "\n".join(b.text for b in page.text_blocks)

        # Try to find price table patterns
        # Look for lines with multiple numbers and Chinese characters
        lines = text.split("\n")
        table_lines = []

        for line in lines:
            # Heuristic: a price table row typically has:
            # - at least one Chinese character (color/substrate name)
            # - at least one number (price/thickness)
            has_chinese = bool(re.search(r"[\u4e00-\u9fff]", line))
            has_number = bool(re.search(r"\d+", line))
            if has_chinese and has_number and len(line) > 10:
                table_lines.append(line)

        if len(table_lines) >= 3:
            # Try to split into columns using whitespace
            rows = [self._split_columns(line) for line in table_lines]

            # Detect header (first row with different characteristics)
            header = rows[0] if rows else []
            data_rows = rows[1:] if len(rows) > 1 else []

            table = ExtractedTable(
                table_id=f"table_p{page.page_no}",
                page_no=page.page_no,
                headers=header,
                rows=data_rows,
                raw_text=text[:500],
            )
            tables.append(table)

        logger.info(
            "Heuristic table extraction",
            page_no=page.page_no,
            tables_found=len(tables),
        )
        return tables

    def _split_columns(self, line: str) -> List[str]:
        """Split a line into columns using whitespace."""
        # Normalize whitespace and split
        parts = re.split(r"\s{2,}", line.strip())
        return [p.strip() for p in parts if p.strip()]


class PaddleTableExtractor(TableExtractor):
    """Table extractor using PaddleOCR PP-Structure.

    Production implementation. Requires paddlepaddle and paddleocr.
    """

    def __init__(self) -> None:
        self._engine = None

    def _get_engine(self):
        """Lazy-load PaddleOCR table engine."""
        if self._engine is None:
            try:
                from paddleocr import PaddleOCR
                self._engine = PaddleOCR(
                    use_angle_cls=True,
                    lang="ch",
                    show_log=False,
                )
            except ImportError:
                raise RuntimeError(
                    "PaddleOCR not installed. Run: uv pip install paddlepaddle paddleocr"
                )
        return self._engine

    def extract_from_page(self, page: ExtractedPage) -> List[ExtractedTable]:
        """Extract tables using PaddleOCR from page image."""
        if not page.raw_image_path:
            return []

        try:
            engine = self._get_engine()
            result = engine.ocr(page.raw_image_path, cls=True)

            # TODO: PP-Structure specific table extraction
            # For now, return empty list as placeholder
            logger.info("PaddleOCR extraction placeholder", page_no=page.page_no)
            return []

        except Exception as e:
            logger.error("PaddleOCR extraction failed", error=str(e), page_no=page.page_no)
            return []


def table_to_products(table: ExtractedTable) -> List[ExtractedProduct]:
    """Convert an extracted price table into Product objects.

    This is a best-effort conversion that maps table rows to product variants.
    Requires knowledge of the table schema (which column = color, price, etc.)
    """
    products: List[ExtractedProduct] = []

    if not table.rows:
        return products

    # Try to identify columns
    headers = [h.lower() for h in table.headers] if table.headers else []

    color_idx = _find_column_index(headers, ["颜色", "color", "色号"])
    price_idx = _find_column_index(headers, ["价格", "单价", "price", "元"])
    thickness_idx = _find_column_index(headers, ["厚度", "thickness", "mm"])
    substrate_idx = _find_column_index(headers, ["基材", "材质", "substrate", "板"])
    model_idx = _find_column_index(headers, ["型号", "model", "门型", "代号"])

    for row in table.rows:
        if len(row) < 2:
            continue

        model_no = row[model_idx] if model_idx is not None and model_idx < len(row) else "UNKNOWN"
        color = row[color_idx] if color_idx is not None and color_idx < len(row) else "默认"
        substrate = row[substrate_idx] if substrate_idx is not None and substrate_idx < len(row) else "待确认"
        thickness = _parse_int(row[thickness_idx]) if thickness_idx is not None and thickness_idx < len(row) else 18
        price = _parse_price(row[price_idx]) if price_idx is not None and price_idx < len(row) else Decimal("0")

        variant = ProductVariant(
            color_name=color,
            substrate=substrate,
            thickness=thickness,
            unit_price=price,
        )

        # Check if product already exists
        existing = next((p for p in products if p.model_no == model_no), None)
        if existing:
            existing.variants.append(variant)
        else:
            products.append(
                ExtractedProduct(
                    product_family="待分类",
                    model_no=model_no,
                    variants=[variant],
                    source_pages=[table.page_no],
                )
            )

    return products


def _find_column_index(headers: List[str], keywords: List[str]) -> Optional[int]:
    """Find column index by keyword matching."""
    for i, h in enumerate(headers):
        if any(kw in h for kw in keywords):
            return i
    return None


def _parse_int(value: str) -> int:
    """Parse integer from string."""
    digits = re.findall(r"\d+", str(value))
    return int(digits[0]) if digits else 18


def _parse_price(value: str) -> Decimal:
    """Parse price from string."""
    match = re.search(r"(\d+(?:\.\d{1,2})?)", str(value))
    return Decimal(match.group(1)) if match else Decimal("0")
