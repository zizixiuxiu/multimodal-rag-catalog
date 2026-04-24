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
from app.schemas.quote import PriceQuoteParams, PriceQuoteResult, PricingRule, QuoteStep
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

        # 5. Handle tool calls (LLM-driven + fallback for reliability)
        structured_data = None
        forced_tool = False

        def _execute_tool_call(tc) -> Dict[str, Any]:
            args = json.loads(tc.function.arguments)
            logger.debug("LLM tool call raw args", args=args, session_id=session_id)
            # Restore decorative prefix (█) if user explicitly used it in query.
            color = args.get("color_name")
            if color and not color.startswith("█"):
                prefixed = f"█{color}"
                if prefixed in query:
                    args["color_name"] = prefixed
            # Merge missing/null params from NER + session history.
            sources = []
            if context and hasattr(context, 'query'):
                sources.append(context.query.entities)
            if session_id:
                try:
                    hist = self.retrieval.query_engine.rewriter._session_context.get(session_id, {})
                    if hist:
                        sources.append(hist)
                except Exception:
                    pass
            for src in sources:
                for key in ["area", "dimensions", "thickness", "substrate", "color_name", "component_type"]:
                    val = args.get(key)
                    if (val is None or val == "") and key in src and src[key] is not None:
                        logger.debug("Merging param from history", key=key, value=src[key], source=src is hist and "session" or "ner")
                        args[key] = src[key]
            logger.debug("Tool call merged args", args=args)
            return self._execute_price_quote(args)

        def _inject_tool_result(messages, tc, result, content):
            """Append tool call + result to messages for second LLM turn."""
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
            # Strip result for history (prevent token bloat & price memorization)
            # CRITICAL: include confirmed params so LLM remembers context across turns
            history_safe = {
                "model_no": result.get("model_no"),
                "component_type": result.get("component_type"),
                "color_name": result.get("color_name"),
                "substrate": result.get("substrate"),
                "thickness": result.get("thickness"),
                "area": result.get("area"),
                "available_options": result.get("available_options"),
                "variant_count": result.get("variant_count"),
                "is_partial": result.get("is_partial"),
                "sample_variant": result["variants"][0] if result.get("variants") else None,
            }
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(history_safe, ensure_ascii=False),
            })
            return messages

        def _save_component_type_to_session(ct: Optional[str]):
            """Preserve component_type in QueryRewriter session context so
            multi-turn enrichment works even when NER no longer extracts it."""
            if session_id and ct:
                try:
                    rewriter = self.retrieval.query_engine.rewriter
                    existing = rewriter._session_context.get(session_id, {})
                    existing["component_type"] = ct
                    rewriter._session_context[session_id] = existing
                except Exception:
                    pass

        if tool_calls:
            for tc in tool_calls:
                if tc.function.name == "get_price_quote":
                    result = _execute_tool_call(tc)
                    structured_data = self._build_structured_from_tool(result)
                    messages = _inject_tool_result(messages, tc, result, content)
                    # Save component_type from LLM's tool call into session context
                    args = json.loads(tc.function.arguments)
                    _save_component_type_to_session(args.get("component_type"))
        else:
            # Fallback: LLM didn't call tool — force-call to ensure progressive flow.
            entities = context.query.entities if context and hasattr(context, 'query') else {}
            # Also pull accumulated params from session history
            session_entities = {}
            if session_id:
                try:
                    session_entities = self.retrieval.query_engine.rewriter._session_context.get(session_id, {})
                except Exception:
                    pass
            forced_tool = True
            forced_args = {
                "component_type": entities.get("component_type") or session_entities.get("component_type"),
                "color_name": entities.get("color_name") or session_entities.get("color_name"),
                "substrate": entities.get("substrate") or session_entities.get("substrate"),
                "thickness": entities.get("thickness") or session_entities.get("thickness"),
                "model_no": entities.get("model_no") or session_entities.get("model_no"),
                "dimensions": entities.get("dimensions") or session_entities.get("dimensions"),
                "area": entities.get("area") or session_entities.get("area"),
            }
            forced_args = {k: v for k, v in forced_args.items() if v is not None}
            result = self._execute_price_quote(forced_args)
            structured_data = self._build_structured_from_tool(result)
            _save_component_type_to_session(forced_args.get("component_type"))
            synthetic_tc = type("ToolCall", (), {
                "id": "forced_001",
                "function": type("Func", (), {
                    "name": "get_price_quote",
                    "arguments": json.dumps(forced_args, ensure_ascii=False),
                })(),
            })()
            messages = _inject_tool_result(messages, synthetic_tc, result, content)

        # Second LLM turn (with tool results, or forced tool results)
        if tool_calls or forced_tool:
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
                    "查询产品价格或可用配置选项。\n"
                    "⚠️ **重要**：当客户提及任何产品相关信息（柜身/门板/护墙/颜色/基材/厚度/门型）时，**立即调用此工具**，不要只聊天！\n"
                    "即使参数不全，工具也会返回可用选项列表，你据此引导客户下一步选择。\n"
                    "支持两种模式：\n"
                    "1. 墙柜一体/柜身/护墙：提供 component_type + 可选的 color/substrate/thickness\n"
                    "2. 吸塑柜门：提供 component_type='吸塑柜门' + model_no(如MX-M00) + color + substrate\n"
                    "3. 铝框玻璃门：提供 component_type='铝框玻璃门' + model_no(如DL01S) + color(铝框颜色) + substrate(玻璃颜色)\n"
                    "4. 皮革门：提供 component_type='皮革门' + model_no(如DP01) + color + substrate\n"
                    "5. 免漆套装门：提供 component_type='免漆套装门' + model_no(如GE-0004) + color + substrate\n"
                    "6. 特定门型：提供 model_no + 可选的 color/substrate/thickness"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "component_type": {
                            "type": "string",
                            "description": "组件类型：柜身、门板、护墙、吸塑柜门、铝框玻璃门、皮革门、免漆套装门。客户说做柜子/柜体时用'柜身'，说门时用'门板'，说墙板/护墙时用'护墙'，说吸塑门/包覆门时用'吸塑柜门'，说铝框门/玻璃门时用'铝框玻璃门'，说皮革门/皮门时用'皮革门'，说套装门/室内门/房门时用'免漆套装门'。只要客户提到其中任何一个，就必须填。",
                        },
                        "model_no": {
                            "type": "string",
                            "description": "门型型号，如 MX-A01。仅当客户明确指定门型时填写。",
                        },
                        "color_name": {
                            "type": "string",
                            "description": "颜色名称，如 咖啡灰、雪山白。客户提到颜色时必须填。",
                        },
                        "substrate": {
                            "type": "string",
                            "description": "基材名称，如 ENF级实木颗粒板、欧松板、多层板、18mm中纤板、21mm中纤板、25mm中纤板。客户提到基材时必须填。",
                        },
                        "thickness": {
                            "type": "integer",
                            "description": "厚度(mm)，如 9、18、25、36。客户提到厚度时必须填。",
                        },
                        "dimensions": {
                            "type": "string",
                            "description": "尺寸，如 2000mm*500mm 或 宽2000高500，用于计算面积和总价",
                        },
                        "area": {
                            "type": "number",
                            "description": "面积(㎡)，客户直接提供面积时填写",
                        },
                        "room": {
                            "type": "string",
                            "description": "房间，如 客厅、卧室、厨房",
                        },
                    },
                    "required": [],
                },
            },
        }

    # ─────────────────────────────────────────────
    # Tool execution
    # ─────────────────────────────────────────────

    @staticmethod
    def _clean_color_name(name: str) -> str:
        """Strip decorative prefixes/suffixes (█ ☆ S) for display."""
        if not name:
            return name
        return name.lstrip("█").rstrip("☆").rstrip("S")

    def _resolve_color_name(
        self, db, component_type: Optional[str], color_name: str
    ) -> str:
        """Resolve user-input color to exact DB color name.

        Logic:
        1. Exact match first
        2. Try prefixed version (█{color_name}) — the main product line
        3. Try fuzzy match (strip prefixes), prefer prefixed if multiple
        4. Fallback: return original
        """
        from sqlalchemy import select, or_, func

        base_stmt = select(PriceVariant.color_name).distinct()
        if component_type:
            base_stmt = base_stmt.where(PriceVariant.component_type == component_type)

        # 1. Exact match
        exact = db.execute(
            base_stmt.where(PriceVariant.color_name == color_name)
        ).scalars().all()
        if exact:
            return color_name

        # 2. Prefixed version (main product line)
        prefixed = db.execute(
            base_stmt.where(PriceVariant.color_name == f"█{color_name}")
        ).scalars().all()
        if prefixed:
            return f"█{color_name}"

        # 3. Fuzzy match — strip decorative chars
        clean_col = func.regexp_replace(PriceVariant.color_name, "[█☆S]", "", "g")
        fuzzy = db.execute(
            base_stmt.where(clean_col == color_name)
        ).scalars().all()
        if fuzzy:
            # Prefer prefixed version if available
            for c in fuzzy:
                if c.startswith("█"):
                    return c
            return fuzzy[0]

        # 4. Substring match (last resort)
        substr = db.execute(
            base_stmt.where(PriceVariant.color_name.ilike(f"%{color_name}%"))
        ).scalars().all()
        if substr:
            for c in substr:
                if c.startswith("█"):
                    return c
            return substr[0]

        return color_name

    def _execute_price_quote(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Query DB + compute available options + apply pricing rules.
        Progressive disclosure: limits variant count to keep response small.
        CRITICAL: All matching is precise — no mixing of similar color names.
        """
        from sqlalchemy import select, or_, func

        params = PriceQuoteParams.model_validate(args)
        component_type = params.component_type
        model_no = params.model_no
        color_name = params.color_name
        substrate = params.substrate
        thickness = params.thickness
        dimensions = params.dimensions
        area_input = params.area
        room = params.room

        MAX_VARIANTS = 8

        with get_db_context() as db:
            # ── Determine product scope ──
            # Price records are spread across multiple products (door models +
            # wall-cabinet). Query the entire table and filter by component_type
            # so we don't miss colors that are only attached to specific models.
            wall_product = db.execute(
                select(Product).where(Product.model_no == "墙柜一体")
            ).scalar_one_or_none()
            if not wall_product:
                return {"error": "价格表数据未初始化，请联系管理员。"}
            product_info = wall_product

            if model_no and not component_type:
                product = db.execute(
                    select(Product).where(Product.model_no == model_no)
                ).scalar_one_or_none()
                if not product:
                    return {"error": f"未找到型号 {model_no}，请确认型号是否正确。"}
                # When a specific model is given, still scope to that model's
                # component_type if we can infer it (门板 models have 门板 variants).
                stmt = select(PriceVariant).where(PriceVariant.product_id == product.id)
                product_info = product
            else:
                stmt = select(PriceVariant)
                if component_type:
                    stmt = stmt.where(PriceVariant.component_type == component_type)

            # ── Resolve color to exact DB name BEFORE filtering ──
            resolved_color: Optional[str] = None
            if color_name:
                resolved_color = self._resolve_color_name(db, component_type, color_name)
                # If resolution changed the color name, log it
                if resolved_color != color_name:
                    logger.debug(
                        "Color resolved",
                        input=color_name,
                        resolved=resolved_color,
                        component_type=component_type,
                    )

            # Apply filters — STRICT exact matching for color
            if resolved_color:
                stmt = stmt.where(PriceVariant.color_name == resolved_color)
            elif color_name:
                # Fallback for unresolved colors (shouldn't happen often)
                clean_col = func.regexp_replace(PriceVariant.color_name, "[█☆S]", "", "g")
                stmt = stmt.where(
                    or_(
                        PriceVariant.color_name == color_name,
                        clean_col == color_name,
                    )
                )
            if substrate:
                # Strict substrate matching — no substring match to prevent
                # '颗粒板' from matching 'E0级实木颗粒板'.
                stmt = stmt.where(PriceVariant.substrate == substrate)
            if thickness:
                stmt = stmt.where(PriceVariant.thickness == thickness)

            variants = db.execute(stmt).scalars().all()

            # ── Validate model_no if explicitly provided ──
            if model_no:
                matching = [v for v in variants if v.applicable_models and model_no in v.applicable_models]
                if not matching:
                    # Model not found — return error with available models
                    available_models = sorted({m for v in variants for m in (v.applicable_models or [])})
                    return {
                        "error": f"未找到门型型号「{model_no}」，请确认型号是否正确。",
                        "component_type": component_type,
                        "model_no": model_no,
                        "available_options": {
                            "model_no": available_models[:20] if available_models else []
                        },
                    }
                variants = matching

            # ── Build available options (progressive disclosure) ──
            # Options must be derived from REAL existing combinations.
            _all_missing = {}
            if not component_type and not model_no:
                _all_missing["component_type"] = sorted({v.component_type for v in variants})
            if not color_name:
                # Deduplicate by cleaned name — user sees "咖啡灰" not "█咖啡灰"
                seen_clean = set()
                color_options = []
                for v in variants:
                    clean = self._clean_color_name(v.color_name)
                    if clean not in seen_clean:
                        seen_clean.add(clean)
                        color_options.append(clean)
                _all_missing["color_name"] = sorted(color_options)[:15]
            if not substrate:
                _all_missing["substrate"] = sorted({v.substrate for v in variants})
            if not thickness:
                _all_missing["thickness"] = sorted({str(v.thickness) for v in variants})

            STEP_ORDER = ["component_type", "color_name", "substrate", "thickness"]
            available_options = {}
            for step in STEP_ORDER:
                if step in _all_missing:
                    available_options[step] = _all_missing[step]
                    break

            is_partial = bool(available_options)

            if not variants:
                # User picked a non-existent combination. Build fallback options
                # from the closest matching records so they can correct their choice.
                fallback_stmt = select(PriceVariant)
                if component_type:
                    fallback_stmt = fallback_stmt.where(PriceVariant.component_type == component_type)
                if resolved_color:
                    fallback_stmt = fallback_stmt.where(PriceVariant.color_name == resolved_color)
                fallback_vars = db.execute(fallback_stmt).scalars().all()

                fallback_options = {}
                if fallback_vars:
                    available_substrates = {v.substrate for v in fallback_vars}
                    available_thicknesses = {str(v.thickness) for v in fallback_vars}

                    if not substrate:
                        fallback_options["substrate"] = sorted(available_substrates)
                    elif substrate not in available_substrates:
                        fallback_options["substrate"] = sorted(available_substrates)
                    elif not thickness or str(thickness) not in available_thicknesses:
                        fallback_options["thickness"] = sorted(available_thicknesses)

                return {
                    "error": "未找到匹配的价格记录。",
                    "component_type": component_type,
                    "color_name": color_name,
                    "substrate": substrate,
                    "thickness": thickness,
                    "area": area_input,
                    "available_options": fallback_options or available_options,
                }

            # ── Compute area from dimensions ──
            area = area_input
            if dimensions and not area:
                dim_match = re.search(
                    r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:[*×xX]|乘以)\s*(\d+(?:\.\d+)?)",
                    dimensions,
                )
                if dim_match:
                    length = float(dim_match.group(1))
                    width = float(dim_match.group(2))
                    area = (length * width) / 1_000_000

            # ── Build results ──
            results = []
            rules_applied = []
            warnings = []

            if is_partial:
                return {
                    "model_no": product_info.model_no,
                    "model_name": product_info.name,
                    "family": product_info.family,
                    "component_type": component_type,
                    "color_name": color_name,
                    "substrate": substrate,
                    "thickness": thickness,
                    "area": area,
                    "room": room,
                    "variants": [],
                    "variant_count": 0,
                    "rules_applied": [],
                    "warnings": [],
                    "available_options": available_options,
                    "is_partial": True,
                }

            # ── Deduplicate: same color+substrate+thickness → keep cheapest ──
            # Also filter to resolved color only (should already be exact)
            best_by_combo: Dict[tuple, PriceVariant] = {}
            for v in variants:
                key = (v.color_name, v.substrate, v.thickness)
                if key not in best_by_combo or v.unit_price < best_by_combo[key].unit_price:
                    best_by_combo[key] = v
            variants = list(best_by_combo.values())

            # Limit variants for response size
            variants = variants[:MAX_VARIANTS]

            # Warn if duplicates were found
            if len(best_by_combo) < len(variants) + (len(variants) - len(best_by_combo)):
                pass  # deduplication happened silently

            # ── Build structured applicable_models for 门板 ──
            all_model_nos = set()
            for v in variants:
                if v.component_type == "门板" and v.applicable_models:
                    all_model_nos.update(v.applicable_models)

            model_info_cache = {}
            if all_model_nos:
                from app.models.product import ImageVector
                prod_rows = db.execute(
                    select(Product).where(Product.model_no.in_(list(all_model_nos)))
                ).scalars().all()
                for prod in prod_rows:
                    imgs = list(prod.image_urls or [])
                    try:
                        img_rows = db.execute(
                            select(ImageVector.image_url).where(ImageVector.product_id == prod.id)
                        ).scalars().all()
                        for url in img_rows:
                            if url and url not in imgs:
                                imgs.append(url)
                    except Exception:
                        pass
                    model_info_cache[prod.model_no] = {
                        "model_no": prod.model_no,
                        "name": prod.name or prod.model_no,
                        "description": prod.description or "",
                        "image_urls": imgs,
                    }
                for mn in all_model_nos:
                    if mn not in model_info_cache:
                        model_info_cache[mn] = {
                            "model_no": mn,
                            "name": mn,
                            "description": "",
                            "image_urls": [],
                        }

            for v in variants:
                item = {
                    "color_name": self._clean_color_name(v.color_name),
                    "substrate": v.substrate,
                    "thickness": v.thickness,
                    "component_type": v.component_type,
                    "unit_price": float(v.unit_price),
                    "unit": v.unit,
                    "min_charge_area": float(v.min_charge_area) if v.min_charge_area else None,
                }

                effective_area = area
                if area is not None and v.min_charge_area:
                    min_area = float(v.min_charge_area)
                    if area < min_area:
                        effective_area = min_area
                        rules_applied.append(
                            f"{v.component_type}单件不足{min_area}㎡按{min_area}㎡计价"
                        )

                if area is not None:
                    item["area"] = round(area, 4)
                    item["effective_area"] = round(effective_area, 4) if effective_area else None
                    item["total_price"] = round(float(v.unit_price) * (effective_area or area), 2)

                if v.component_type == "门板":
                    item["applicable_models"] = [
                        model_info_cache.get(mn, {"model_no": mn, "name": mn, "description": "", "image_urls": []})
                        for mn in (v.applicable_models or [])
                    ]

                results.append(item)

            # Collect product images
            image_urls = list(product_info.image_urls or [])
            try:
                from app.models.product import ImageVector
                img_rows = db.execute(
                    select(ImageVector.image_url).where(ImageVector.product_id == product_info.id)
                ).scalars().all()
                for url in img_rows:
                    if url and url not in image_urls:
                        image_urls.append(url)
            except Exception:
                pass

            # Build related options — query ALL records for this component_type
            related_stmt = select(PriceVariant).where(
                PriceVariant.component_type == component_type,
            )
            related_vars = db.execute(related_stmt).scalars().all()
            seen_clean_colors = set()
            related_colors = []
            for v in related_vars:
                clean = self._clean_color_name(v.color_name)
                if clean not in seen_clean_colors:
                    seen_clean_colors.add(clean)
                    related_colors.append(clean)

            related_options = {
                "color_name": sorted(related_colors)[:20],
                "substrate": sorted({v.substrate for v in related_vars}),
                "thickness": sorted({str(v.thickness) for v in related_vars}),
            }

            return {
                "model_no": product_info.model_no,
                "model_name": product_info.name,
                "family": product_info.family,
                "component_type": component_type,
                "color_name": color_name,
                "substrate": substrate,
                "thickness": thickness,
                "area": area,
                "room": room,
                "variants": results,
                "variant_count": len(results),
                "rules_applied": rules_applied,
                "warnings": list(set(warnings)),
                "available_options": {},
                "is_partial": False,
                "image_urls": image_urls,
                "related_options": related_options,
            }

    # ─────────────────────────────────────────────
    # System prompt & product catalog
    # ─────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        products = self._get_product_overview()
        # Only show door models + wall-cabinet, skip accessories
        door_lines = "\n".join(
            f"- {p['model_no']}: {p['name']}"
            for p in products
            if p['model_no'].startswith('MX-') or p['model_no'] == '墙柜一体'
        )
        # 吸塑柜门门型
        xisu_models = [
            "MX-M00", "MX-M23", "MX-M24", "MX-M25", "MX-M26",
            "MX-M15", "MX-M16", "MX-M17", "MX-M04", "MX-M34",
            "MX-M21", "MX-M22", "MX-M33", "MX-M06", "MX-M07",
            "MX-M01", "MX-M03", "MX-M09", "MX-M31", "MX-M35",
            "MX-M18", "MX-M20", "MX-M19", "MX-M27", "MX-M28",
            "MX-M29", "MX-M30", "波浪装饰板", "吸塑格栅",
        ]
        xisu_lines = "\n".join(f"- {m}" for m in xisu_models)
        # 铝框玻璃门门型
        glass_models = [
            "DL01S: 窄边铝框玻璃门 (855元/㎡)",
            "DL02: 弧形铝框玻璃门 (1860元/㎡)",
            "DL04: 斜边铝框玻璃门 (1521元/㎡)",
            "DL05: T型通顶拉手铝框玻璃门 (2550元/㎡)",
            "DL06: A款免拉手铝框门 (2880元/㎡)",
            "DL07: B款免拉手铝框门 (2970元/㎡)",
        ]
        glass_lines = "\n".join(f"- {m}" for m in glass_models)
        # 皮革门门型
        leather_models = [
            "DP01: 灰色金属包边皮革门 (3504元/㎡)",
            "DP02: 古铜拉丝金属包边皮革门 (3504元/㎡)",
            "DP03: 编织纹皮革车线皮革门 (3504元/㎡)",
        ]
        leather_lines = "\n".join(f"- {m}" for m in leather_models)
        # 免漆套装门门型
        set_models = [
            "GE-0004: 平板无造型 (1285元/樘)",
            "GE-1003~GE-1014: 平板拉黑色水线 (1465元/樘)",
            "MW-02/MW-06: 平板嵌T型黑色金属条 (1465元/樘)",
            "MW-03: 平板嵌T型黑色金属条 (1675元/樘)",
            "MW-04: 平板拉水线+嵌花 (1705元/樘)",
            "GE-4010~GE-5007: 平板拉水线+嵌花 (1615元/樘)",
            "GE-4071~GE-4085: 黑色水线+嵌花/嵌装饰条 (1614~1764元/樘)",
            "PET-35: 平板门无造型 (1465元/樘)",
            "PET-20~PET-42: 平板拉黑色水线 (1555元/樘)",
            "GE-5003: 拼装成型门 (2220元/樘)",
            "GE-5011/MW-05/MW-07/GE-5001: 拼装成型门 (2070元/樘)",
        ]
        set_lines = "\n".join(f"- {m}" for m in set_models)

        return (
            "你是奢匠家居定制的专属客服顾问「小奢」。\n\n"
            "【风格】热情专业，自然交流，适当用emoji 😊\n\n"
            "【产品型号 — 饰面门板】\n"
            f"{door_lines}\n\n"
            "【产品型号 — 吸塑柜门】\n"
            f"{xisu_lines}\n\n"
            "【产品型号 — 铝框玻璃门】\n"
            f"{glass_lines}\n\n"
            "【产品型号 — 皮革门】\n"
            f"{leather_lines}\n\n"
            "【产品型号 — 免漆套装门】\n"
            f"{set_lines}\n\n"
            "【报价工具 — 核心规则】\n"
            "⚠️ 有 get_price_quote 工具查实时价格，**禁止编造任何价格/选项**。\n"
            "⚠️ 客户提到柜身/门板/护墙/颜色/基材/厚度/门型时，**立即调用工具**。\n"
            "⚠️ **参数不全时工具只返回 available_options（选项列表），不返回任何价格**。\n"
            "   所以你在这个阶段**绝对不要提任何价格或参考价**，只引导用户做选择。\n"
            "⚠️ **每轮对话中，只要客户补充了新参数，必须重新调用工具**。\n\n"
            "【component_type — 最关键】\n"
            "柜身、门板、护墙、吸塑柜门、铝框玻璃门、皮革门、免漆套装门的价格体系完全不同，**必须明确确认类型**，不能猜测！\n"
            "- 客户说'柜子/衣柜/橱柜' → 理解为'柜身'\n"
            "- 客户说'门/门板' → 理解为'门板'\n"
            "- 客户说'墙/护墙' → 理解为'护墙'\n"
            "- 客户说'吸塑门/吸塑柜门/包覆门' → 理解为'吸塑柜门'\n"
            "- 客户说'铝框门/铝框玻璃门/玻璃门' → 理解为'铝框玻璃门'\n"
            "- 客户说'皮革门/皮门' → 理解为'皮革门'\n"
            "- 客户说'套装门/室内门/房门/卧室门' → 理解为'免漆套装门'\n"
            "- 如果客户没有明确说类型，工具会返回 component_type 选项，你必须追问：\n"
            "  '请问您是想做柜身、门板、护墙、吸塑柜门、铝框玻璃门、皮革门还是免漆套装门呢？'\n\n"
            "【渐进式报价流程 — 每轮只做一步】\n"
            "1. 客户说'柜身' → 调用工具(component_type='柜身') → 返回颜色选项 → 问颜色\n"
            "2. 客户说'咖啡灰' → 调用工具(+color) → 返回基材选项 → 问基材\n"
            "3. 客户说'颗粒板' → 调用工具(+substrate) → 返回厚度选项 → 问厚度\n"
            "4. 客户说'18mm' → 调用工具(+thickness) → 参数齐全 → **此时才展示单价**\n"
            "5. 客户提供尺寸/面积 → 工具计算总价\n\n"
            "【价格展示规则】\n"
            "- is_partial=true（参数不全）：**不提任何价格**，只展示选项并引导选择\n"
            "- is_partial=false（参数齐全）：展示精确单价和总价\n\n"
            "【历史消息限制】\n"
            "工具返回的结果中不会包含完整价格列表，所以你**无法从历史消息中回忆价格**。\n"
            "每轮客户给出新参数时，**必须重新调用 get_price_quote**。\n\n"
            "【颜色选择 — 绝对禁止替用户做决定】\n"
            "**你必须让用户自己选颜色，不能擅自替用户决定！**\n"
            "- 客户说'我喜欢简约风' → 调用工具获取颜色列表 → 从列表中挑3-5个符合简约风格的推荐 → 说'推荐以下几个，您看看喜欢哪个：XX、XX、XX'\n"
            "- 客户说'给我推荐几个' → 调用工具获取颜色列表 → 推荐3-5个热门色 → 让用户自己选\n"
            "- **只有客户明确说出颜色名称（如'咖啡灰'）时，才能确定颜色，进入下一步基材选择**\n"
            "- 绝对禁止说'您选择了XX颜色'，除非客户亲口说了那个颜色名称\n\n"
            "【颜色风格参考】\n"
            "以下分类仅用于引导推荐，不能替用户决定：\n"
            "- 复古/经典：半透胡桃2号、沉香胡桃、古枋留痕、黑檀木、铁刀木、樱桃木、经典茶色\n"
            "- 现代/极简：月影灰、深空灰、极致黑、咖啡灰、雪山白、经典白、云青灰\n"
            "- 原木/自然：亚麻橡木、卡塞尔榆木、森屿棕橡、沙丘橡木、杏仁色、沉香胡桃\n"
            "- 轻奢/暖调：温莎金、燕尾灰、焦糖灰、奶油灰、莫兰迪粉、梨花白\n"
            "⚠️ 注意：以上颜色不一定全部存在于当前 component_type 中，必须通过工具确认！\n\n"
            "【计价规则】\n"
            "- 门板/护墙不足0.2㎡按0.2㎡计价；抽面不足0.1㎡按0.1㎡计价\n"
            "- 门板宽≥350mm且高≥1600mm需加拉直器（价格另计）\n"
            "- 柜身按展开面积计价\n"
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
        q = query.strip()
        # Don't treat product/quote keywords as greeting
        product_keywords = ["柜身", "门板", "护墙", "见光板", "抽面",
                           "柜子", "衣柜", "橱柜", "书柜", "鞋柜",
                           "门", "墙", "报价", "价格", "多少钱", "怎么卖"]
        if any(kw in q for kw in product_keywords):
            return False
        return q in short_greetings or len(q) <= 2

    def _welcome_result(self, session_id: Optional[str]) -> GenerationResult:
        if session_id:
            self._seen_sessions.add(session_id)

        welcome = (
            "👋 欢迎来到**奢匠家居定制**！我是您的专属顾问小奢。\n\n"
            "我可以帮您：\n"
            "• 🏠 了解各类饰面门板、柜身、护墙的特点和优势\n"
            "• 💰 查询产品价格并精准计算报价（支持柜身/门板/护墙）\n"
            "• 📐 根据您的尺寸需求核算总价（含最低计价面积规则）\n\n"
            "您可以告诉我：\n"
            "• 做什么组件？（柜身、门板、护墙）\n"
            "• 用什么颜色和基材？\n"
            "• 面积或尺寸是多少？\n\n"
            "我来为您一步步引导报价～"
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
        if "error" in result and not result.get("available_options"):
            return None
        products = []
        for v in result.get("variants", []):
            products.append({
                "model_no": result.get("model_no"),
                "model_name": result.get("model_name"),
                "family": result.get("family"),
                "component_type": v.get("component_type"),
                "color_name": v.get("color_name"),
                "substrate": v.get("substrate"),
                "thickness": v.get("thickness"),
                "unit_price": v.get("unit_price"),
                "unit": v.get("unit"),
                "area": v.get("area"),
                "effective_area": v.get("effective_area"),
                "total_price": v.get("total_price"),
                "min_charge_area": v.get("min_charge_area"),
                "applicable_models": v.get("applicable_models"),
                "image_urls": result.get("image_urls", []),
                "rules_applied": v.get("rules_applied", []),
                "warnings": v.get("warnings", []),
            })
        sd = {
            "products": products,
            "rules_applied": result.get("rules_applied", []),
            "warnings": result.get("warnings", []),
        }
        # Include related options (alternative colors/substrates/thicknesses)
        if result.get("related_options"):
            sd["related_options"] = result["related_options"]
        # Include available options for guided selection
        if result.get("available_options"):
            sd["guide_mode"] = True
            sd["options"] = result["available_options"]
            sd["is_partial"] = result.get("is_partial", False)
        return sd

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
