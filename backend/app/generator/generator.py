"""Generation engine — LLM-powered customer service with function calling.

The LLM acts as a natural客服. When it decides the user needs a price quote,
it calls the get_price_quote tool. The backend executes the query and returns
results, then the LLM formats the final reply naturally.
"""

import json
import re
from typing import Any, Dict, List, Optional

from app.core.database import get_db_context
from app.core.logging import get_logger
from app.generator.schemas import GenerationResult
from app.models import PriceVariant, Product
from app.retrieval.pipeline import RetrievalPipeline
from app.retrieval.schemas import QueryIntent
from app.services.models import llm_service
from app.services.quote_guide import QuoteGuideEngine

logger = get_logger(__name__)


class GenerationEngine:
    """LLM-driven generation with tool calling for price queries."""

    def __init__(
        self,
        retrieval_pipeline: Optional[RetrievalPipeline] = None,
        quote_guide: Optional[QuoteGuideEngine] = None,
    ) -> None:
        self.retrieval = retrieval_pipeline or RetrievalPipeline()
        self.quote_guide = quote_guide or QuoteGuideEngine()
        self._seen_sessions: set = set()
        self._product_cache: Optional[List[Dict[str, Any]]] = None
        # Session conversation history for LLM context memory
        self._session_histories: Dict[str, List[Dict[str, Any]]] = {}

    # ─────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────

    def answer(self, query: str, session_id: Optional[str] = None) -> GenerationResult:
        """Complete flow: extract entities → LLM with tool calling + history → assemble."""
        logger.info("Generation started", query=query, session_id=session_id)

        # 1. First-time greeting (no history yet)
        history = self._session_histories.get(session_id, []) if session_id else []
        if not history and self._is_first_greeting(query, session_id):
            return self._welcome_result(session_id)

        # 2. Retrieve context (entities + semantic results for LLM grounding)
        context = self.retrieval.retrieve(query, session_id=session_id)

        # 3. Build messages: system + history + current user
        system_prompt = self._build_system_prompt()
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": query})

        # 4. Call LLM with price tool
        content, tool_calls = llm_service.chat(
            messages=messages,
            tools=[self._price_tool_schema()],
            max_tokens=2048,
            temperature=0.3,
        )

        # 5. Handle tool calls
        structured_data = None
        if tool_calls:
            for tc in tool_calls:
                if tc.function.name == "get_price_quote":
                    args = json.loads(tc.function.arguments)
                    result = self._execute_price_quote(args)
                    structured_data = self._build_structured_from_tool(result)

                    # Append assistant tool_call to messages
                    messages.append({
                        "role": "assistant",
                        "content": content,
                        "tool_calls": [{
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }],
                    })
                    # Append tool result
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })

            # Call LLM again with tool results
            content, _ = llm_service.chat(
                messages=messages,
                max_tokens=2048,
                temperature=0.3,
            )

        # 6. Save conversation to history
        if session_id:
            # Save user message
            history.append({"role": "user", "content": query})
            # Save assistant reply
            history.append({"role": "assistant", "content": content.strip()})
            # Trim history to last 10 turns (20 messages) to save tokens
            if len(history) > 20:
                history = history[-20:]
            self._session_histories[session_id] = history

        # 7. Fallback: if LLM returns empty, use retrieval context
        if not content.strip():
            content = self._fallback_answer(context)

        return GenerationResult(
            answer_text=content.strip(),
            intent=context.query.intent.value if context.query.intent else "unknown",
            structured_data=structured_data,
            image_urls=[],
            source_chunks=[],
            source_pages=[],
        )

    # ─────────────────────────────────────────────
    # Tool schema
    # ─────────────────────────────────────────────

    def _price_tool_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_price_quote",
                "description": (
                    "查询指定产品的价格。当客户明确询问产品价格、报价、多少钱时调用。"
                    "参数尽可能填写客户已提供的信息，缺少的参数不要编造。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "model_no": {
                            "type": "string",
                            "description": "产品型号，如 MX-A01（必填）",
                        },
                        "color_name": {
                            "type": "string",
                            "description": "颜色名称，如 咖啡灰",
                        },
                        "substrate": {
                            "type": "string",
                            "description": "基材名称，如 颗粒板、多层板",
                        },
                        "thickness": {
                            "type": "integer",
                            "description": "厚度(mm)，如 18、25",
                        },
                        "dimensions": {
                            "type": "string",
                            "description": "尺寸，如 2000mm*50mm，用于计算总价",
                        },
                    },
                    "required": ["model_no"],
                },
            },
        }

    # ─────────────────────────────────────────────
    # Tool execution
    # ─────────────────────────────────────────────

    def _execute_price_quote(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Query DB for price variants matching the tool arguments."""
        from sqlalchemy import select

        model_no = args.get("model_no")
        color_name = args.get("color_name")
        substrate = args.get("substrate")
        thickness = args.get("thickness")
        dimensions = args.get("dimensions")

        with get_db_context() as db:
            product = db.execute(
                select(Product).where(Product.model_no == model_no)
            ).scalar_one_or_none()

            if not product:
                return {"error": f"未找到型号 {model_no}，请确认型号是否正确。"}

            stmt = select(PriceVariant).where(PriceVariant.product_id == product.id)
            if color_name:
                stmt = stmt.where(PriceVariant.color_name == color_name)
            if substrate:
                stmt = stmt.where(PriceVariant.substrate == substrate)
            if thickness:
                stmt = stmt.where(PriceVariant.thickness == thickness)

            variants = db.execute(stmt).scalars().all()

            results = []
            for v in variants:
                item = {
                    "color_name": v.color_name,
                    "color_code": v.color_code,
                    "substrate": v.substrate,
                    "thickness": v.thickness,
                    "unit_price": float(v.unit_price),
                    "unit": v.unit,
                    "is_standard": v.is_standard,
                }
                if dimensions:
                    dim_match = re.search(
                        r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*[*×xX]\s*(\d+(?:\.\d+)?)",
                        dimensions,
                    )
                    if dim_match:
                        length = float(dim_match.group(1))
                        width = float(dim_match.group(2))
                        area = (length * width) / 1_000_000
                        item["area"] = round(area, 4)
                        item["total_price"] = round(float(v.unit_price) * area, 2)
                results.append(item)

            return {
                "model_no": product.model_no,
                "model_name": product.name,
                "family": product.family,
                "description": product.description,
                "image_urls": product.image_urls or [],
                "variants": results,
                "variant_count": len(results),
            }

    # ─────────────────────────────────────────────
    # System prompt & product catalog
    # ─────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        products = self._get_product_overview()
        lines = "\n".join(
            f"- {p['model_no']}: {p['name']}"
            for p in products
        )

        return (
            "你是**奢匠家居定制**的专属客服顾问，名字叫「小奢」。\n\n"
            "【你的风格】\n"
            "- 热情、专业、亲切，像一位经验丰富的家居顾问\n"
            "- 善于介绍产品优点和设计亮点\n"
            "- 用自然语言和客户交流，不要机械回复\n"
            "- 适当使用emoji，让对话更有温度 😊\n\n"
            "【产品型号列表】（仅型号和名称，不含价格）\n"
            f"{lines}\n\n"
            "【报价工具 — 重要】\n"
            "你有一个 get_price_quote 工具可以查询实时价格。\n"
            "⚠️ **绝对禁止自己编造或猜测价格**。所有价格信息必须通过工具查询。\n"
            "⚠️ 当客户问「多少钱」「价格」「报价」「怎么卖」「什么价」时，**必须**调用 get_price_quote 工具。\n"
            "⚠️ 工具参数尽可能填写客户已提供的型号、颜色、基材、厚度、尺寸。\n"
            "⚠️ 如果工具返回多个变体，你据此引导客户选择下一步参数。\n\n"
            "【工作原则】\n"
            "- 如果客户只说型号没问价格 → 先介绍产品亮点和适用场景\n"
            "- 如果客户询价 → **调用工具**，根据结果自然回复\n"
            "- 如果客户提供了尺寸 → 工具会自动计算面积和总价\n"
            "- 如果客户问知识性问题 → 用专业知识自然回答\n"
        )

    def _get_product_overview(self) -> List[Dict[str, Any]]:
        if self._product_cache is not None:
            return self._product_cache

        from sqlalchemy import select
        with get_db_context() as db:
            products = db.execute(select(Product)).scalars().all()
            self._product_cache = [
                {
                    "model_no": p.model_no,
                    "name": p.name or "",
                    "desc": (p.description or "")[:40],
                }
                for p in products
            ]
        return self._product_cache

    # ─────────────────────────────────────────────
    # Greeting
    # ─────────────────────────────────────────────

    def _is_first_greeting(self, query: str, session_id: Optional[str]) -> bool:
        if not session_id or session_id in self._seen_sessions:
            return False
        short_greetings = {"你好", "您好", "hi", "hello", "在吗", "在", "有人吗"}
        return query in short_greetings or len(query.strip()) <= 4

    def _welcome_result(self, session_id: Optional[str]) -> GenerationResult:
        if session_id:
            self._seen_sessions.add(session_id)

        from sqlalchemy import select
        with get_db_context() as db:
            products = db.execute(select(Product)).scalars().all()
            product_lines = []
            for p in products:
                product_lines.append(f"- **{p.model_no}**：{p.name} — {p.description or ''}")

        welcome = (
            "👋 欢迎来到**奢匠家居定制**！我是您的专属顾问小奢。\n\n"
            "我可以帮您：\n"
            "• 🏠 了解各类饰面门板的特点和优势\n"
            "• 💰 查询产品价格并精准计算报价\n"
            "• 📐 根据您的尺寸需求核算总价\n\n"
            "目前产品目录包含以下型号：\n\n"
            f"{'\n'.join(product_lines)}\n\n"
            "您可以随时告诉我感兴趣的型号，我来为您详细介绍或报价～"
        )

        return GenerationResult(
            answer_text=welcome,
            intent="welcome",
            structured_data={"guide_mode": True, "step": "welcome"},
            image_urls=[],
            source_chunks=[],
            source_pages=[],
        )

    # ─────────────────────────────────────────────
    # Structured data for frontend
    # ─────────────────────────────────────────────

    def _build_structured_from_tool(self, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if "error" in result:
            return None
        products = []
        for v in result.get("variants", []):
            products.append({
                "model_no": result.get("model_no"),
                "model_name": result.get("model_name"),
                "family": result.get("family"),
                "color_name": v.get("color_name"),
                "substrate": v.get("substrate"),
                "thickness": v.get("thickness"),
                "unit_price": v.get("unit_price"),
                "unit": v.get("unit"),
                "image_urls": result.get("image_urls", []),
                "area": v.get("area"),
                "total_price": v.get("total_price"),
            })
        return {"products": products}

    # ─────────────────────────────────────────────
    # Fallback
    # ─────────────────────────────────────────────

    def _fallback_answer(self, context) -> str:
        """Generate a direct answer when LLM returns empty."""
        from app.retrieval.schemas import QueryIntent
        intent = context.query.intent
        if intent == QueryIntent.QUERY_PRICE and context.structured_results:
            lines = ["根据产品目录，价格如下："]
            for r in context.structured_results[:3]:
                if r.unit_price:
                    line = (
                        f"- {r.model_no} {r.model_name or ''} "
                        f"({r.color_name} / {r.substrate} / {r.thickness}mm): "
                        f"{r.unit_price:.2f}{r.unit or '元/㎡'}"
                    )
                    if r.area is not None and r.total_price is not None:
                        line += f"，面积{r.area:.4f}㎡，总价{r.total_price:.2f}元"
                    lines.append(line)
            return "\n".join(lines)
        return "抱歉，我暂时无法回答这个问题。请尝试更具体地描述您想查询的产品型号。"
