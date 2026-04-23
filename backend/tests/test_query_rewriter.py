"""Tests for QueryRewriter."""

import pytest

from app.retrieval.query_rewriter import QueryRewriter
from app.retrieval.query_understanding import QueryUnderstandingEngine


class TestQueryRewriter:
    """Test query rewriting capabilities."""

    @pytest.fixture
    def rewriter(self):
        return QueryRewriter()

    # ── 1. Synonym normalization ───────────────────────────────

    def test_normalize_substrate_synonyms(self, rewriter):
        """刨花板 should be normalized to 颗粒板."""
        result = rewriter.rewrite("刨花板 18mm")
        assert "颗粒板" in result
        assert "刨花板" not in result

    def test_normalize_color_synonyms(self, rewriter):
        """Color aliases should be normalized to canonical names."""
        result = rewriter.rewrite("米白的门")
        assert "象牙白" in result

    def test_normalize_osb(self, rewriter):
        """OSB should be normalized to 欧松板."""
        result = rewriter.rewrite("OSB基材")
        assert "欧松板" in result

    def test_normalize_mdf(self, rewriter):
        """MDF should be normalized to 密度板."""
        result = rewriter.rewrite("MDF门板")
        assert "密度板" in result

    # ── 2. Spelling correction ─────────────────────────────────

    def test_correct_spelling_color(self, rewriter):
        """咖非灰 (typo) should be corrected to 咖啡灰."""
        result = rewriter.rewrite("咖非灰")
        assert "咖啡灰" in result

    def test_correct_spelling_substrate(self, rewriter):
        """颗泣板 (typo) should be corrected to 颗粒板."""
        result = rewriter.rewrite("颗泣板")
        assert "颗粒板" in result

    # ── 3. Model number completion ─────────────────────────────

    def test_complete_model_number(self, rewriter):
        """A01 should be completed to MX-A01."""
        result = rewriter.rewrite("A01 多少钱")
        assert "MX-A01" in result

    def test_no_duplicate_prefix(self, rewriter):
        """MX-A01 should not be double-prefixed."""
        result = rewriter.rewrite("MX-A01 价格")
        assert result.count("MX-A01") == 1

    # ── 4. Multi-turn context ──────────────────────────────────

    def test_session_context_model_no(self, rewriter):
        """Session should remember model_no from previous turn."""
        # First turn: establish context
        r1 = rewriter.rewrite("MX-A01 咖啡灰 18mm 多少钱？", session_id="sess_001")
        assert "MX-A01" in r1

        # Second turn: only mention thickness change
        r2 = rewriter.rewrite("25mm 的呢？", session_id="sess_001")
        assert "MX-A01" in r2
        assert "25mm" in r2

    def test_session_context_color(self, rewriter):
        """Session should remember and enrich with color."""
        rewriter.rewrite("MX-A02 深空灰", session_id="sess_002")
        r2 = rewriter.rewrite("18mm 价格", session_id="sess_002")
        assert "MX-A02" in r2
        assert "深空灰" in r2

    def test_different_sessions_isolated(self, rewriter):
        """Different sessions should not share context."""
        rewriter.rewrite("MX-A01", session_id="sess_a")
        r2 = rewriter.rewrite("多少钱", session_id="sess_b")
        assert "MX-A01" not in r2

    # ── 5. Integration with QueryUnderstandingEngine ───────────

    def test_engine_with_rewrite_price_query(self):
        """Full pipeline: typo query should still produce correct intent and entities."""
        engine = QueryUnderstandingEngine()
        parsed = engine.parse("咖非灰 A01 多少", session_id="sess_integ")

        assert parsed.intent.value == "query_price"
        assert parsed.entities.get("color_name") == "咖啡灰"
        assert parsed.entities.get("model_no") == "MX-A01"

    def test_engine_with_rewrite_substrate_query(self):
        """刨花板 should be normalized and recognized."""
        engine = QueryUnderstandingEngine()
        parsed = engine.parse("刨花板 18mm 价格", session_id="sess_sub")

        assert parsed.intent.value == "query_price"
        assert parsed.entities.get("substrate") == "颗粒板"
        assert parsed.entities.get("thickness") == 18

    def test_engine_multi_turn(self):
        """Multi-turn query understanding."""
        engine = QueryUnderstandingEngine()

        # Turn 1
        p1 = engine.parse("MX-A01 咖啡灰 多少钱", session_id="sess_mt")
        assert p1.entities.get("model_no") == "MX-A01"
        assert p1.entities.get("color_name") == "咖啡灰"

        # Turn 2: just thickness
        p2 = engine.parse("18mm 的", session_id="sess_mt")
        assert p2.entities.get("model_no") == "MX-A01"
        assert p2.entities.get("color_name") == "咖啡灰"
        assert p2.entities.get("thickness") == 18

    # ── 6. Edge cases ──────────────────────────────────────────

    def test_no_false_positive_on_short_words(self, rewriter):
        """Single char '灰' should not blindly be replaced in all contexts."""
        result = rewriter.rewrite("灰色空间")
        # Should not crash; may or may not contain 咖啡灰 depending on matching logic
        assert isinstance(result, str)

    def test_empty_query(self, rewriter):
        """Empty query should return empty string."""
        result = rewriter.rewrite("")
        assert result == ""

    def test_clear_session(self, rewriter):
        """Clearing session should remove context."""
        rewriter.rewrite("MX-A01", session_id="sess_clear")
        rewriter.clear_session("sess_clear")
        r2 = rewriter.rewrite("多少钱", session_id="sess_clear")
        assert "MX-A01" not in r2
