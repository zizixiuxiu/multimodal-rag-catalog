"""Pydantic schemas for price quoting flow."""

from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class QuoteStep(str, Enum):
    """Multi-turn quote guidance steps."""

    ROOM = "room"           # 选择房间
    AREA = "area"           # 确认面积
    COMPONENT = "component" # 选择组件类型
    COLOR = "color"         # 选择颜色
    SUBSTRATE = "substrate" # 选择基材
    THICKNESS = "thickness" # 选择厚度
    DIMENSIONS = "dimensions"  # 确认尺寸
    COMPLETE = "complete"   # 报价完成


class PriceQuoteParams(BaseModel):
    """Input parameters for get_price_quote tool — what the LLM extracts from user query."""

    component_type: Optional[str] = Field(
        default=None,
        description="组件类型：柜身、门板、护墙、吸塑柜门、见光板、抽面",
    )
    color_name: Optional[str] = Field(
        default=None,
        description="颜色名称，如 咖啡灰、雪山白",
    )
    substrate: Optional[str] = Field(
        default=None,
        description="基材名称，如 ENF级实木颗粒板、欧松板、18mm中纤板、21mm中纤板、25mm中纤板",
    )
    thickness: Optional[int] = Field(
        default=None,
        description="厚度(mm)，如 9、18、25、36",
    )
    model_no: Optional[str] = Field(
        default=None,
        description="门型型号，如 MX-A01（仅门板询价时需要）",
    )
    dimensions: Optional[str] = Field(
        default=None,
        description="尺寸，如 2000mm*500mm 或 宽2000高500",
    )

    @field_validator("dimensions", mode="before")
    @classmethod
    def _normalize_dimensions(cls, v):
        if isinstance(v, dict) and "length" in v and "width" in v:
            return f"{v['length']}*{v['width']}"
        return v
    area: Optional[float] = Field(
        default=None,
        description="面积(㎡)，用户直接提供时",
    )
    room: Optional[str] = Field(
        default=None,
        description="房间，如 客厅、卧室、厨房",
    )

    @field_validator("component_type")
    @classmethod
    def normalize_component(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        mapping = {
            "柜身": "柜身",
            "柜体": "柜身",
            "body": "柜身",
            "cabinet": "柜身",
            "门板": "门板",
            "门": "门板",
            "door": "门板",
            "护墙": "护墙",
            "墙板": "护墙",
            "wall": "护墙",
            "吸塑柜门": "吸塑柜门",
            "吸塑门": "吸塑柜门",
            "包覆门": "吸塑柜门",
            "铝框玻璃门": "铝框玻璃门",
            "铝框门": "铝框玻璃门",
            "玻璃门": "铝框玻璃门",
            "铝框玻璃": "铝框玻璃门",
            "皮革门": "皮革门",
            "皮革门板": "皮革门",
            "皮门": "皮革门",
            "免漆套装门": "免漆套装门",
            "套装门": "免漆套装门",
            "室内门": "免漆套装门",
            "房门": "免漆套装门",
            "卧室门": "免漆套装门",
            "见光板": "见光板",
            "抽面": "抽面",
            "抽屉": "抽面",
        }
        return mapping.get(v.strip(), v.strip())


class PriceVariantItem(BaseModel):
    """A single price variant returned from DB."""

    color_name: str
    color_code: Optional[str] = None
    substrate: str
    thickness: int
    component_type: str
    unit_price: float
    unit: str = "元/㎡"
    min_charge_area: Optional[float] = None
    applicable_models: Optional[List[str]] = None
    remark: Optional[str] = None
    is_standard: bool = True


class PricingRule(BaseModel):
    """A pricing rule retrieved from knowledge base."""

    rule_type: str  # min_area / extra_fee / tech_spec / warning
    description: str
    condition: Optional[str] = None
    amount: Optional[float] = None


class PriceQuoteResult(BaseModel):
    """Complete result of a price quote — structured data for frontend."""

    product_id: Optional[int] = None
    model_no: Optional[str] = None
    model_name: Optional[str] = None
    family: Optional[str] = None

    # User selections
    component_type: Optional[str] = None
    color_name: Optional[str] = None
    substrate: Optional[str] = None
    thickness: Optional[int] = None
    room: Optional[str] = None

    # Calculated prices
    unit_price: Optional[float] = None
    unit: str = "元/㎡"
    area: Optional[float] = None
    effective_area: Optional[float] = Field(
        default=None,
        description="应用最低计价规则后的有效面积",
    )
    total_price: Optional[float] = None

    # Rules & warnings
    rules_applied: List[PricingRule] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    extra_fees: List[Dict[str, Any]] = Field(default_factory=list)

    # Next step guidance
    next_step: Optional[QuoteStep] = None
    missing_params: List[str] = Field(default_factory=list)
    available_options: Optional[Dict[str, List[str]]] = None

    # Source
    image_urls: List[str] = Field(default_factory=list)
    remark: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()
