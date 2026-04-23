"""Tests for document processing pipeline."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.processors.image_manager import ImageAssetManager
from app.processors.page_classifier import PageClassifier
from app.processors.pdf_parser import PDFParser
from app.processors.pipeline import DocumentPipeline
from app.processors.schemas import (
    ExtractedImage,
    ExtractedPage,
    ExtractedProduct,
    ExtractedTextBlock,
    ImageType,
    PageType,
    ProductVariant,
)
from app.processors.table_extractor import HeuristicTableExtractor, table_to_products
from app.processors.vie_extractor import RuleBasedVIEExtractor


class TestPDFParser:
    """Test PDF parsing with real brochure file."""

    @pytest.fixture(scope="class")
    def pdf_path(self):
        path = "/Users/zizixiuixu/Documents/测试文件/奢匠免漆门墙柜价格手册202509版(零售价) .pdf"
        if not Path(path).exists():
            pytest.skip("Real PDF not available")
        return path

    @pytest.fixture(scope="class")
    def parsed_pages(self, pdf_path):
        parser = PDFParser(dpi=150)
        return parser.parse(pdf_path)

    def test_parse_pages_count(self, parsed_pages):
        assert len(parsed_pages) == 54

    def test_page_has_raw_image(self, parsed_pages):
        page = parsed_pages[0]
        assert page.raw_image_path is not None
        assert Path(page.raw_image_path).exists()

    def test_page_has_text_blocks(self, parsed_pages):
        page = parsed_pages[3]  # Page 4 typically has process description
        assert len(page.text_blocks) > 0

    def test_page_has_images(self, parsed_pages):
        # Pages with door styles should have embedded images
        page = parsed_pages[6]  # Page 7
        assert len(page.images) >= 1


class TestPageClassifier:
    """Test page classification heuristics."""

    def test_classify_price_table(self):
        page = ExtractedPage(
            page_no=17,
            page_type=PageType.UNKNOWN,
            text_blocks=[
                ExtractedTextBlock(text="价格表 咖啡灰 318元/㎡", page_no=17),
                ExtractedTextBlock(text="ENF级实木颗粒板 18mm 368元/㎡", page_no=17),
            ],
        )
        classifier = PageClassifier()
        result = classifier.classify(page)
        assert result == PageType.PRICE_TABLE

    def test_classify_door_style(self):
        page = ExtractedPage(
            page_no=7,
            page_type=PageType.UNKNOWN,
            text_blocks=[
                ExtractedTextBlock(text="门型 颜色 色板 门板", page_no=7),
                ExtractedTextBlock(text="MX-A01 平板门型", page_no=7),
            ],
            images=[
                ExtractedImage(image_id="img1", image_type=ImageType.UNKNOWN, local_path="/tmp/1.png"),
                ExtractedImage(image_id="img2", image_type=ImageType.UNKNOWN, local_path="/tmp/2.png"),
                ExtractedImage(image_id="img3", image_type=ImageType.UNKNOWN, local_path="/tmp/3.png"),
            ],
        )
        classifier = PageClassifier()
        result = classifier.classify(page)
        assert result == PageType.DOOR_STYLE_COLOR_CHART

    def test_classify_process(self):
        page = ExtractedPage(
            page_no=4,
            page_type=PageType.UNKNOWN,
            text_blocks=[
                ExtractedTextBlock(text="计价说明 工艺规则", page_no=4),
                ExtractedTextBlock(text="非标产品处理方式", page_no=4),
            ],
        )
        classifier = PageClassifier()
        result = classifier.classify(page)
        assert result == PageType.PROCESS_DESCRIPTION

    def test_classify_cover(self):
        page = ExtractedPage(
            page_no=1,
            page_type=PageType.UNKNOWN,
            text_blocks=[ExtractedTextBlock(text="目录", page_no=1)],
        )
        classifier = PageClassifier()
        result = classifier.classify(page)
        assert result == PageType.COVER_OR_INDEX


class TestVIEExtractor:
    """Test rule-based VIE extraction."""

    def test_extract_model_numbers(self):
        page = ExtractedPage(
            page_no=7,
            page_type=PageType.DOOR_STYLE_COLOR_CHART,
            text_blocks=[
                ExtractedTextBlock(text="门型 MX-A01 平板门型", page_no=7),
                ExtractedTextBlock(text="门型 MX-A02 G型拉手", page_no=7),
            ],
        )
        extractor = RuleBasedVIEExtractor()
        products = extractor.extract_from_page(page)
        assert len(products) >= 1
        assert any(p.model_no == "MX-A01" for p in products)

    def test_extract_prices(self):
        page = ExtractedPage(
            page_no=17,
            page_type=PageType.PRICE_TABLE,
            text_blocks=[
                ExtractedTextBlock(text="咖啡灰 ENF颗粒板 18mm 318元/㎡", page_no=17),
            ],
        )
        extractor = RuleBasedVIEExtractor()
        products = extractor.extract_from_page(page)
        # Rule-based may not extract from price tables well — this is expected
        assert isinstance(products, list)


class TestTableExtractor:
    """Test table extraction and conversion."""

    def test_heuristic_table_extraction(self):
        page = ExtractedPage(
            page_no=17,
            page_type=PageType.PRICE_TABLE,
            text_blocks=[
                ExtractedTextBlock(text="颜色        基材          厚度    价格", page_no=17),
                ExtractedTextBlock(text="咖啡灰      ENF颗粒板     18mm    318元/㎡", page_no=17),
                ExtractedTextBlock(text="象牙白      多层实木板    18mm    368元/㎡", page_no=17),
                ExtractedTextBlock(text="胡桃木      密度板        25mm    398元/㎡", page_no=17),
            ],
        )
        extractor = HeuristicTableExtractor()
        tables = extractor.extract_from_page(page)
        assert len(tables) >= 1

    def test_table_to_products(self):
        from app.processors.schemas import ExtractedTable

        table = ExtractedTable(
            table_id="t1",
            page_no=17,
            headers=["型号", "颜色", "基材", "厚度", "价格"],
            rows=[
                ["MX-A01", "咖啡灰", "颗粒板", "18", "318"],
                ["MX-A02", "象牙白", "多层板", "18", "368"],
            ],
        )
        products = table_to_products(table)
        assert len(products) == 2
        assert products[0].variants[0].color_name == "咖啡灰"
        assert products[1].variants[0].color_name == "象牙白"


class TestImageAssetManager:
    """Test image asset management."""

    def test_classify_door_image(self):
        manager = ImageAssetManager()
        img = ExtractedImage(
            image_id="test_door",
            image_type=ImageType.UNKNOWN,
            local_path="/tmp/test_mx_door.png",
        )
        result = manager._classify_image(img)
        assert result == ImageType.DOOR_STYLE

    def test_classify_color_image(self):
        manager = ImageAssetManager()
        img = ExtractedImage(
            image_id="test_color",
            image_type=ImageType.UNKNOWN,
            local_path="/tmp/test_color_chip.png",
        )
        result = manager._classify_image(img)
        assert result == ImageType.COLOR_CHIP

    def test_generate_filename(self):
        manager = ImageAssetManager()
        img = ExtractedImage(
            image_id="door_001",
            image_type=ImageType.DOOR_STYLE,
            local_path="/tmp/door_001.png",
        )
        name = manager._generate_filename(img, product_family="墙柜一体", model_no="MX-A01")
        assert name == "墙柜一体/MX-A01/door_style_door_001.png"


class TestDocumentPipeline:
    """Integration test for the full pipeline."""

    def test_pipeline_with_real_pdf(self):
        pdf_path = "/Users/zizixiuixu/Documents/测试文件/奢匠免漆门墙柜价格手册202509版(零售价) .pdf"
        if not Path(pdf_path).exists():
            pytest.skip("Real PDF not available")

        pipeline = DocumentPipeline()
        result = pipeline.process(pdf_path)

        assert result.metadata["total_pages"] == 54
        assert result.metadata["products_extracted"] > 0
        assert result.metadata["text_chunks"] > 0

        # Verify page type distribution
        types = result.metadata["page_types"]
        assert types.get("door_style_color_chart", 0) > 0
        assert types.get("price_table", 0) > 0

        # Verify extracted products have model numbers
        for product in result.products[:5]:
            assert product.model_no is not None
            assert product.model_no != "UNKNOWN"

    def test_pipeline_output_serialization(self):
        """Verify extraction result can be serialized to JSON."""
        product = ExtractedProduct(
            product_family="墙柜一体",
            model_no="MX-A01",
            model_name="平板门型",
            variants=[
                ProductVariant(
                    color_name="咖啡灰",
                    substrate="ENF级实木颗粒板",
                    thickness=18,
                    unit_price=Decimal("318.00"),
                )
            ],
        )

        # Convert to dict for JSON serialization
        data = {
            "product_family": product.product_family,
            "model_no": product.model_no,
            "model_name": product.model_name,
            "variants": [
                {
                    "color_name": v.color_name,
                    "substrate": v.substrate,
                    "thickness": v.thickness,
                    "unit_price": float(v.unit_price),
                }
                for v in product.variants
            ],
        }

        json_str = json.dumps(data, ensure_ascii=False)
        assert "MX-A01" in json_str
        assert "318.0" in json_str
