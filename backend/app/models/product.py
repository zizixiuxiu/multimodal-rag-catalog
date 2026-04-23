"""Product-related database models."""

from typing import List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DECIMAL,
    ForeignKey,
    Integer,
    String,
    Text,
)
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.models.base import Base, TimestampMixin


class Product(Base, TimestampMixin):
    """Product master table — one product family + model."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    family: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="墙柜一体 / PET门板 / 吸塑门板")
    model_no: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="MX-A01")
    name: Mapped[Optional[str]] = mapped_column(String(100), comment="平板门型")
    description: Mapped[Optional[str]] = mapped_column(Text, comment="门型描述")
    category: Mapped[Optional[str]] = mapped_column(String(50), comment="门板 / 柜体 / 配件")
    image_urls: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), default=list, comment="['minio://door/mx-a01.png']")
    text_embedding: Mapped[Optional[list]] = mapped_column(Vector(settings.VECTOR_DIMENSION_TEXT), comment="BGE-M3 embedding")

    # Relationships
    variants: Mapped[List["PriceVariant"]] = relationship(
        "PriceVariant", back_populates="product", cascade="all, delete-orphan"
    )
    image_vectors: Mapped[List["ImageVector"]] = relationship(
        "ImageVector", back_populates="product", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, family='{self.family}', model_no='{self.model_no}')>"


class PriceVariant(Base, TimestampMixin):
    """Price variant table — exact pricing for each SKU combination."""

    __tablename__ = "price_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    color_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="咖啡灰")
    color_code: Mapped[Optional[str]] = mapped_column(String(20), comment="色卡编号")
    substrate: Mapped[str] = mapped_column(String(50), nullable=False, comment="ENF级实木颗粒板")
    thickness: Mapped[int] = mapped_column(Integer, nullable=False, comment="18 (mm)")
    unit_price: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=False, comment="精确到分")
    unit: Mapped[str] = mapped_column(String(20), default="元/㎡", comment="计价单位")
    spec: Mapped[Optional[dict]] = mapped_column(JSON, default=dict, comment="其他规格参数")
    is_standard: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否标准品")
    remark: Mapped[Optional[str]] = mapped_column(Text, comment="备注（非标说明等）")

    # Relationships
    product: Mapped[Optional["Product"]] = relationship("Product", back_populates="variants")

    def __repr__(self) -> str:
        return (
            f"<PriceVariant(id={self.id}, product_id={self.product_id}, "
            f"color='{self.color_name}', substrate='{self.substrate}', "
            f"thickness={self.thickness}, price={self.unit_price})>"
        )


class ImageVector(Base, TimestampMixin):
    """Image vector table — for image-to-image similarity search."""

    __tablename__ = "image_vectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id", ondelete="CASCADE"))
    image_url: Mapped[str] = mapped_column(Text, nullable=False, comment="minio://...")
    image_type: Mapped[Optional[str]] = mapped_column(String(20), comment="door_style / color_chip / effect")
    clip_embedding: Mapped[Optional[list]] = mapped_column(Vector(settings.VECTOR_DIMENSION_IMAGE), comment="CLIP embedding")

    # Relationships
    product: Mapped[Optional["Product"]] = relationship("Product", back_populates="image_vectors")

    def __repr__(self) -> str:
        return f"<ImageVector(id={self.id}, product_id={self.product_id}, type='{self.image_type}')>"
