"""Knowledge text chunk model for unstructured content."""

from typing import Optional

from sqlalchemy import Column, Integer, String, Text
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.models.base import Base, TimestampMixin


class TextChunk(Base, TimestampMixin):
    """Text knowledge chunks — for semantic search on process descriptions, rules, etc."""

    __tablename__ = "text_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_doc: Mapped[Optional[str]] = mapped_column(String(100), comment="来源文档文件名")
    page_no: Mapped[Optional[int]] = mapped_column(Integer, comment="页码")
    chunk_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        comment="rule / process / description / pricing_note",
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="文本内容")
    embedding: Mapped[Optional[list]] = mapped_column(Vector(settings.VECTOR_DIMENSION_TEXT), comment="BGE-M3 embedding")

    def __repr__(self) -> str:
        return f"<TextChunk(id={self.id}, source='{self.source_doc}', page={self.page_no})>"
