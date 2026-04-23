"""Image Retriever — CLIP-based image similarity search.

Supports:
- Image-to-image: upload image → find similar catalog images
- Text-to-image: text query → find matching images (via CLIP text encoder)
"""

from typing import List, Optional

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models import ImageVector
from app.services.clip_service import CLIPService

logger = get_logger(__name__)


class ImageSearchResult:
    """Result from image similarity search."""

    def __init__(
        self,
        image_id: int,
        product_id: int,
        image_url: str,
        image_type: Optional[str],
        similarity: float,
    ):
        self.image_id = image_id
        self.product_id = product_id
        self.image_url = image_url
        self.image_type = image_type
        self.similarity = similarity


class ImageRetriever:
    """Retrieve similar images using CLIP vector similarity."""

    def __init__(self, clip_service: Optional[CLIPService] = None):
        self.clip = clip_service or CLIPService()

    def search_by_image(
        self,
        image_path: str,
        db: Session,
        top_k: int = 5,
    ) -> List[ImageSearchResult]:
        """Find images similar to the uploaded query image.

        Args:
            image_path: Path to query image file
            db: SQLAlchemy session
            top_k: Number of results to return

        Returns:
            List of ImageSearchResult sorted by similarity (desc)
        """
        query_vec = self.clip.encode_image(image_path)
        return self._vector_search(query_vec, db, top_k)

    def search_by_text(
        self,
        text_query: str,
        db: Session,
        top_k: int = 5,
    ) -> List[ImageSearchResult]:
        """Find images matching a text description (text-to-image).

        Args:
            text_query: Text description (e.g. "白色平板门")
            db: SQLAlchemy session
            top_k: Number of results to return

        Returns:
            List of ImageSearchResult sorted by similarity (desc)
        """
        query_vec = self.clip.encode_text(text_query)
        return self._vector_search(query_vec, db, top_k)

    def _vector_search(
        self,
        query_vec: np.ndarray,
        db: Session,
        top_k: int,
    ) -> List[ImageSearchResult]:
        """Execute pgvector similarity search against image_vectors table."""
        dim = settings.VECTOR_DIMENSION_IMAGE
        vec_list = query_vec.tolist()

        # Use pgvector <=> operator (cosine distance on normalized vectors = 1 - similarity)
        sql = text(f"""
            SELECT id, product_id, image_url, image_type,
                   clip_embedding <=> :vec::vector({dim}) AS distance
            FROM image_vectors
            WHERE clip_embedding IS NOT NULL
            ORDER BY clip_embedding <=> :vec::vector({dim})
            LIMIT :limit
        """)

        rows = db.execute(sql, {"vec": str(vec_list), "limit": top_k}).fetchall()

        results = []
        for row in rows:
            # Convert cosine distance back to similarity (both normalized)
            similarity = 1.0 - float(row.distance)
            results.append(
                ImageSearchResult(
                    image_id=row.id,
                    product_id=row.product_id,
                    image_url=row.image_url,
                    image_type=row.image_type,
                    similarity=round(similarity, 4),
                )
            )

        logger.info(
            "Image search complete",
            results=len(results),
            best_similarity=results[0].similarity if results else None,
        )
        return results
