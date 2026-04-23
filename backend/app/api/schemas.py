"""API request/response schemas (Pydantic models)."""

from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================
# Chat / Query
# ============================================

class ChatRequest(BaseModel):
    """User query request."""

    query: str = Field(..., min_length=1, description="用户问题", examples=["MX-A04 咖啡灰 18mm 多少钱？"])
    session_id: Optional[str] = Field(None, description="会话ID，用于多轮对话")


class ChatResponse(BaseModel):
    """AI answer response."""

    answer: str = Field(..., description="自然语言回答")
    intent: str = Field(..., description="识别的意图")
    structured_data: Optional[Dict[str, Any]] = Field(None, description="结构化数据，供前端渲染表格")
    image_urls: List[str] = Field(default_factory=list, description="相关产品图片URL")
    sources: List[str] = Field(default_factory=list, description="引用来源文本")
    model_no: Optional[str] = Field(None, description="涉及的产品型号")


class ImageSearchRequest(BaseModel):
    """Image-based search request."""

    query: Optional[str] = Field(None, description="可选的文本补充说明")


class SimilarImage(BaseModel):
    """A single similar image result."""

    image_url: str
    image_type: str = ""
    product_id: Optional[int] = None
    similarity: float = 0.0


class ImageSearchResponse(BaseModel):
    """Image search response."""

    query: str = ""
    similar_images: List[SimilarImage] = Field(default_factory=list)
    total: int = 0


# ============================================
# Products
# ============================================

class PriceVariantOut(BaseModel):
    """Price variant output."""

    color_name: str
    color_code: Optional[str] = None
    substrate: str
    thickness: int
    unit_price: float
    unit: str = "元/㎡"
    remark: Optional[str] = None

    class Config:
        from_attributes = True


class ProductOut(BaseModel):
    """Product output."""

    id: int
    family: str
    model_no: str
    name: Optional[str] = None
    description: Optional[str] = None
    image_urls: List[str] = Field(default_factory=list)
    variants: List[PriceVariantOut] = Field(default_factory=list)

    class Config:
        from_attributes = True


class ProductListResponse(BaseModel):
    """Product list response."""

    total: int
    items: List[ProductOut]


# ============================================
# Documents
# ============================================

class DocumentUploadResponse(BaseModel):
    """PDF upload response."""

    message: str
    file_id: str
    pages: int
    products_extracted: int
    text_chunks: int


# ============================================
# Health / Status
# ============================================

# ============================================
# Admin / Management
# ============================================

class VariantCreate(BaseModel):
    """Create a new price variant."""

    color_name: str = Field(..., min_length=1, description="颜色名称，如：咖啡灰")
    color_code: Optional[str] = Field(None, description="色卡编号")
    substrate: str = Field(..., min_length=1, description="基材，如：颗粒板")
    thickness: int = Field(..., ge=1, le=100, description="厚度(mm)，如：18")
    unit_price: float = Field(..., ge=0, description="单价，如：318.00")
    unit: str = Field("元/㎡", description="计价单位")
    spec: Optional[Dict[str, Any]] = Field(None, description="其他规格参数")
    is_standard: bool = Field(True, description="是否标准品")
    remark: Optional[str] = Field(None, description="备注")


class VariantUpdate(BaseModel):
    """Update an existing price variant."""

    color_name: Optional[str] = Field(None, min_length=1)
    color_code: Optional[str] = None
    substrate: Optional[str] = Field(None, min_length=1)
    thickness: Optional[int] = Field(None, ge=1, le=100)
    unit_price: Optional[float] = Field(None, ge=0)
    unit: Optional[str] = None
    spec: Optional[Dict[str, Any]] = None
    is_standard: Optional[bool] = None
    remark: Optional[str] = None


class ProductCreate(BaseModel):
    """Create a new product."""

    family: str = Field(..., min_length=1, description="产品族，如：饰面门板")
    model_no: str = Field(..., min_length=1, description="型号，如：MX-A01")
    name: Optional[str] = Field(None, description="产品名称")
    description: Optional[str] = Field(None, description="产品描述")
    category: Optional[str] = Field(None, description="分类")
    image_urls: List[str] = Field(default_factory=list, description="图片URL列表")


class ProductUpdate(BaseModel):
    """Update an existing product."""

    family: Optional[str] = Field(None, min_length=1)
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    image_urls: Optional[List[str]] = None


class AdminActionResponse(BaseModel):
    """Generic admin action response."""

    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    services: Dict[str, str] = Field(default_factory=dict)
