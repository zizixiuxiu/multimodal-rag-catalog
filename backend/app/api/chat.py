"""Chat API — intelligent Q&A endpoint."""

import os
import tempfile
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.schemas import ChatRequest, ChatResponse, ImageSearchResponse
from app.core.config import settings
from app.core.logging import get_logger
from app.generator.generator import GenerationEngine
from app.retrieval.image_retriever import ImageRetriever

logger = get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

# Singleton services
generation_engine = GenerationEngine()
image_retriever = ImageRetriever()


@router.post("/query", response_model=ChatResponse)
async def chat_query(request: ChatRequest):
    """Process a text query and return AI answer with structured data.

    Examples:
        - "MX-A04 咖啡灰 18mm 多少钱？"
        - "G型拉手安装有什么要求？"
        - "有哪些颜色的MX-A01？"
    """
    try:
        result = generation_engine.answer(request.query, session_id=request.session_id)

        return ChatResponse(
            answer=result.answer_text,
            intent=result.intent,
            structured_data=result.structured_data,
            image_urls=result.image_urls,
            sources=result.source_chunks,
            model_no=result.structured_data["products"][0]["model_no"]
            if result.structured_data and result.structured_data.get("products")
            else None,
        )
    except Exception as e:
        logger.error("Chat query failed", error=str(e), query=request.query)
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")


@router.post("/query-with-image", response_model=ImageSearchResponse)
async def chat_with_image(
    file: UploadFile = File(..., description="Query image file (jpg/png)"),
    query: str = "",
):
    """Upload an image to find similar products in catalog.

    Args:
        file: Query image file
        query: Optional text description to refine search

    Returns:
        Similar images with product info and similarity scores
    """
    # Validate file type
    allowed = ("image/jpeg", "image/jpg", "image/png", "image/webp")
    if file.content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Only image files are supported ({', '.join(allowed)})",
        )

    # Save uploaded file to temp location
    suffix = os.path.splitext(file.filename or ".jpg")[1] or ".jpg"
    temp_path = os.path.join(tempfile.gettempdir(), f"img_query_{uuid.uuid4().hex}{suffix}")
    try:
        with open(temp_path, "wb") as f:
            f.write(await file.read())

        # Execute image retrieval
        context = generation_engine.retrieval.retrieve_by_image(
            image_path=temp_path,
            text_query=query or None,
        )

        # Build response from image_results
        similar_images = []
        for r in context.image_results:
            similar_images.append({
                "image_url": r.image_url,
                "image_type": r.image_type,
                "product_id": r.product_id,
                "similarity": round(1.0 - r.distance, 4),
            })

        return ImageSearchResponse(
            query=query,
            similar_images=similar_images,
            total=len(similar_images),
        )

    except Exception as e:
        logger.error("Image search failed", error=str(e), filename=file.filename)
        raise HTTPException(status_code=500, detail=f"Image search failed: {str(e)}")

    finally:
        # Cleanup temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)
