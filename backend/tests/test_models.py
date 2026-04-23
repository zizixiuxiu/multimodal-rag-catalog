"""Tests for database models and storage service."""

import pytest
from decimal import Decimal

from app.core.database import get_db_context
from app.models import Product, PriceVariant, ImageVector, TextChunk
from app.services.storage import storage_service, LocalStorage


class TestStorageService:
    """Test storage service (local filesystem fallback)."""

    def test_storage_type(self):
        assert isinstance(storage_service, LocalStorage)

    def test_upload_and_get(self):
        url = storage_service.upload_file("test/hello.txt", b"Hello World")
        assert url.startswith("file://")

        data = storage_service.get_file("test/hello.txt")
        assert data == b"Hello World"

        storage_service.delete_file("test/hello.txt")
        assert storage_service.get_file("test/hello.txt") is None


class TestProductModel:
    """Test Product and PriceVariant CRUD operations."""

    @pytest.fixture(scope="function")
    def db(self):
        with get_db_context() as session:
            yield session

    def test_create_product(self, db):
        product = Product(
            family="墙柜一体",
            model_no="TEST-MX-001",
            name="测试门型",
            description="用于单元测试的门型",
        )
        db.add(product)
        db.commit()
        db.refresh(product)

        assert product.id is not None
        assert product.family == "墙柜一体"
        assert product.model_no == "TEST-MX-001"

        # Cleanup
        db.delete(product)
        db.commit()

    def test_create_price_variant(self, db):
        product = Product(
            family="PET门板",
            model_no="TEST-PET-001",
            name="PET测试门型",
        )
        db.add(product)
        db.commit()
        db.refresh(product)

        variant = PriceVariant(
            product_id=product.id,
            color_name="咖啡灰",
            substrate="ENF级实木颗粒板",
            thickness=18,
            unit_price=Decimal("318.00"),
        )
        db.add(variant)
        db.commit()
        db.refresh(variant)

        assert variant.id is not None
        assert variant.color_name == "咖啡灰"
        assert variant.thickness == 18
        assert float(variant.unit_price) == 318.00

        # Verify relationship
        queried = db.query(Product).filter_by(id=product.id).first()
        assert len(queried.variants) == 1
        assert queried.variants[0].color_name == "咖啡灰"

        # Cleanup
        db.delete(product)
        db.commit()

    def test_exact_price_query(self, db):
        """Test structured price query — core requirement."""
        product = Product(
            family="墙柜一体",
            model_no="MX-A04",
            name="G型拉手门型",
        )
        db.add(product)
        db.commit()
        db.refresh(product)

        variant = PriceVariant(
            product_id=product.id,
            color_name="咖啡灰",
            substrate="ENF级实木颗粒板",
            thickness=18,
            unit_price=Decimal("318.00"),
            unit="元/㎡",
        )
        db.add(variant)
        db.commit()

        # Simulate structured query
        result = (
            db.query(Product, PriceVariant)
            .join(PriceVariant)
            .filter(Product.model_no == "MX-A04")
            .filter(PriceVariant.color_name == "咖啡灰")
            .filter(PriceVariant.thickness == 18)
            .first()
        )

        assert result is not None
        assert result.Product.model_no == "MX-A04"
        assert result.PriceVariant.unit_price == Decimal("318.00")

        # Cleanup
        db.delete(product)
        db.commit()


class TestTextChunkModel:
    """Test TextChunk model."""

    @pytest.fixture(scope="function")
    def db(self):
        with get_db_context() as session:
            yield session

    def test_create_text_chunk(self, db):
        chunk = TextChunk(
            source_doc="test.pdf",
            page_no=5,
            chunk_type="process",
            content="吸塑门板的厚度规格为18mm和25mm两种。",
        )
        db.add(chunk)
        db.commit()
        db.refresh(chunk)

        assert chunk.id is not None
        assert chunk.source_doc == "test.pdf"
        assert "18mm" in chunk.content

        # Cleanup
        db.delete(chunk)
        db.commit()
