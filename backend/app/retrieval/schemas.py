"""Retrieval layer schemas — data structures for query understanding and search results."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from app.processors.schemas import ExtractedImage


class QueryIntent(Enum):
    """User query intent types."""

    QUERY_PRICE = "query_price"           # 查价
    KNOWLEDGE = "knowledge"               # 工艺/知识问答
    IMAGE_SEARCH = "image_search"         # 以图搜图
    COMPARE = "compare"                   # 产品对比
    LIST_PRODUCTS = "list_products"       # 列产品
    UNKNOWN = "unknown"


@dataclass
class ParsedQuery:
    """Output of query understanding layer."""

    intent: QueryIntent
    original_query: str
    entities: Dict[str, Any] = field(default_factory=dict)
    # entities may contain: model_no, color_name, substrate, thickness, etc.

    sql_filters: Dict[str, Any] = field(default_factory=dict)
    # For structured query: {table, conditions}

    vector_query: str = ""
    # Normalized text for semantic search

    def __post_init__(self):
        if not self.vector_query:
            self.vector_query = self.original_query


@dataclass
class StructuredResult:
    """Result from structured SQL query."""

    product_id: int
    model_no: str
    model_name: Optional[str]
    family: str
    color_name: Optional[str]
    substrate: Optional[str]
    thickness: Optional[int]
    unit_price: Optional[Decimal]
    unit: Optional[str]
    image_urls: List[str] = field(default_factory=list)
    source: str = "structured"
    # Computed when dimensions are provided in the query
    area: Optional[float] = None            # in ㎡
    total_price: Optional[float] = None     # unit_price * area


@dataclass
class SemanticResult:
    """Result from text vector search."""

    chunk_id: int
    content: str
    source_doc: Optional[str]
    page_no: Optional[int]
    distance: float
    source: str = "semantic"


@dataclass
class ImageResult:
    """Result from image vector search."""

    image_id: int
    image_url: str
    image_type: str
    product_id: Optional[int]
    distance: float
    source: str = "image"


@dataclass
class RetrievalContext:
    """Assembled context for generation layer."""

    query: ParsedQuery
    structured_results: List[StructuredResult] = field(default_factory=list)
    semantic_results: List[SemanticResult] = field(default_factory=list)
    image_results: List[ImageResult] = field(default_factory=list)

    def has_price_data(self) -> bool:
        return any(r.unit_price is not None for r in self.structured_results)

    def get_primary_product(self) -> Optional[StructuredResult]:
        if self.structured_results:
            return self.structured_results[0]
        return None
