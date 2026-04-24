"""Query Rewriter — fixes spelling, normalizes synonyms, and handles multi-turn context.

Core capabilities:
1. Spell correction (咖非灰 → 咖啡灰)
2. Synonym normalization (刨花板 → 颗粒板)
3. Model number completion (A01 → MX-A01)
4. Multi-turn context enrichment (uses session history to fill missing entities)
"""

import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


class QueryRewriter:
    """Rewrites user queries to improve structured retrieval accuracy."""

    # ── Synonym dictionaries ───────────────────────────────────
    # CRITICAL: Each alias must map to exactly ONE canonical.
    # If an alias could belong to multiple colors, assign it to the most common one.
    COLOR_SYNONYMS: Dict[str, List[str]] = {
        "咖啡灰": ["咖灰", "深咖灰"],
        "象牙白": ["米白", "奶白"],
        "高级灰": ["高级灰", "深灰"],
        "深空灰": ["深空灰", "太空灰"],
        "暖白色": ["暖白", "米黄色"],
        "经典白": ["经典白", "纯白"],
        "高光白": ["高光白", "亮白"],
        "高光灰": ["高光灰", "亮灰"],
        "原木色": ["木色", "木纹", "原木"],
        "胡桃木": ["胡桃", "胡桃色"],
        "樱桃木": ["樱桃", "樱桃色"],
        "纯黑": ["黑色", "黑"],
    }

    # Short generic aliases (1-2 chars) that match via word boundary only
    COLOR_SHORT_ALIASES: Dict[str, str] = {
        "灰": "灰色",      # marker only, resolved by context
        "白": "白色",
        "红": "红色",
        "黑": "黑色",
    }

    SUBSTRATE_SYNONYMS: Dict[str, List[str]] = {
        # Keep E0/ENF prefixes distinct — they have different prices
        "E0级实木颗粒板": ["E0颗粒板", "E0实木颗粒板"],
        "ENF级实木颗粒板": ["ENF颗粒板", "ENF实木颗粒板"],
        "颗粒板": ["刨花板", "实木颗粒板", "颗粒"],
        "复合多层板": ["复合多层"],
        "多层板": ["多层实木板", "胶合板", "多层"],
        "25mm中纤板": ["25中纤板"],
        "21mm中纤板": ["21中纤板"],
        "18mm中纤板": ["18中纤板"],
        "密度板": ["中纤板", "中密度纤维板", "MDF", "纤维板", "密度"],
        "ENF级欧松板": ["ENF欧松板"],
        "欧松板": ["OSB", "定向结构刨花板", "欧松"],
        "匠芯实木板": ["匠芯实木"],
        "实木板": ["原木板", "实木", "原木"],
    }

    # Reverse map: alias → canonical
    _color_alias_map: Dict[str, str] = {}
    _substrate_alias_map: Dict[str, str] = {}

    # Model prefix patterns — expanded to cover all product codes in the catalog
    MODEL_PREFIX_PATTERN = re.compile(
        r"\b([A-Z]-\d{2,4}|[A-Z]{1,2}\d{2,4}|\d{3,4})\b",
        re.IGNORECASE,
    )
    MODEL_FULL_PATTERN = re.compile(
        r"\b(MX-[A-Z]\d{2,3}[A-Z]?|WLS-\d{2,3}|LM-[A-Z]\d{2,3}-\d{2,3}|"
        r"[A-Z]{2,3}-[A-Z]{2,3}-\d{2,3}[A-Z]?|[A-Z]{2}-[A-Z]\d{2,3}|"
        r"[A-Z]{2}\d{4}[A-Z]?-\d{2,3}[A-Z]?|[A-Z]{3}-\d{3,4}|"
        r"[A-Z]{2}\d{2,4}[A-Z]?|"
        r"GE-\d{4}|MW-\d{2,3}|PET-\d{2,3}|RL-\d|DL0\dS?|DP0\d)\b",
        re.IGNORECASE,
    )

    # Known model prefixes for completion
    KNOWN_PREFIXES = ["MX-", "WLS-", "GE-", "MW-", "PET-", "RL-", "DL", "DP"]

    def __init__(self):
        self._build_alias_maps()
        self._db_colors: List[str] = []
        self._load_db_colors()
        # Session context store: session_id → last_entities
        self._session_context: Dict[str, Dict[str, Any]] = {}

    def _build_alias_maps(self):
        """Build reverse alias maps for O(1) lookup."""
        for canonical, aliases in self.COLOR_SYNONYMS.items():
            for alias in aliases:
                self._color_alias_map[alias] = canonical
            # Canonical maps to itself
            self._color_alias_map[canonical] = canonical

        for canonical, aliases in self.SUBSTRATE_SYNONYMS.items():
            for alias in aliases:
                self._substrate_alias_map[alias] = canonical
            self._substrate_alias_map[canonical] = canonical

    def _load_db_colors(self) -> None:
        """Load color names from DB for accurate extraction."""
        try:
            from app.core.database import engine
            from sqlalchemy import text
            with engine.connect() as conn:
                rows = conn.execute(text(
                    "SELECT DISTINCT color_name FROM price_variants WHERE color_name IS NOT NULL"
                )).fetchall()
                self._db_colors = sorted([r[0] for r in rows if r[0]], key=len, reverse=True)
        except Exception:
            pass  # fallback to COLOR_SYNONYMS only

    # ── Public API ─────────────────────────────────────────────

    def rewrite(
        self,
        query: str,
        session_id: Optional[str] = None,
        history_entities: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Rewrite a query for better retrieval.

        Args:
            query: Raw user query
            session_id: Session ID for multi-turn context (optional)
            history_entities: Explicitly passed entities from previous turn (optional)

        Returns:
            Rewritten query string
        """
        original = query
        rewritten = query

        # Step 1: Normalize whitespace
        rewritten = rewritten.strip()

        # Step 2: Spell correction + synonym normalization
        rewritten = self._normalize_component_types(rewritten)
        rewritten = self._normalize_colors(rewritten)
        rewritten = self._normalize_substrates(rewritten)
        rewritten = self._correct_spelling(rewritten)

        # Step 3: Model number completion (A01 → MX-A01)
        rewritten = self._complete_model_numbers(rewritten)

        # Step 4: Multi-turn context enrichment
        context_entities = self._get_session_context(session_id) or history_entities or {}
        if context_entities:
            rewritten = self._enrich_with_context(rewritten, context_entities)

        # Store entities for future turns
        if session_id:
            self._update_session_context(session_id, rewritten)

        if rewritten != original:
            logger.info("Query rewritten", original=original, rewritten=rewritten)

        return rewritten

    # ── Internal methods ───────────────────────────────────────

    def _normalize_colors(self, query: str) -> str:
        """Replace color aliases with canonical names."""
        # Sort by length descending to match longer aliases first
        aliases = sorted(self._color_alias_map.keys(), key=len, reverse=True)
        for alias in aliases:
            if alias in query:
                canonical = self._color_alias_map[alias]
                # Only replace if it's a whole-word match or the alias is multi-char
                if len(alias) >= 2:
                    query = query.replace(alias, canonical)
                else:
                    # Single char: be careful, use word boundary
                    pattern = re.compile(rf"(?<![一-龥a-zA-Z]){re.escape(alias)}(?![一-龥a-zA-Z])")
                    query = pattern.sub(canonical, query)
        return query

    def _normalize_component_types(self, query: str) -> str:
        """Replace component type aliases with canonical names."""
        # Build alias → canonical map
        alias_map: Dict[str, str] = {}
        for canonical, aliases in self.COMPONENT_TYPE_ALIASES.items():
            for alias in aliases:
                alias_map[alias] = canonical
            alias_map[canonical] = canonical
        aliases = sorted(alias_map.keys(), key=len, reverse=True)
        matches = []
        for alias in aliases:
            for m in re.finditer(re.escape(alias), query):
                start, end = m.start(), m.end()
                if any(start < e and end > s for s, e, _ in matches):
                    continue
                matches.append((start, end, alias_map[alias]))
        matches.sort(key=lambda x: x[0])
        parts = []
        prev_end = 0
        for start, end, canonical in matches:
            parts.append(query[prev_end:start])
            parts.append(canonical)
            prev_end = end
        parts.append(query[prev_end:])
        return "".join(parts)

    def _normalize_substrates(self, query: str) -> str:
        """Replace substrate aliases with canonical names.
        
        Uses position-aware replacement to avoid shorter aliases corrupting
        longer canonical names (e.g. '实木颗粒板' inside 'E0级实木颗粒板').
        """
        aliases = sorted(self._substrate_alias_map.keys(), key=len, reverse=True)
        # Find all non-overlapping matches (longest first)
        matches = []
        for alias in aliases:
            for m in re.finditer(re.escape(alias), query):
                start, end = m.start(), m.end()
                # Skip if this match overlaps with any already-recorded match
                if any(start < e and end > s for s, e, _ in matches):
                    continue
                canonical = self._substrate_alias_map[alias]
                matches.append((start, end, canonical))
        # Sort by position and replace
        matches.sort(key=lambda x: x[0])
        parts = []
        prev_end = 0
        for start, end, canonical in matches:
            parts.append(query[prev_end:start])
            parts.append(canonical)
            prev_end = end
        parts.append(query[prev_end:])
        return "".join(parts)

    def _correct_spelling(self, query: str) -> str:
        """Correct common misspellings using fuzzy matching."""
        # Build candidate vocabulary
        candidates = list(self.COLOR_SYNONYMS.keys()) + list(self.SUBSTRATE_SYNONYMS.keys())

        # Tokenize query into potential words (2+ chars), including adjacent alphanumerics
        # so that 'E0级实木颗粒板' is treated as one token, not split into '级实木颗粒板'
        tokens = re.findall(r"[a-zA-Z0-9]*[\u4e00-\u9fff]{2,}[a-zA-Z0-9]*", query)

        corrections = {}
        for token in tokens:
            # Skip if already a canonical form or known alias
            if token in self._color_alias_map or token in self._substrate_alias_map:
                continue

            best_match = None
            best_score = 0.0
            for candidate in candidates:
                score = SequenceMatcher(None, token, candidate).ratio()
                if score > best_score and score >= 0.6:
                    best_score = score
                    best_match = candidate

            if best_match:
                corrections[token] = best_match
                logger.debug("Spelling corrected", token=token, correction=best_match, score=best_score)

        for token, correction in corrections.items():
            query = query.replace(token, correction)

        return query

    def _complete_model_numbers(self, query: str) -> str:
        """Complete partial model numbers (A01 → MX-A01)."""
        # If full model already present, skip
        if self.MODEL_FULL_PATTERN.search(query):
            return query

        # Find partial matches like "A01", "B01" without prefix
        for match in self.MODEL_PREFIX_PATTERN.finditer(query):
            partial = match.group(1)
            # Check if it looks like our product model pattern (letter + digits)
            if re.match(r"^[A-Z]\d{2,3}$", partial):
                # Complete with MX- prefix (most common)
                full = f"MX-{partial}"
                query = query.replace(partial, full, 1)
                logger.debug("Model number completed", partial=partial, full=full)
                break  # Only complete one per query

        return query

    def _enrich_with_context(self, query: str, context: Dict[str, Any]) -> str:
        """Append missing entities from session context.

        Only adds entity types that are NOT already present in the current query.
        This prevents stale context from overriding user's new intent (e.g. changing color).
        """
        # If query already has a model number, don't add context model
        if self.MODEL_FULL_PATTERN.search(query):
            return query

        # Extract entities already present in current query
        current_entities = self._extract_entities_from_query(query)

        additions = []
        for key, val in context.items():
            if val and key not in current_entities:
                # Thickness needs unit suffix for entity extraction to match
                if key == "thickness":
                    additions.append(f"{val}mm")
                else:
                    additions.append(str(val))

        if additions:
            enriched = f"{' '.join(additions)} {query}"
            logger.debug("Query enriched with context", additions=additions, result=enriched)
            return enriched

        return query

    def _get_session_context(self, session_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """Get stored entities from previous turn."""
        if not session_id:
            return None
        return self._session_context.get(session_id)

    def _update_session_context(self, session_id: str, rewritten_query: str):
        """Extract and store entities from the current rewritten query."""
        entities = self._extract_entities_from_query(rewritten_query)
        if entities:
            # Merge with existing context
            existing = self._session_context.get(session_id, {})
            existing.update(entities)
            self._session_context[session_id] = existing
            logger.debug("Session context updated", session_id=session_id, entities=existing)

    # Known component types (canonical names matching DB)
    COMPONENT_TYPE_KEYWORDS = [
        "门板", "柜身", "护墙", "背板", "见光板", "收口条", "同色封边条",
        "吸塑柜门", "铝框玻璃门", "皮革门", "免漆套装门",
        "第二代铝木门", "第二代铝框隐形门", "饰面隐形门",
        "套装门附件", "异形件工艺费",
        "双开门", "子母门",
        "特殊工艺产品", "木抽盒及分线",
        "PET门板", "爱格板", "EB板", "22厚门板",
        "吸塑配件", "套装门五金",
    ]
    COMPONENT_TYPE_ALIASES = {
        "柜身": ["柜体", "柜子", "衣柜", "橱柜"],
        "门板": ["柜门"],
        "吸塑柜门": ["吸塑门", "包覆门", "吸塑门板"],
        "铝框玻璃门": ["铝框门", "玻璃门", "铝框玻璃", "铝玻璃门"],
        "皮革门": ["皮革门板", "皮门"],
        "免漆套装门": ["套装门", "室内门", "房门", "卧室门"],
        "第二代铝木门": ["铝木门", "二代铝木门"],
        "第二代铝框隐形门": ["铝框隐形门", "二代铝框隐形门"],
        "饰面隐形门": ["木质隐形门", "隐形门"],
        "套装门附件": ["哑口套", "门套线", "踢脚线", "门楣板", "窗套"],
        "异形件工艺费": ["工艺费", "开孔费", "木架费", "开槽费", "圆弧工艺", "切角工艺"],
        "双开门": ["对开门", "双扇门"],
        "子母门": ["子母套装门"],
        "特殊工艺产品": ["格栅", "圆弧护墙", "圆弧板", "铝立板", "ABA加厚板", "斜拼柜"],
        "木抽盒及分线": ["木抽盒", "格子架", "裤架", "拉板抽", "木分线"],
        "PET门板": ["PET门", "PET板"],
        "爱格板": ["爱格", "爱格门板"],
        "EB板": ["EB饰面", "EB门板"],
        "22厚门板": ["22厚门", "22厚板"],
        "吸塑配件": ["吸塑罗马柱", "吸塑脚线", "吸塑顶线", "吸塑楣板", "酒格"],
        "套装门五金": ["门锁", "门把手", "合页", "门吸", "液压合页", "指纹锁"],
    }

    def _extract_entities_from_query(self, query: str) -> Dict[str, Any]:
        """Quick entity extraction for context tracking."""
        entities = {}

        # Model
        m = self.MODEL_FULL_PATTERN.search(query)
        if m:
            entities["model_no"] = m.group(1)

        # Color — use DB colors first (includes █ prefixes), then fallback
        color_sources = self._db_colors if self._db_colors else list(self.COLOR_SYNONYMS.keys())
        for color in color_sources:
            if color in query:
                entities["color_name"] = color
                break

        # Substrate
        for canonical in self.SUBSTRATE_SYNONYMS:
            if canonical in query:
                entities["substrate"] = canonical
                break

        # Thickness — avoid numbers inside dimension patterns (e.g. 500mm in 500mm*2500mm)
        size_spans = []
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:mm|cm|m|厘米|米|毫米)?\s*(?:[\*×xX]|乘以)\s*(\d+(?:\.\d+)?)", query):
            size_spans.append((m.start(), m.end()))
        for m in re.finditer(r"(\d{2,3})\s*(?:mm|毫米|厘)", query):
            t = int(m.group(1))
            if not (5 <= t <= 100):
                continue
            t_start, t_end = m.start(), m.end()
            if any(t_start < s_end and t_end > s_start for s_start, s_end in size_spans):
                continue
            entities["thickness"] = t
            break

        # Area
        a = re.search(r"(\d+(?:\.\d+)?)\s*(?:平米|平方米|㎡)", query)
        if a:
            entities["area"] = float(a.group(1))

        # Component type — whitelist only, longer first
        for ct in self.COMPONENT_TYPE_KEYWORDS:
            if ct in query:
                entities["component_type"] = ct
                break

        return entities

    def clear_session(self, session_id: str):
        """Clear session context."""
        self._session_context.pop(session_id, None)
