"""Prompt builder — assembles LLM prompts from retrieval context.

Core principle: LLM NEVER generates prices directly.
Prices come from structured SQL results only.
LLM's job is to "speak human" and present the data naturally.
"""

from typing import List

from app.core.logging import get_logger
from app.retrieval.schemas import (
    QueryIntent,
    RetrievalContext,
    SemanticResult,
    StructuredResult,
)

logger = get_logger(__name__)


SYSTEM_PROMPT_PRICE = """你是奢匠家居定制的专业销售顾问，擅长用清晰、友好的语言为客户解答产品和价格问题。

【重要规则】
1. 价格数据来自结构化数据库，绝对准确，请直接引用。
2. 如果用户询问的价格有多种变体（不同颜色/基材/厚度），请列出所有选项。
3. 如果用户没有指定某些参数（如颜色、基材），请说明"根据您选择的配置，价格为..."并列出常见选项。
4. 当查询包含尺寸（如2000mm×50mm）时，结构化数据中已经计算好了面积(area)和总价(total_price)，请直接引用，不要自行重新计算。
5. 可以补充相关工艺说明，但不要编造信息。
6. 语气专业、亲切，像一位经验丰富的门店导购。
"""

SYSTEM_PROMPT_KNOWLEDGE = """你是奢匠家居定制的技术顾问，擅长解答工艺、安装、计价规则等专业问题。

【重要规则】
1. 仅基于提供的参考资料回答问题，不要编造信息。
2. 如果资料不足以回答，请诚实说明"根据现有资料，我了解到..."，不要猜测。
3. 技术解释要清晰、结构化，必要时分点说明。
4. 如果涉及计价规则，引用原文，不要自行计算。
"""

SYSTEM_PROMPT_COMPARE = """你是奢匠家居定制的产品对比顾问，帮助客户在不同产品/配置之间做出选择。

【重要规则】
1. 基于提供的产品数据进行客观对比。
2. 列出每个选项的关键参数和价格差异。
3. 可以给出建议，但要说明建议依据（如性价比、适用场景）。
4. 不要编造产品没有的特性。
"""


class PromptBuilder:
    """Builds prompts for LLM based on retrieval context."""

    def build(self, context: RetrievalContext) -> List[dict]:
        """Build OpenAI-compatible messages list."""
        intent = context.query.intent

        if intent == QueryIntent.QUERY_PRICE:
            system = SYSTEM_PROMPT_PRICE
        elif intent == QueryIntent.KNOWLEDGE:
            system = SYSTEM_PROMPT_KNOWLEDGE
        elif intent == QueryIntent.COMPARE:
            system = SYSTEM_PROMPT_COMPARE
        else:
            system = SYSTEM_PROMPT_PRICE  # Default

        user_prompt = self._build_user_prompt(context)

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ]

        logger.debug("Prompt built", intent=intent.value, prompt_length=len(user_prompt))
        return messages

    def _build_user_prompt(self, context: RetrievalContext) -> str:
        """Build the user-facing prompt with all retrieval data."""
        parts = []

        # 1. Structured data (products + prices) — PRIMARY for price queries
        if context.structured_results:
            parts.append("【产品信息】")
            parts.append(self._format_structured_results(context.structured_results))
            parts.append("")

        # 2. Semantic knowledge (text chunks) — for knowledge queries or supplementary info
        if context.semantic_results:
            parts.append("【参考资料】")
            for i, result in enumerate(context.semantic_results, 1):
                parts.append(f"{i}. {result.content}")
            parts.append("")

        # 3. Image references
        image_urls = self._collect_image_urls(context)
        if image_urls:
            parts.append("【产品图片】")
            for url in image_urls:
                parts.append(f"- {url}")
            parts.append("")

        # 4. User's original question
        parts.append(f"【用户问题】{context.query.original_query}")

        return "\n".join(parts)

    def _format_structured_results(self, results: List[StructuredResult]) -> str:
        """Format structured results into a clear, LLM-readable table."""
        lines = []

        # Group by product
        products: dict = {}
        for r in results:
            key = r.model_no
            if key not in products:
                products[key] = {
                    "model_no": r.model_no,
                    "model_name": r.model_name,
                    "family": r.family,
                    "variants": [],
                    "image_urls": r.image_urls or [],
                }
            if r.unit_price is not None:
                products[key]["variants"].append({
                    "color": r.color_name,
                    "substrate": r.substrate,
                    "thickness": r.thickness,
                    "price": float(r.unit_price),
                    "unit": r.unit,
                    "area": r.area,
                    "total_price": r.total_price,
                })

        for prod in products.values():
            lines.append(f"型号：{prod['model_no']}")
            if prod["model_name"]:
                lines.append(f"名称：{prod['model_name']}")
            lines.append(f"产品族：{prod['family']}")

            if prod["variants"]:
                lines.append("价格变体：")
                for v in prod["variants"]:
                    # When dimensions provided, show area/total_price as primary price info
                    if v.get("area") is not None and v.get("total_price") is not None:
                        lines.append(
                            f"  - {v['color']} / {v['substrate']} / {v['thickness']}mm"
                        )
                        lines.append(
                            f"    面积：{v['area']:.4f}㎡ | 单价：{v['price']:.2f}{v['unit']} | 【总价：{v['total_price']:.2f}元】"
                        )
                    else:
                        lines.append(
                            f"  - {v['color']} / {v['substrate']} / {v['thickness']}mm = {v['price']:.2f}{v['unit']}"
                        )
            else:
                lines.append("价格：暂无比价信息")

            lines.append("")

        return "\n".join(lines)

    def _collect_image_urls(self, context: RetrievalContext) -> List[str]:
        """Collect unique image URLs from structured results."""
        urls = set()
        for r in context.structured_results:
            for url in (r.image_urls or []):
                if url:
                    urls.add(url)
        return list(urls)
