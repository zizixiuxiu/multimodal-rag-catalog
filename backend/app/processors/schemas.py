"""Data schemas for document extraction pipeline."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional


class PageType(Enum):
    """Classification of PDF page types."""

    DOOR_STYLE_COLOR_CHART = "door_style_color_chart"      # 门型/颜色对照表
    PRICE_TABLE = "price_table"                             # 大格价格表
    PROCESS_DESCRIPTION = "process_description"             # 工艺/计价说明
    SPECIAL_ACCESSORY = "special_accessory"                 # 特殊工艺/配件
    THERMOFORMING_DOOR = "thermoforming_door"              # 吸塑门板图集
    COVER_OR_INDEX = "cover_or_index"                       # 封面/目录/封底
    UNKNOWN = "unknown"


class ImageType(Enum):
    """Type of extracted image assets."""

    DOOR_STYLE = "door_style"
    COLOR_CHIP = "color_chip"
    EFFECT = "effect"
    ACCESSORY = "accessory"
    PROCESS_DIAGRAM = "process_diagram"
    UNKNOWN = "unknown"


@dataclass
class ExtractedImage:
    """An image extracted from a PDF page."""

    image_id: str
    image_type: ImageType
    local_path: str
    storage_url: Optional[str] = None
    page_no: int = 0
    bbox: Optional[tuple] = None  # (x0, y0, x1, y1)
    caption: Optional[str] = None


@dataclass
class ExtractedTable:
    """A structured table extracted from a PDF page."""

    table_id: str
    page_no: int
    headers: List[str] = field(default_factory=list)
    rows: List[List[Any]] = field(default_factory=list)
    bbox: Optional[tuple] = None
    raw_text: Optional[str] = None


@dataclass
class ExtractedTextBlock:
    """A text block extracted from a PDF page."""

    text: str
    page_no: int
    bbox: Optional[tuple] = None
    font_size: Optional[float] = None
    is_bold: bool = False


@dataclass
class ExtractedPage:
    """Complete extraction result for a single PDF page."""

    page_no: int
    page_type: PageType
    images: List[ExtractedImage] = field(default_factory=list)
    tables: List[ExtractedTable] = field(default_factory=list)
    text_blocks: List[ExtractedTextBlock] = field(default_factory=list)
    raw_image_path: Optional[str] = None  # Full page rendered as image


@dataclass
class ProductVariant:
    """A single product variant with pricing."""

    color_name: str
    substrate: str
    thickness: int
    unit_price: Decimal
    color_code: Optional[str] = None
    unit: str = "元/㎡"
    spec: Dict[str, Any] = field(default_factory=dict)
    is_standard: bool = True
    remark: Optional[str] = None


@dataclass
class ExtractedProduct:
    """Structured product data — matches PRD JSON Schema."""

    product_family: str
    model_no: str
    model_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    images: List[ExtractedImage] = field(default_factory=list)
    variants: List[ProductVariant] = field(default_factory=list)
    source_pages: List[int] = field(default_factory=list)


@dataclass
class ExtractionResult:
    """Final output of the document extraction pipeline."""

    source_file: str
    pages: List[ExtractedPage] = field(default_factory=list)
    products: List[ExtractedProduct] = field(default_factory=list)
    text_chunks: List[ExtractedTextBlock] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
