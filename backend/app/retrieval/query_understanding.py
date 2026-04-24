"""Query Understanding — intent recognition + entity extraction.

Provides both rule-based (fast, zero-cost) and LLM-based (accurate) implementations.
"""

import re
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.retrieval.query_rewriter import QueryRewriter
from app.retrieval.schemas import ParsedQuery, QueryIntent
from app.services.models import llm_service

logger = get_logger(__name__)


class QueryUnderstandingEngine:
    """Hybrid query understanding: rules + LLM fallback."""

    # Intent keywords
    PRICE_KEYWORDS = ["多少钱", "价格", "报价", "单价", "怎么卖", "什么价", "元", "费用"]
    KNOWLEDGE_KEYWORDS = ["工艺", "怎么做", "规则", "说明", "注意", "要求", "标准", "规范", "可以", "支持"]
    COMPARE_KEYWORDS = ["对比", "区别", "哪个好", "差别", "不一样", "vs", "versus"]
    LIST_KEYWORDS = ["有哪些", "列表", "全部", "所有", "都有什么", "有什么"]

    # Base model patterns (fallback when DB is empty)
    MODEL_PATTERN = re.compile(
        r"\b(MX-[A-Z]\d{2,3}[A-Z]?|WLS-\d{2,3}|LM-[A-Z]\d{2,3}-\d{2,3}|"
        r"[A-Z]{2,3}-[A-Z]{2,3}-\d{2,3}[A-Z]?|[A-Z]{2}-[A-Z]\d{2,3}|"
        r"[A-Z]{2}\d{4}[A-Z]?-\d{2,3}[A-Z]?|[A-Z]{3}-\d{3,4}|"
        r"[A-Z]{2}\d{2,4}[A-Z]?)\b",
        re.IGNORECASE,
    )
    # Thickness: must not be part of a larger number, reasonable range 5-100
    # Use (?<!\d) and (?!\d) instead of \b because \b treats CJK chars as word chars in Unicode mode
    THICKNESS_PATTERN = re.compile(r"(?<!\d)([1-9]\d{1,2})\s*(?:mm|毫米|厘)(?!\d)")
    # Dimensions: e.g. 2000mm*50mm, 2m*0.5m, 2000*50, 500mm乘以2500mm
    SIZE_PATTERN = re.compile(
        r"(\d+(?:\.\d+)?)\s*(?:mm|cm|m|厘米|米|毫米)?\s*(?:[\*×xX]|乘以)\s*(\d+(?:\.\d+)?)\s*(?:mm|cm|m|厘米|米|毫米)?"
    )
    PRICE_PATTERN = re.compile(r"(\d{3,4})\s*元")
    # Area: e.g. 2.5平米, 2.5平方米, 2.5㎡
    AREA_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(?:平米|平方米|㎡)")

    # Common colors in furniture industry
    # Known component types (whitelist — canonical names matching DB)
    COMPONENT_TYPE_KEYWORDS = [
        "门板", "柜身", "护墙", "背板", "见光板", "收口条", "同色封边条",
    ]
    # Aliases that map to canonical component types
    COMPONENT_TYPE_ALIASES = {
        "柜身": ["柜体", "柜子", "衣柜", "橱柜"],
        "门板": ["柜门"],
    }

    COLOR_KEYWORDS = [
        "咖啡灰", "象牙白", "纯黑", "胡桃木", "橡木", "樱桃木",
        "白", "黑", "灰", "红", "黄", "蓝", "绿", "木色", "原木",
    ]

    # Common substrates (longer first for greedy matching)
    SUBSTRATE_KEYWORDS = [
        "ENF级实木颗粒板（负氧离子抗菌因子）",
        "ENF级实木颗粒板", "E0级实木颗粒板",
        "实木颗粒板", "颗粒板",
        "复合多层板", "多层实木板", "多层板",
        "密度板", "中纤板", "mdf",
        "ENF级欧松板（负氧离子抗菌因子）", "ENF级欧松板（同步木纹）",
        "ENF级欧松板", "欧松板", "OSB",
        "匠芯实木板", "橡胶木板", "实木板", "原木板",
    ]

    def __init__(self):
        self.rewriter = QueryRewriter()
        self._db_model_pattern: Optional[re.Pattern] = None
        self._db_color_keywords: List[str] = []
        self._load_model_pattern_from_db()
        self._load_color_keywords_from_db()

    def _load_model_pattern_from_db(self) -> None:
        """Build precise model pattern from database."""
        try:
            from app.core.database import engine
            from sqlalchemy import text
            with engine.connect() as conn:
                rows = conn.execute(text("SELECT model_no FROM products")).fetchall()
                model_nos = [r[0] for r in rows if r[0]]
            if model_nos:
                # Sort by length descending to match longer ones first
                model_nos = sorted(model_nos, key=len, reverse=True)
                escaped = [re.escape(m) for m in model_nos]
                pattern = r"\b(" + "|".join(escaped) + r")\b"
                self._db_model_pattern = re.compile(pattern, re.IGNORECASE)
        except Exception as e:
            logger.warning("Failed to load model pattern from DB", error=str(e))

    def _load_color_keywords_from_db(self) -> None:
        """Load all color names from price_variants for accurate extraction."""
        try:
            from app.core.database import engine
            from sqlalchemy import text
            with engine.connect() as conn:
                rows = conn.execute(text("SELECT DISTINCT color_name FROM price_variants WHERE color_name IS NOT NULL")).fetchall()
                colors = [r[0] for r in rows if r[0]]
            if colors:
                # Sort by length descending so longer names match first
                # (e.g. █咖啡灰 matches before 咖啡灰)
                self._db_color_keywords = sorted(colors, key=len, reverse=True)
        except Exception as e:
            logger.warning("Failed to load color keywords from DB", error=str(e))

    def _get_model_pattern(self) -> re.Pattern:
        """Return DB-backed pattern if available, else fallback."""
        return self._db_model_pattern or self.MODEL_PATTERN

    def parse(self, query: str, session_id: Optional[str] = None, use_llm: bool = True) -> ParsedQuery:
        """Parse user query into structured intent and entities.

        By default uses LLM for intent recognition (natural language understanding),
        with rule-based entity extraction for accuracy.

        Args:
            query: Raw user query
            session_id: Session ID for multi-turn context enrichment
            use_llm: Whether to use LLM for intent recognition (default True)
        """
        original = query.strip()

        # Step 1: Rewrite query (spell correction, synonyms, context)
        rewritten = self.rewriter.rewrite(original, session_id=session_id)

        # Step 2: Extract entities with rules (fast, accurate)
        entities = self._extract_entities(rewritten)

        # Step 3: Intent recognition with LLM (understands natural conversation)
        if use_llm:
            parsed = self._parse_with_llm(rewritten, entities=entities, original_query=original)
        else:
            parsed = self._parse_with_rules(rewritten, entities=entities, original_query=original)

        # Preserve original query for reference
        parsed.original_query = original
        return parsed

    def _parse_with_rules(self, query: str, entities: Dict[str, Any], original_query: str = "") -> ParsedQuery:
        """Rule-based parsing fallback (conservative intent detection)."""
        intent = self._detect_intent(query)

        sql_filters = {}
        if intent == QueryIntent.QUERY_PRICE:
            sql_filters = {"table": "price_variants", "conditions": {}}
            if "model_no" in entities:
                sql_filters["conditions"]["model_no"] = entities["model_no"]
            if "color_name" in entities:
                sql_filters["conditions"]["color_name"] = entities["color_name"]
            if "thickness" in entities:
                sql_filters["conditions"]["thickness"] = entities["thickness"]
            if "substrate" in entities:
                sql_filters["conditions"]["substrate"] = entities["substrate"]

        vector_query = query
        if intent == QueryIntent.QUERY_PRICE:
            vector_query = f"{entities.get('model_no', '')} {entities.get('color_name', '')} {query}"

        return ParsedQuery(
            intent=intent,
            original_query=original_query or query,
            entities=entities,
            sql_filters=sql_filters,
            vector_query=vector_query.strip(),
        )

    def _parse_with_llm(self, query: str, entities: Dict[str, Any], original_query: str = "") -> ParsedQuery:
        """LLM-based intent recognition — understands natural conversation like a human客服.

        Key principle: be conservative with QUERY_PRICE. Most user messages are casual
        product inquiries ("这个产品怎么样", "有图片吗"). Only trigger price mode when
        the user clearly expresses purchase/quote intent.
        """
        # Build entity hints from rule extraction (helps LLM focus on intent, not entities)
        entity_hints = []
        if "model_no" in entities:
            entity_hints.append(f'型号：{entities["model_no"]}')
        if "color_name" in entities:
            entity_hints.append(f'颜色：{entities["color_name"]}')
        if "substrate" in entities:
            entity_hints.append(f'基材：{entities["substrate"]}')
        if "thickness" in entities:
            entity_hints.append(f'厚度：{entities["thickness"]}mm')
        if "dimensions" in entities:
            d = entities["dimensions"]
            entity_hints.append(f'尺寸：{d["length"]}*{d["width"]}')

        entity_section = "\n".join(entity_hints) if entity_hints else "（未提取到明确参数）"

        prompt = f"""你是一位经验丰富的家居定制行业客服主管。请判断以下客户消息的真实意图。

【客户消息】"{query}"

【已识别的参数】
{entity_section}

【判断规则】非常重要，请严格遵守：

1. **query_price（询价）**：客户**明确问价格、报价、购买、下单**。以下情况**必须**判为query_price：
   - 包含"多少钱"、"价格"、"报价"、"怎么卖"、"什么价"、"费用"
   - 包含"买"、"下单"、"订购"、"采购"、"定一套"
   - 例如："MX-A01多少钱"、"报个价"、"我想买MX-A01"、"这个门怎么卖"
   ⚠️ 只要客户问了价格相关的问题，**必须**选query_price，不要犹豫。

2. **knowledge（知识咨询）**：客户想了解产品信息、工艺、特点、区别等，**但没有问价格**。例如：
   - "MX-A01怎么样"、"有什么特点"、"和A02有什么区别"
   - "颗粒板和多层板哪个好"、"18mm够吗"
   - "有图片吗"、"介绍一下这款产品"

3. **list_products（列表）**：客户想看全部产品列表或某个系列的所有产品

4. **compare（对比）**：客户明确对比两款或多款产品

5. **unknown（其他）**：闲聊、打招呼、或者表达不明确的需求。例如"你好"、"在吗"、"有人吗"。

【输出格式】只返回JSON，不要解释：
{{"intent": "query_price|knowledge|list_products|compare|unknown"}}
"""

        try:
            response, _ = llm_service.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=256,
                temperature=0.1,
                json_mode=True,
            )
            import json

            data = json.loads(response)
            intent_str = data.get("intent", "unknown")
            intent = QueryIntent(intent_str) if intent_str in [e.value for e in QueryIntent] else QueryIntent.UNKNOWN

            # Guard: override LLM intent for obvious price signals
            # LLM is sometimes too conservative; we enforce clear user intent
            obvious_price = any(kw in query for kw in ["多少钱", "价格", "报价", "怎么卖", "什么价", "费用"])
            obvious_buy = any(kw in query for kw in ["买", "下单", "订购", "采购", "定"])
            if obvious_price or obvious_buy:
                intent = QueryIntent.QUERY_PRICE
                logger.debug("LLM intent overridden to QUERY_PRICE by rule", query=query, original=intent_str)

            # Build SQL filters using rule-extracted entities (more reliable than LLM entities)
            sql_filters = {}
            if intent == QueryIntent.QUERY_PRICE:
                sql_filters = {"table": "price_variants", "conditions": {}}
                if "model_no" in entities:
                    sql_filters["conditions"]["model_no"] = entities["model_no"]
                if "color_name" in entities:
                    sql_filters["conditions"]["color_name"] = entities["color_name"]
                if "thickness" in entities:
                    sql_filters["conditions"]["thickness"] = entities["thickness"]
                if "substrate" in entities:
                    sql_filters["conditions"]["substrate"] = entities["substrate"]

            vector_query = query
            if intent == QueryIntent.QUERY_PRICE:
                vector_query = f"{entities.get('model_no', '')} {entities.get('color_name', '')} {query}"

            return ParsedQuery(
                intent=intent,
                original_query=original_query or query,
                entities=entities,
                sql_filters=sql_filters,
                vector_query=vector_query.strip(),
            )

        except Exception as e:
            logger.error("LLM intent recognition failed, falling back to rules", error=str(e))
            return self._parse_with_rules(query, entities=entities, original_query=original_query)

    def _detect_intent(self, query: str) -> QueryIntent:
        """Fallback intent detection (conservative, used only when LLM fails).

        Never aggressively trigger QUERY_PRICE. Let LLM do the heavy lifting.
        """
        if any(kw in query for kw in self.COMPARE_KEYWORDS):
            return QueryIntent.COMPARE
        if any(kw in query for kw in self.LIST_KEYWORDS):
            return QueryIntent.LIST_PRODUCTS

        # Only the most obvious price signals
        obvious_price = any(kw in query for kw in ["多少钱", "价格", "报价", "怎么卖", "什么价"])
        obvious_buy = any(kw in query for kw in ["买", "下单", "订购"])
        has_model = self._get_model_pattern().search(query)

        if has_model and (obvious_price or obvious_buy):
            return QueryIntent.QUERY_PRICE

        return QueryIntent.UNKNOWN

    def _extract_entities(self, query: str) -> Dict[str, Any]:
        """Extract entities from query text."""
        entities: Dict[str, Any] = {}

        # Model number (use DB-backed precise pattern)
        model_match = self._get_model_pattern().search(query)
        if model_match:
            entities["model_no"] = model_match.group(1)

        # Dimensions (e.g. 2000mm*50mm) — must be extracted BEFORE thickness
        # to avoid misinterpreting size numbers as thickness
        size_match = self.SIZE_PATTERN.search(query)
        if size_match:
            entities["dimensions"] = {
                "length": float(size_match.group(1)),
                "width": float(size_match.group(2)),
            }

        # Thickness — collect all candidates, filter out those inside size patterns
        size_spans = [(m.start(), m.end()) for m in self.SIZE_PATTERN.finditer(query)]
        for m in self.THICKNESS_PATTERN.finditer(query):
            t = int(m.group(1))
            if not (5 <= t <= 100):
                continue
            # Skip if this thickness overlaps with any size pattern (e.g. 200mm in 2000mm*50mm)
            t_start, t_end = m.start(), m.end()
            if any(t_start < s_end and t_end > s_start for s_start, s_end in size_spans):
                continue
            entities["thickness"] = t
            break  # Take the first valid standalone thickness

        # Color — use DB colors first (includes prefixes like █), fallback to hardcoded
        color_sources = self._db_color_keywords if self._db_color_keywords else self.COLOR_KEYWORDS
        for color in color_sources:
            if color in query:
                entities["color_name"] = color
                break

        # Substrate
        for substrate in self.SUBSTRATE_KEYWORDS:
            if substrate in query:
                entities["substrate"] = substrate
                break

        # Area
        area_match = self.AREA_PATTERN.search(query)
        if area_match:
            entities["area"] = float(area_match.group(1))

        # Component type — check canonicals and aliases, longer first
        all_ct_patterns = []
        for canonical in self.COMPONENT_TYPE_KEYWORDS:
            all_ct_patterns.append((canonical, canonical))
        for canonical, aliases in self.COMPONENT_TYPE_ALIASES.items():
            for alias in aliases:
                all_ct_patterns.append((alias, canonical))
        # Sort by alias length descending to match longer first
        all_ct_patterns.sort(key=lambda x: len(x[0]), reverse=True)
        for alias, canonical in all_ct_patterns:
            if alias in query:
                entities["component_type"] = canonical
                break

        return entities

    def _is_thickness_separate(self, query: str, thickness: int) -> bool:
        """Check if thickness value appears outside of dimension patterns."""
        import re
        # First: exclude if the thickness number is part of any size pattern (e.g. 2000*50)
        thickness_str = str(thickness)
        for m in self.SIZE_PATTERN.finditer(query):
            if thickness_str in m.group(0):
                return False

        # Second: check standalone mm mentions
        standalone = re.search(rf"\b{thickness}\s*(?:mm|毫米|厘)\b", query)
        if standalone:
            # Only exclude if * or × is directly adjacent (within 3 chars)
            before = query[:standalone.start()]
            after = query[standalone.end():]
            near_before = before[-3:]
            near_after = after[:3]
            if ("*" in near_before or "×" in near_before or
                "*" in near_after or "×" in near_after):
                return False
            return True
        return False
