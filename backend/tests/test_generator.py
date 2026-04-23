"""Tests for generation layer — prompt building and response generation."""

import pytest

from app.generator.prompt_builder import PromptBuilder
from app.generator.schemas import GenerationResult
from app.retrieval.schemas import (
    ParsedQuery,
    QueryIntent,
    RetrievalContext,
    SemanticResult,
    StructuredResult,
)


class TestPromptBuilder:
    """Test prompt assembly from retrieval context."""

    def test_price_prompt_contains_structured_data(self):
        builder = PromptBuilder()
        context = RetrievalContext(
            query=ParsedQuery(
                intent=QueryIntent.QUERY_PRICE,
                original_query="MX-A01 多少钱？",
                entities={"model_no": "MX-A01"},
            ),
            structured_results=[
                StructuredResult(
                    product_id=1,
                    model_no="MX-A01",
                    model_name="平板门型",
                    family="饰面门板",
                    color_name="咖啡灰",
                    substrate="颗粒板",
                    thickness=18,
                    unit_price=318.00,
                    unit="元/㎡",
                )
            ],
        )
        messages = builder.build(context)
        assert len(messages) == 2  # system + user
        user_content = messages[1]["content"]
        assert "MX-A01" in user_content
        assert "318.00" in user_content
        assert "用户问题" in user_content

    def test_knowledge_prompt_contains_references(self):
        builder = PromptBuilder()
        context = RetrievalContext(
            query=ParsedQuery(
                intent=QueryIntent.KNOWLEDGE,
                original_query="安装注意什么？",
            ),
            semantic_results=[
                SemanticResult(
                    chunk_id=1,
                    content="安装时注意留缝2mm。",
                    source_doc="test.pdf",
                    page_no=5,
                    distance=0.2,
                )
            ],
        )
        messages = builder.build(context)
        user_content = messages[1]["content"]
        assert "参考资料" in user_content
        assert "安装时注意留缝2mm" in user_content
        assert "用户问题" in user_content

    def test_prompt_includes_images(self):
        builder = PromptBuilder()
        context = RetrievalContext(
            query=ParsedQuery(
                intent=QueryIntent.QUERY_PRICE,
                original_query="MX-A01",
            ),
            structured_results=[
                StructuredResult(
                    product_id=1,
                    model_no="MX-A01",
                    model_name="平板门型",
                    family="饰面门板",
                    color_name=None,
                    substrate=None,
                    thickness=None,
                    unit_price=None,
                    unit=None,
                    image_urls=["minio://products/mx-a01.png"],
                )
            ],
        )
        messages = builder.build(context)
        user_content = messages[1]["content"]
        assert "minio://products/mx-a01.png" in user_content

    def test_system_prompt_varies_by_intent(self):
        builder = PromptBuilder()

        price_ctx = RetrievalContext(
            query=ParsedQuery(intent=QueryIntent.QUERY_PRICE, original_query="价格"),
        )
        price_messages = builder.build(price_ctx)
        assert "销售顾问" in price_messages[0]["content"]

        knowledge_ctx = RetrievalContext(
            query=ParsedQuery(intent=QueryIntent.KNOWLEDGE, original_query="工艺"),
        )
        knowledge_messages = builder.build(knowledge_ctx)
        assert "技术顾问" in knowledge_messages[0]["content"]


class TestGenerationResult:
    """Test generation result data structures."""

    def test_to_dict(self):
        result = GenerationResult(
            answer_text="测试回答",
            intent="query_price",
            structured_data={"products": [{"model_no": "MX-A01"}]},
            image_urls=["img1.png"],
        )
        d = result.to_dict()
        assert d["answer_text"] == "测试回答"
        assert d["intent"] == "query_price"
        assert d["structured_data"]["products"][0]["model_no"] == "MX-A01"
        assert d["image_urls"] == ["img1.png"]

    def test_to_markdown_with_images(self):
        result = GenerationResult(
            answer_text="产品价格如下",
            image_urls=["http://example.com/img.png"],
        )
        md = result.to_markdown()
        assert "产品价格如下" in md
        assert "![产品图片](http://example.com/img.png)" in md


class TestGenerationEngine:
    """End-to-end generation tests (requires LLM API)."""

    @pytest.mark.slow
    def test_generate_price_answer(self):
        """Test full generation for price query.

        Marked as slow because it calls LLM API.
        """
        from app.generator.generator import GenerationEngine

        engine = GenerationEngine()

        # This will retrieve from DB and call LLM
        result = engine.answer("MX-A01 咖啡灰 18mm 多少钱？")

        assert isinstance(result, GenerationResult)
        assert result.intent == "query_price"
        assert len(result.answer_text) > 0
        # LLM should mention the price in its answer
        assert "318" in result.answer_text or "价格" in result.answer_text

    @pytest.mark.slow
    def test_generate_knowledge_answer(self):
        """Test full generation for knowledge query."""
        from app.generator.generator import GenerationEngine

        engine = GenerationEngine()
        result = engine.answer("G型拉手安装")

        assert isinstance(result, GenerationResult)
        assert len(result.answer_text) > 0
        # source_chunks may be empty if no matching chunks in DB; LLM can still answer
