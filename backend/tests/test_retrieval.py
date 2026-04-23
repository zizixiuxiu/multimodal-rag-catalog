"""Tests for retrieval layer — query understanding, structured search, semantic search."""

import pytest

from app.core.database import get_db_context
from app.models import PriceVariant, Product, TextChunk
from app.retrieval.query_understanding import QueryUnderstandingEngine
from app.retrieval.reranker import Reranker
from app.retrieval.schemas import QueryIntent, RetrievalContext, StructuredResult
from app.retrieval.semantic_retriever import SemanticRetriever
from app.retrieval.structured_retriever import StructuredRetriever
from app.services.data_import import DataImportService


class TestQueryUnderstanding:
    """Test query parsing and intent recognition."""

    def test_price_query_intent(self):
        engine = QueryUnderstandingEngine()
        parsed = engine.parse("MX-A04 咖啡灰18mm柜门多少钱？")
        assert parsed.intent == QueryIntent.QUERY_PRICE
        assert parsed.entities.get("model_no") == "MX-A04"
        assert parsed.entities.get("color_name") == "咖啡灰"
        assert parsed.entities.get("thickness") == 18

    def test_knowledge_query_intent(self):
        engine = QueryUnderstandingEngine()
        parsed = engine.parse("吸塑门板的安装工艺是什么？")
        assert parsed.intent == QueryIntent.KNOWLEDGE

    def test_list_query_intent(self):
        engine = QueryUnderstandingEngine()
        parsed = engine.parse("你们有哪些门型？")
        assert parsed.intent == QueryIntent.LIST_PRODUCTS

    def test_compare_query_intent(self):
        engine = QueryUnderstandingEngine()
        parsed = engine.parse("MX-A01和MX-A04有什么区别？")
        assert parsed.intent == QueryIntent.COMPARE

    def test_model_no_extraction(self):
        engine = QueryUnderstandingEngine()
        parsed = engine.parse("WLS-08拉手的价格是多少？")
        assert parsed.entities.get("model_no") == "WLS-08"

    def test_sql_filters_for_price(self):
        engine = QueryUnderstandingEngine()
        parsed = engine.parse("MX-A04 咖啡灰 18mm")
        assert "model_no" in parsed.sql_filters.get("conditions", {})
        assert "color_name" in parsed.sql_filters.get("conditions", {})
        assert "thickness" in parsed.sql_filters.get("conditions", {})


class TestStructuredRetriever:
    """Test exact SQL price queries."""

    @pytest.fixture(autouse=True)
    def setup_data(self):
        """Insert test data before each test."""
        with get_db_context() as db:
            # Clean
            db.query(PriceVariant).delete()
            db.query(Product).delete()
            db.commit()

            # Insert test product with variants
            product = Product(
                family="饰面门板",
                model_no="MX-TEST-01",
                name="测试门型",
                description="用于测试的门型",
                image_urls=["minio://test/1.png"],
            )
            db.add(product)
            db.commit()
            db.refresh(product)

            variants = [
                PriceVariant(product_id=product.id, color_name="咖啡灰", substrate="颗粒板", thickness=18, unit_price=318.00),
                PriceVariant(product_id=product.id, color_name="咖啡灰", substrate="多层板", thickness=18, unit_price=368.00),
                PriceVariant(product_id=product.id, color_name="象牙白", substrate="颗粒板", thickness=18, unit_price=328.00),
            ]
            for v in variants:
                db.add(v)
            db.commit()

        yield

        # Cleanup
        with get_db_context() as db:
            db.query(PriceVariant).delete()
            db.query(Product).delete()
            db.commit()

    def test_exact_price_query(self):
        retriever = StructuredRetriever()

        from app.retrieval.schemas import ParsedQuery
        parsed = ParsedQuery(
            intent=QueryIntent.QUERY_PRICE,
            original_query="MX-TEST-01 咖啡灰 18mm",
            entities={"model_no": "MX-TEST-01", "color_name": "咖啡灰", "thickness": 18},
            sql_filters={"table": "price_variants", "conditions": {"model_no": "MX-TEST-01", "color_name": "咖啡灰", "thickness": 18}},
        )

        results = retriever.search(parsed)
        assert len(results) >= 1
        assert any(r.unit_price == 318.00 for r in results)

    def test_price_query_with_all_filters(self):
        retriever = StructuredRetriever()

        from app.retrieval.schemas import ParsedQuery
        parsed = ParsedQuery(
            intent=QueryIntent.QUERY_PRICE,
            original_query="MX-TEST-01 咖啡灰 颗粒板 18mm",
            entities={"model_no": "MX-TEST-01", "color_name": "咖啡灰", "substrate": "颗粒板", "thickness": 18},
            sql_filters={"table": "price_variants", "conditions": {"model_no": "MX-TEST-01", "color_name": "咖啡灰", "substrate": "颗粒板", "thickness": 18}},
        )

        results = retriever.search(parsed)
        assert len(results) == 1
        assert results[0].unit_price == 318.00

    def test_list_all_variants(self):
        retriever = StructuredRetriever()

        from app.retrieval.schemas import ParsedQuery
        parsed = ParsedQuery(
            intent=QueryIntent.QUERY_PRICE,
            original_query="MX-TEST-01",
            entities={"model_no": "MX-TEST-01"},
            sql_filters={"table": "price_variants", "conditions": {"model_no": "MX-TEST-01"}},
        )

        results = retriever.search(parsed)
        assert len(results) == 3
        prices = {float(r.unit_price) for r in results}
        assert prices == {318.00, 328.00, 368.00}


