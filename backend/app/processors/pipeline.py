"""Document extraction pipeline — orchestrates PDF parsing, classification,
VIE, table extraction, and image asset management.

Two-phase architecture:
  Phase 1: Extract price tables → build model_no → variants mapping
  Phase 2: Extract door styles / accessories → cross-reference prices
"""

from typing import Dict, List, Optional

from app.core.logging import get_logger
from app.processors.image_manager import ImageAssetManager
from app.processors.page_classifier import PageClassifier
from app.processors.pdf_parser import PDFParser
from app.processors.schemas import (
    ExtractedProduct,
    ExtractionResult,
    ExtractedTextBlock,
    PageType,
    ProductVariant,
)
from app.processors.table_extractor import (
    HeuristicTableExtractor,
    TableExtractor,
    table_to_products,
)
from app.processors.vie_extractor import (
    DashScopeVIEExtractor,
    RuleBasedVIEExtractor,
    VIEExtractor,
)

logger = get_logger(__name__)


class DocumentPipeline:
    """Main pipeline for extracting structured product data from PDF brochures.

    Pipeline stages:
    1. PDF Parsing → pages with images, text, tables
    2. Page Classification → identify page types
    3. Phase 1: Price Table Extraction → build cross-page price map
    4. Phase 2: VIE / Door Style Extraction → with price cross-reference
    5. Image Asset Management → rename, classify, upload images
    6. Result Assembly → final structured output
    """

    def __init__(
        self,
        pdf_parser: Optional[PDFParser] = None,
        classifier: Optional[PageClassifier] = None,
        vie_extractor: Optional[VIEExtractor] = None,
        table_extractor: Optional[TableExtractor] = None,
        image_manager: Optional[ImageAssetManager] = None,
        use_vlm: bool = True,
    ) -> None:
        self.pdf_parser = pdf_parser or PDFParser()
        self.classifier = classifier or PageClassifier()
        self.image_manager = image_manager or ImageAssetManager()

        # VIE: prefer DashScope VLM, fallback to rule-based
        if use_vlm:
            self.vie_extractor = vie_extractor or DashScopeVIEExtractor()
        else:
            self.vie_extractor = vie_extractor or RuleBasedVIEExtractor()

        self.table_extractor = table_extractor or HeuristicTableExtractor()

    def process(self, pdf_path: str) -> ExtractionResult:
        """Process a PDF file through the full two-phase pipeline."""
        logger.info("Starting document pipeline", file=pdf_path)

        # Stage 1: Parse PDF
        pages = self.pdf_parser.parse(pdf_path)

        # Stage 2: Classify pages
        pages = self.classifier.classify_all(pages)

        type_counts = {}
        for p in pages:
            type_counts[p.page_type.value] = type_counts.get(p.page_type.value, 0) + 1
        logger.info("Page classification summary", counts=type_counts)

        # ================================================================
        # Phase 1: Extract price tables → build model_no → variants map
        # ================================================================
        price_map: Dict[str, List[ProductVariant]] = {}
        for page in pages:
            if page.page_type == PageType.PRICE_TABLE:
                tables = self.table_extractor.extract_from_page(page)
                for table in tables:
                    table_products = table_to_products(table)
                    for prod in table_products:
                        if prod.model_no != "UNKNOWN" and prod.variants:
                            if prod.model_no not in price_map:
                                price_map[prod.model_no] = []
                            # Merge variants, avoid duplicates by (color, substrate, thickness)
                            existing_keys = {
                                (v.color_name, v.substrate, v.thickness)
                                for v in price_map[prod.model_no]
                            }
                            for v in prod.variants:
                                key = (v.color_name, v.substrate, v.thickness)
                                if key not in existing_keys:
                                    price_map[prod.model_no].append(v)
                                    existing_keys.add(key)

        logger.info("Price map built", models=len(price_map), total_variants=sum(len(v) for v in price_map.values()))

        # ================================================================
        # Phase 2: Extract products from visual pages, with price cross-ref
        # ================================================================
        all_products: List[ExtractedProduct] = []
        all_text_chunks: List[ExtractedTextBlock] = []

        for page in pages:
            # Extract products from visual content
            # Skip color chart pages for VLM (too many small images, slow)
            if page.page_type in (
                PageType.THERMOFORMING_DOOR,
                PageType.SPECIAL_ACCESSORY,
            ):
                products = self.vie_extractor.extract_from_page(page, price_map=price_map)
                for prod in products:
                    prod.images = self.image_manager.process_images(
                        prod.images,
                        product_family=prod.product_family,
                        model_no=prod.model_no,
                    )
                all_products.extend(products)

            # Also try VIE on price tables (for tables that are image-based)
            if page.page_type == PageType.PRICE_TABLE:
                # If heuristic table extraction found nothing, try VLM
                if not any(t.rows for t in self.table_extractor.extract_from_page(page)):
                    products = self.vie_extractor.extract_from_page(page, price_map=price_map)
                    for prod in products:
                        prod.images = self.image_manager.process_images(
                            prod.images,
                            product_family=prod.product_family,
                            model_no=prod.model_no,
                        )
                    all_products.extend(products)

            # Collect text chunks for knowledge base
            if page.page_type == PageType.PROCESS_DESCRIPTION:
                all_text_chunks.extend(page.text_blocks)

        # ================================================================
        # Stage 5: Deduplicate products by model_no
        # ================================================================
        deduped_products: List[ExtractedProduct] = []
        seen_models: set = set()
        for prod in all_products:
            if prod.model_no in seen_models:
                # Merge variants into existing product
                existing = next(p for p in deduped_products if p.model_no == prod.model_no)
                existing.variants.extend(prod.variants)
                existing.images.extend(prod.images)
                existing.source_pages.extend(prod.source_pages)
            else:
                seen_models.add(prod.model_no)
                deduped_products.append(prod)

        # Sort variants within each product for consistency
        for prod in deduped_products:
            prod.variants = sorted(
                prod.variants,
                key=lambda v: (v.color_name, v.substrate, v.thickness),
            )

        # ================================================================
        # Stage 6: Assemble result
        # ================================================================
        result = ExtractionResult(
            source_file=pdf_path,
            pages=pages,
            products=deduped_products,
            text_chunks=all_text_chunks,
            metadata={
                "total_pages": len(pages),
                "products_extracted": len(deduped_products),
                "text_chunks": len(all_text_chunks),
                "page_types": type_counts,
                "price_map_models": len(price_map),
            },
        )

        logger.info(
            "Pipeline complete",
            file=pdf_path,
            products=len(deduped_products),
            text_chunks=len(all_text_chunks),
            price_models=len(price_map),
        )
        return result
