"""Retrieval pipeline — orchestrates query understanding, multi-way retrieval,
reranking, and context assembly.

This is the core of the RAG system's "R" (Retrieval) component.
"""

from typing import Optional

from app.core.database import get_db_context
from app.core.logging import get_logger
from app.retrieval.image_retriever import ImageRetriever
from app.retrieval.query_understanding import QueryUnderstandingEngine
from app.retrieval.reranker import Reranker
from app.retrieval.schemas import ImageResult, ParsedQuery, QueryIntent, RetrievalContext
from app.retrieval.semantic_retriever import SemanticRetriever
from app.retrieval.structured_retriever import StructuredRetriever

logger = get_logger(__name__)


class RetrievalPipeline:
    """Main retrieval pipeline.

    Flow:
    1. Query Understanding → intent + entities
    2. Route to retrieval strategy based on intent
    3. Multi-way recall (structured + semantic + image)
    4. Rerank and assemble context
    5. Return context for generation layer
    """

    def __init__(
        self,
        query_engine: Optional[QueryUnderstandingEngine] = None,
        structured_retriever: Optional[StructuredRetriever] = None,
        semantic_retriever: Optional[SemanticRetriever] = None,
        image_retriever: Optional[ImageRetriever] = None,
        reranker: Optional[Reranker] = None,
        use_llm_for_query: bool = False,
    ) -> None:
        self.query_engine = query_engine or QueryUnderstandingEngine()
        self.structured_retriever = structured_retriever or StructuredRetriever()
        self.semantic_retriever = semantic_retriever or SemanticRetriever()
        self.image_retriever = image_retriever or ImageRetriever()
        self.reranker = reranker or Reranker()
        self.use_llm_for_query = use_llm_for_query

    def retrieve(self, query: str, session_id: Optional[str] = None) -> RetrievalContext:
        """Execute full retrieval pipeline for a user query."""
        logger.info("Retrieval started", query=query, session_id=session_id)

        # Stage 1: Query Understanding (with rewriting + multi-turn context)
        parsed = self.query_engine.parse(query, session_id=session_id, use_llm=self.use_llm_for_query)
        logger.info("Query parsed", intent=parsed.intent.value, entities=parsed.entities, rewritten=parsed.vector_query)

        context = RetrievalContext(query=parsed)

        with get_db_context() as db:
            # Stage 2: Multi-way Retrieval based on intent
            if parsed.intent.value in ("query_price", "compare", "list_products"):
                # PRIMARY: Structured query for exact data
                context.structured_results = self.structured_retriever.search(parsed, db=db)

                # Compute area / total price when dimensions are provided
                if "dimensions" in parsed.entities and context.structured_results:
                    dims = parsed.entities["dimensions"]
                    length_mm = float(dims.get("length", 0))
                    width_mm = float(dims.get("width", 0))
                    if length_mm > 0 and width_mm > 0:
                        area = (length_mm * width_mm) / 1_000_000.0  # mm² → ㎡
                        for r in context.structured_results:
                            r.area = round(area, 4)
                            if r.unit_price is not None:
                                r.total_price = round(float(r.unit_price) * area, 2)
                        logger.info(
                            "Area computed",
                            length=length_mm,
                            width=width_mm,
                            area=area,
                            results=len(context.structured_results),
                        )

                # FALLBACK: Semantic search if structured returns nothing
                if not context.structured_results:
                    logger.info("Structured search empty, falling back to semantic")
                    context.semantic_results = self.semantic_retriever.search(parsed, db=db)

            elif parsed.intent.value == "knowledge":
                # PRIMARY: Semantic search for knowledge
                context.semantic_results = self.semantic_retriever.search(parsed, db=db)

                # FALLBACK: Structured search for related products
                context.structured_results = self.structured_retriever.search(parsed, db=db)

            elif parsed.intent.value == "image_search":
                # Image search intent: text-to-image via CLIP
                image_results = self.image_retriever.search_by_text(
                    parsed.original_query, db=db, top_k=settings.TOP_K_RETRIEVAL
                )
                context.image_results = [
                    ImageResult(
                        image_id=r.image_id,
                        image_url=r.image_url,
                        image_type=r.image_type or "",
                        product_id=r.product_id,
                        distance=1.0 - r.similarity,
                    )
                    for r in image_results
                ]
                # Fallback: also do semantic search for context
                context.semantic_results = self.semantic_retriever.search(parsed, db=db)

            else:
                # Unknown intent: try both
                context.structured_results = self.structured_retriever.search(parsed, db=db)
                context.semantic_results = self.semantic_retriever.search(parsed, db=db)

            # Stage 3: Rerank
            context = self.reranker.rerank(context)

        logger.info(
            "Retrieval complete",
            intent=parsed.intent.value,
            structured=len(context.structured_results),
            semantic=len(context.semantic_results),
            has_price=context.has_price_data(),
        )
        return context

    def retrieve_by_image(self, image_path: str, text_query: Optional[str] = None) -> RetrievalContext:
        """Retrieve similar images and related products by uploaded image.

        Args:
            image_path: Local path to uploaded query image
            text_query: Optional text description to combine with image

        Returns:
            RetrievalContext with image_results and optional semantic_results
        """
        logger.info("Image retrieval started", image_path=image_path, text_query=text_query)

        parsed = ParsedQuery(
            intent=QueryIntent.IMAGE_SEARCH,
            original_query=text_query or "image search",
            entities={},
        )
        context = RetrievalContext(query=parsed)

        with get_db_context() as db:
            # Stage 1: Image-to-image similarity search
            image_results = self.image_retriever.search_by_image(
                image_path, db=db, top_k=settings.TOP_K_RETRIEVAL
            )
            context.image_results = [
                ImageResult(
                    image_id=r.image_id,
                    image_url=r.image_url,
                    image_type=r.image_type or "",
                    product_id=r.product_id,
                    distance=1.0 - r.similarity,
                )
                for r in image_results
            ]

            # Stage 2: Optional text semantic search for additional context
            if text_query:
                context.semantic_results = self.semantic_retriever.search(parsed, db=db)

        logger.info(
            "Image retrieval complete",
            images=len(context.image_results),
            semantic=len(context.semantic_results),
        )
        return context

    def retrieve_price(
        self,
        model_no: Optional[str] = None,
        color_name: Optional[str] = None,
        thickness: Optional[int] = None,
        substrate: Optional[str] = None,
    ) -> RetrievalContext:
        """Direct price retrieval without query parsing.

        Used when entities are already known (e.g. from frontend filters).
        """
        parsed = ParsedQuery(
            intent=ParsedQuery.intent.__class__("query_price"),
            original_query=f"{model_no} {color_name} {thickness}mm",
            entities={
                "model_no": model_no,
                "color_name": color_name,
                "thickness": thickness,
                "substrate": substrate,
            },
            sql_filters={
                "table": "price_variants",
                "conditions": {
                    k: v for k, v in {
                        "model_no": model_no,
                        "color_name": color_name,
                        "thickness": thickness,
                        "substrate": substrate,
                    }.items() if v is not None
                },
            },
        )

        context = RetrievalContext(query=parsed)
        with get_db_context() as db:
            context.structured_results = self.structured_retriever.search(parsed, db=db)
            context = self.reranker.rerank(context)

        return context
