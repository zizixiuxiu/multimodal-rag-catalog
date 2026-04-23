"""Tests for data import service."""

from decimal import Decimal

import pytest

from app.core.database import get_db_context
from app.models import ImageVector, PriceVariant, Product, TextChunk
from app.processors.schemas import (
    ExtractedImage,
    ExtractedProduct,
    ExtractedTextBlock,
    ImageType,
    ProductVariant,
)
from app.services.data_import import DataImportService


class TestDataImportService:
    """Test data import into PostgreSQL."""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clean up database after each test."""
        yield
        with get_db_context() as db:
            db.query(ImageVector).delete()
            db.query(PriceVariant).delete()
            db.query(Product).delete()
            db.query(TextChunk).delete()
            db.commit()

    def test_import_single_product(self):
        service = DataImportService()

        product = ExtractedProduct(
            product_family="墙柜一体",
            model_no="MX-A01",
            model_name="平板门型",
            description="测试门型",
            variants=[
                ProductVariant(
                    color_name="咖啡灰",
                    substrate="ENF级实木颗粒板",
                    thickness=18,
                    unit_price=Decimal("318.00"),
                )
            ],
            images=[
                ExtractedImage(
                    image_id="img_001",
                    image_type=ImageType.DOOR_STYLE,
                    local_path="/tmp/test.png",
                    storage_url="minio://test/img_001.png",
                )
            ],
        )

        result = service.import_products([product])
        assert result["MX-A01"] > 0

        # Verify in database
        with get_db_context() as db:
            p = db.query(Product).filter_by(model_no="MX-A01").first()
            assert p is not None
            assert p.family == "墙柜一体"
            assert p.name == "平板门型"
            assert p.text_embedding is not None  # BGE-M3 generated
            assert len(p.text_embedding) == 1024

            # Verify variant
            assert len(p.variants) == 1
            assert p.variants[0].color_name == "咖啡灰"
            assert float(p.variants[0].unit_price) == 318.00

            # Verify image
            assert len(p.image_vectors) == 1
            assert p.image_vectors[0].image_type == "door_style"

    def test_import_product_deduplication(self):
        """Same model_no should not create duplicate products."""
        service = DataImportService()

        product1 = ExtractedProduct(
            product_family="墙柜一体",
            model_no="MX-A02",
            model_name="G型拉手",
            variants=[
                ProductVariant(
                    color_name="咖啡灰",
                    substrate="颗粒板",
                    thickness=18,
                    unit_price=Decimal("318.00"),
                )
            ],
        )

        product2 = ExtractedProduct(
            product_family="墙柜一体",
            model_no="MX-A02",  # Same model
            model_name="G型拉手（更新）",
            variants=[
                ProductVariant(
                    color_name="象牙白",  # Different color
                    substrate="多层板",
                    thickness=18,
                    unit_price=Decimal("368.00"),
                )
            ],
        )

        service.import_products([product1, product2])

        with get_db_context() as db:
            products = db.query(Product).filter_by(model_no="MX-A02").all()
            assert len(products) == 1  # Only one product

            variants = db.query(PriceVariant).filter_by(product_id=products[0].id).all()
            assert len(variants) == 2  # Both variants merged
            colors = {v.color_name for v in variants}
            assert colors == {"咖啡灰", "象牙白"}

    def test_import_variant_deduplication(self):
        """Same (color, substrate, thickness) should not duplicate."""
        service = DataImportService()

        product = ExtractedProduct(
            product_family="PET门板",
            model_no="MX-A03",
            variants=[
                ProductVariant(
                    color_name="咖啡灰",
                    substrate="颗粒板",
                    thickness=18,
                    unit_price=Decimal("318.00"),
                ),
                ProductVariant(
                    color_name="咖啡灰",  # Same color
                    substrate="颗粒板",   # Same substrate
                    thickness=18,         # Same thickness
                    unit_price=Decimal("328.00"),  # Different price
                ),
            ],
        )

        service.import_products([product])

        with get_db_context() as db:
            p = db.query(Product).filter_by(model_no="MX-A03").first()
            assert len(p.variants) == 1  # Only first variant kept

    def test_import_text_chunks(self):
        service = DataImportService()

        chunks = [
            ExtractedTextBlock(text="吸塑门板的厚度规格为18mm和25mm两种。", page_no=5),
            ExtractedTextBlock(text="所有柜身按展开计价，包括衣柜、橱柜。", page_no=4),
        ]

        count = service.import_text_chunks(chunks)
        assert count == 2

        with get_db_context() as db:
            db_chunks = db.query(TextChunk).all()
            assert len(db_chunks) == 2

            # Verify embeddings
            for chunk in db_chunks:
                assert chunk.embedding is not None
                assert len(chunk.embedding) == 1024

    def test_import_text_chunk_deduplication_not_applied(self):
        """Text chunks are not deduplicated — same text can appear on different pages."""
        service = DataImportService()

        chunks = [
            ExtractedTextBlock(text="测试文本", page_no=1),
            ExtractedTextBlock(text="测试文本", page_no=2),
        ]

        count = service.import_text_chunks(chunks)
        assert count == 2

        with get_db_context() as db:
            assert db.query(TextChunk).count() == 2

    def test_full_import_workflow(self):
        """Test importing both products and text chunks together."""
        service = DataImportService()

        products = [
            ExtractedProduct(
                product_family="墙柜一体",
                model_no="MX-A04",
                model_name="G型拉手",
                variants=[
                    ProductVariant(
                        color_name="咖啡灰",
                        substrate="ENF级实木颗粒板",
                        thickness=18,
                        unit_price=Decimal("318.00"),
                    )
                ],
            )
        ]

        chunks = [
            ExtractedTextBlock(text="计价说明：门板按展开面积计算。", page_no=4),
        ]

        stats = service.import_from_extraction_result(products, chunks)
        assert stats["products_imported"] == 1
        assert stats["chunks_imported"] == 1

        with get_db_context() as db:
            assert db.query(Product).count() == 1
            assert db.query(PriceVariant).count() == 1
            assert db.query(TextChunk).count() == 1
