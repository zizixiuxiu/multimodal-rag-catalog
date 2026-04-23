"""Multi-turn quote guidance — guides users to complete product configuration
step by step before calculating the final price.

Flow:
1. User mentions model → "What color?"
2. User picks color → "What substrate?"
3. User picks substrate → "What thickness?"
4. User picks thickness → "What dimensions? (optional)"
5. All params ready → Calculate total price
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db_context
from app.core.logging import get_logger
from app.models import PriceVariant, Product

logger = get_logger(__name__)

# Human-readable param names
PARAM_LABELS = {
    "model_no": "产品型号",
    "color_name": "颜色",
    "substrate": "基材",
    "thickness": "厚度",
    "dimensions": "尺寸",
}


@dataclass
class QuoteState:
    """Accumulated configuration for a quote session."""

    model_no: Optional[str] = None
    color_name: Optional[str] = None
    substrate: Optional[str] = None
    thickness: Optional[int] = None
    dimensions: Optional[Dict[str, float]] = None

    def update(self, entities: Dict[str, Any]) -> None:
        """Merge new entities into state."""
        if "model_no" in entities:
            self.model_no = entities["model_no"]
        if "color_name" in entities:
            self.color_name = entities["color_name"]
        if "substrate" in entities:
            self.substrate = entities["substrate"]
        if "thickness" in entities:
            self.thickness = entities["thickness"]
        if "dimensions" in entities:
            self.dimensions = entities["dimensions"]

    def missing_params(self) -> List[str]:
        """Return missing params in priority order."""
        missing = []
        if not self.model_no:
            missing.append("model_no")
        if not self.color_name:
            missing.append("color_name")
        if not self.substrate:
            missing.append("substrate")
        if not self.thickness:
            missing.append("thickness")
        return missing

    def is_ready_for_unit_price(self) -> bool:
        """Have enough params to look up unit price."""
        return all([self.model_no, self.color_name, self.substrate, self.thickness])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_no": self.model_no,
            "color_name": self.color_name,
            "substrate": self.substrate,
            "thickness": self.thickness,
            "dimensions": self.dimensions,
        }


class QuoteGuideEngine:
    """Manages multi-turn product configuration sessions."""

    def __init__(self):
        self._states: Dict[str, QuoteState] = {}

    def get_state(self, session_id: Optional[str]) -> QuoteState:
        if not session_id:
            return QuoteState()
        return self._states.get(session_id, QuoteState())

    def update_state(self, session_id: Optional[str], entities: Dict[str, Any]) -> QuoteState:
        if not session_id:
            return QuoteState()
        state = self._states.setdefault(session_id, QuoteState())
        state.update(entities)
        logger.debug("Quote state updated", session_id=session_id, state=state.to_dict())
        return state

    def clear(self, session_id: str) -> None:
        self._states.pop(session_id, None)

    def get_options(self, state: QuoteState, db: Optional[Session] = None) -> Dict[str, List[str]]:
        """Query DB for available options given the current partial config.

        Returns a dict like:
            {"color_name": ["咖啡灰", "象牙白"], "substrate": ["颗粒板", "多层板"]}
        Only includes params that are currently missing.
        """
        should_close = db is None
        if db is None:
            context = get_db_context()
            db = context.__enter__()

        try:
            options: Dict[str, List[str]] = {}
            missing = state.missing_params()
            if not missing:
                return options

            next_param = missing[0]

            # Build base query
            stmt = select(PriceVariant).join(Product)
            if state.model_no:
                stmt = stmt.where(Product.model_no == state.model_no)
            if state.color_name:
                stmt = stmt.where(PriceVariant.color_name == state.color_name)
            if state.substrate:
                stmt = stmt.where(PriceVariant.substrate == state.substrate)
            if state.thickness:
                stmt = stmt.where(PriceVariant.thickness == state.thickness)

            rows = db.execute(stmt).all()

            if next_param == "color_name":
                options["color_name"] = sorted({r[0].color_name for r in rows if r[0].color_name})
            elif next_param == "substrate":
                options["substrate"] = sorted({r[0].substrate for r in rows if r[0].substrate})
            elif next_param == "thickness":
                options["thickness"] = sorted({str(r[0].thickness) for r in rows if r[0].thickness})

            return options

        finally:
            if should_close:
                context.__exit__(None, None, None)

    def build_guide_message(self, state: QuoteState, options: Dict[str, List[str]]) -> str:
        """Generate a friendly guidance message in Chinese."""
        missing = state.missing_params()
        if not missing:
            return ""

        next_param = missing[0]
        param_label = PARAM_LABELS.get(next_param, next_param)

        # Build context prefix
        parts = []
        if state.model_no:
            parts.append(f"{state.model_no}")
        if state.color_name:
            parts.append(f"{state.color_name}")
        if state.substrate:
            parts.append(f"{state.substrate}")

        prefix = f"{' '.join(parts)}" if parts else "该产品"

        # Build options text
        opts = options.get(next_param, [])
        if opts:
            if next_param == "thickness":
                opts_text = "、".join([f"{o}mm" for o in opts])
            else:
                opts_text = "、".join(opts)
            return f"{prefix} 可选的{param_label}有：{opts_text}。请问您需要哪种{param_label}？"
        else:
            return f"请提供{param_label}信息。"

    def build_dimension_prompt(self, state: QuoteState, unit_price: Optional[float] = None, unit: Optional[str] = None) -> str:
        """Prompt for dimensions when all other params are ready."""
        parts = []
        if state.model_no:
            parts.append(state.model_no)
        if state.color_name:
            parts.append(state.color_name)
        if state.substrate:
            parts.append(state.substrate)
        if state.thickness:
            parts.append(f"{state.thickness}mm")

        config = " ".join(parts)
        price_line = f"单价为 **{unit_price:.2f}{unit or '元/㎡'}**" if unit_price else "单价已查询成功"
        return (
            f"已确认配置：{config}，{price_line}。\n\n"
            f"如果您需要计算总价，请提供尺寸（如 2000mm*50mm）；"
            f"如果只需了解单价，可以直接下单。"
        )

    def build_welcome_message(self, db: Optional[Session] = None) -> str:
        """Build welcome message with product overview and param guide."""
        should_close = db is None
        if db is None:
            from app.core.database import get_db_context
            context = get_db_context()
            db = context.__enter__()

        try:
            # Get all products for overview
            products = db.execute(select(Product)).scalars().all()
            product_lines = []
            for p in products:
                product_lines.append(f"- **{p.model_no}**：{p.name} — {p.description or ''}")

            product_overview = "\n".join(product_lines)

            return (
                "👋 欢迎来到**奢匠家居定制**！我是您的专属产品顾问。\n\n"
                "我可以帮您查询各类饰面门板的价格，为您精准计算报价。"
                "目前产品目录包含以下型号：\n\n"
                f"{product_overview}\n\n"
                "---\n\n"
                "📋 **为了给您精准报价，我需要了解以下信息：**\n"
                "1. **产品型号**（如 MX-A01、MX-A02 等）\n"
                "2. **颜色**（如 咖啡灰、象牙白）\n"
                "3. **基材**（如 颗粒板、多层板）\n"
                "4. **厚度**（如 18mm、25mm）\n"
                "5. **尺寸**（如 2000mm*50mm，用于计算总价，可选）\n\n"
                "您可以一次性说完所有参数，也可以一步步告诉我，我会引导您完成选配。"
                "请问您想查询哪个型号？"
            )
        finally:
            if should_close:
                context.__exit__(None, None, None)
