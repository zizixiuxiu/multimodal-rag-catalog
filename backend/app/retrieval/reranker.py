"""Reranker — cross-encoder or rule-based result fusion.

For MVP, uses simple rule-based fusion. Can be upgraded to BGE-Reranker.
"""

from typing import List

from app.core.logging import get_logger
from app.retrieval.schemas import (
    ImageResult,
    RetrievalContext,
    SemanticResult,
    StructuredResult,
)

logger = get_logger(__name__)


class Reranker:
    """Fuse and rerank results from multiple retrieval paths."""

    def __init__(self, top_k: int = 5) -> None:
        self.top_k = top_k

    def rerank(self, context: RetrievalContext) -> RetrievalContext:
        """Rerank and limit results from each source."""
        # For structured results, already exact — just limit
        context.structured_results = context.structured_results[:self.top_k]

        # For semantic results, already sorted by distance — just limit
        context.semantic_results = context.semantic_results[:self.top_k]

        # For image results, already sorted by distance — just limit
        context.image_results = context.image_results[:self.top_k]

        logger.info(
            "Reranked results",
            structured=len(context.structured_results),
            semantic=len(context.semantic_results),
            images=len(context.image_results),
        )
        return context

    def deduplicate_structured(self, results: List[StructuredResult]) -> List[StructuredResult]:
        """Remove duplicate structured results by product_id."""
        seen = set()
        deduped = []
        for r in results:
            key = (r.product_id, r.color_name, r.thickness)
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        return deduped
