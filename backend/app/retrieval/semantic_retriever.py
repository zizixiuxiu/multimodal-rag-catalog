"""Semantic retriever — vector similarity search via pgvector (BGE-M3).

Used for:
- Knowledge/process description queries
- Product description semantic matching
- Fallback when structured query returns no results
"""

from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db_context
from app.core.logging import get_logger
from app.retrieval.schemas import ParsedQuery, SemanticResult
from app.services.models import embedding_service

logger = get_logger(__name__)


class SemanticRetriever:
    """Retrieve relevant text chunks via vector similarity search."""

    def __init__(self, top_k: int = 5) -> None:
        self.top_k = top_k

    def search(self, parsed: ParsedQuery, db: Optional[Session] = None) -> List[SemanticResult]:
        """Search text chunks by semantic similarity."""
        should_close = db is None
        if db is None:
            context = get_db_context()
            db = context.__enter__()

        try:
            query_text = parsed.vector_query or parsed.original_query
            query_embedding = embedding_service.encode_single(query_text)

            # pgvector cosine distance search
            # Using <=> operator (cosine distance = 1 - cosine_similarity)
            sql = text("""
                SELECT id, content, source_doc, page_no,
                       embedding <=> :vec AS distance
                FROM text_chunks
                ORDER BY embedding <=> :vec
                LIMIT :limit
            """)

            rows = db.execute(sql, {
                "vec": str(query_embedding),
                "limit": self.top_k,
            }).fetchall()

            results = [
                SemanticResult(
                    chunk_id=row.id,
                    content=row.content,
                    source_doc=row.source_doc,
                    page_no=row.page_no,
                    distance=float(row.distance),
                )
                for row in rows
            ]

            logger.info(
                "Semantic search",
                query=query_text[:50],
                results=len(results),
                best_distance=results[0].distance if results else None,
            )
            return results

        finally:
            if should_close:
                context.__exit__(None, None, None)