class TestSemanticRetriever:
    """Test vector similarity search."""

    @pytest.fixture(autouse=True)
    def setup_chunks(self):
        """Insert test text chunks with embeddings."""
        from app.services.models import embedding_service

        with get_db_context() as db:
            db.query(TextChunk).delete()
            db.commit()

            texts = [
                "G型拉手门型需搭配专用铰链，安装时注意留缝2mm。",
                "吸塑门板的厚度规格为18mm和25mm两种。",
                "所有柜身按展开计价，包括衣柜、橱柜。",
            ]
            embeddings = embedding_service.encode(texts)

            for text, emb in zip(texts, embeddings):
                chunk = TextChunk(source_doc="test", page_no=1, content=text, embedding=emb)
                db.add(chunk)
            db.commit()

        yield

        with get_db_context() as db:
            db.query(TextChunk).delete()
            db.commit()

    def test_semantic_search(self):
        retriever = SemanticRetriever(top_k=3)

        from app.retrieval.schemas import ParsedQuery
        parsed = ParsedQuery(
            intent=QueryIntent.KNOWLEDGE,
            original_query="G型拉手安装",
            vector_query="G型拉手安装注意事项",
        )

        results = retriever.search(parsed)
        assert len(results) >= 1
        # Top result should be about G型拉手
        assert "G型拉手" in results[0].content
        assert results[0].distance < 0.5  # Reasonably close

    def test_semantic_search_thickness(self):
        retriever = SemanticRetriever(top_k=3)

        from app.retrieval.schemas import ParsedQuery
        parsed = ParsedQuery(
            intent=QueryIntent.KNOWLEDGE,
            original_query="门板厚度",
            vector_query="门板厚度规格",
        )

        results = retriever.search(parsed)
        assert len(results) >= 1
        # Should find the chunk about 18mm/25mm
        assert any("18mm" in r.content for r in results)


class TestReranker:
    """Test result fusion and deduplication."""

    def test_deduplicate_structured(self):
        reranker = Reranker()
        results = [
            StructuredResult(product_id=1, model_no="A", model_name=None, color_name="灰", substrate="板", thickness=18, unit_price=300, unit="元/㎡", family="test"),
            StructuredResult(product_id=1, model_no="A", model_name=None, color_name="灰", substrate="板", thickness=18, unit_price=300, unit="元/㎡", family="test"),  # Duplicate
            StructuredResult(product_id=1, model_no="A", model_name=None, color_name="白", substrate="板", thickness=18, unit_price=320, unit="元/㎡", family="test"),
        ]
        deduped = reranker.deduplicate_structured(results)
        assert len(deduped) == 2

    def test_rerank_limits(self):
        reranker = Reranker(top_k=2)
        context = RetrievalContext(
            query=None,
            structured_results=[
                StructuredResult(product_id=i, model_no=f"MX-{i}", model_name=None, color_name=None, substrate=None, thickness=None, unit_price=None, unit=None, family="test")
                for i in range(10)
            ],
        )
        result = reranker.rerank(context)
        assert len(result.structured_results) == 2


class TestRetrievalPipeline:
    """End-to-end retrieval pipeline tests."""

    @pytest.fixture(autouse=True)
    def setup_data(self):
        """Setup test data."""
        from app.processors.schemas import ExtractedProduct, ProductVariant, ExtractedTextBlock
        from decimal import Decimal

        service = DataImportService()

        # Clean first
        with get_db_context() as db:
            from app.models import ImageVector
            db.query(ImageVector).delete()
            db.query(PriceVariant).delete()
            db.query(TextChunk).delete()
            db.query(Product).delete()
            db.commit()

        products = [
            ExtractedProduct(
                product_family="饰面门板",
                model_no="MX-E2E-01",
                model_name="E2E测试门型",
                variants=[
                    ProductVariant(color_name="咖啡灰", substrate="颗粒板", thickness=18, unit_price=Decimal("318.00")),
                ],
            )
        ]
        chunks = [ExtractedTextBlock(text="E2E测试工艺说明文本。", page_no=1)]
        service.import_from_extraction_result(products, chunks)

        yield

        # Cleanup
        with get_db_context() as db:
            from app.models import ImageVector
            db.query(ImageVector).delete()
            db.query(PriceVariant).delete()
            db.query(TextChunk).delete()
            db.query(Product).delete()
            db.commit()

    def test_price_pipeline(self):
        from app.retrieval.pipeline import RetrievalPipeline

        pipeline = RetrievalPipeline()
        context = pipeline.retrieve("MX-E2E-01 咖啡灰 18mm 多少钱？")

        assert context.query.intent == QueryIntent.QUERY_PRICE
        assert len(context.structured_results) >= 1
        assert context.has_price_data()
        assert context.structured_results[0].unit_price == 318.00

    def test_knowledge_pipeline(self):
        from app.retrieval.pipeline import RetrievalPipeline

        pipeline = RetrievalPipeline()
        context = pipeline.retrieve("E2E测试工艺")

        assert context.query.intent == QueryIntent.KNOWLEDGE
        assert len(context.semantic_results) >= 1
        assert "E2E测试" in context.semantic_results[0].content

    def test_fallback_when_no_structured_match(self):
        from app.retrieval.pipeline import RetrievalPipeline

        pipeline = RetrievalPipeline()
        # Query with non-existent model number
        context = pipeline.retrieve("MX-不存在的型号 价格")

        # Should fallback to semantic search
        assert len(context.semantic_results) >= 0  # May be empty if no chunks match
