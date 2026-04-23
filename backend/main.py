"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.products import router as products_router
from app.core.config import settings
from app.core.database import engine
from app.core.logging import configure_logging, get_logger
from app.models.base import Base

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    configure_logging(settings.LOG_LEVEL)
    logger.info("Starting up", env=settings.APP_ENV)

    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ensured")

    yield

    logger.info("Shutting down")


app = FastAPI(
    title="Multimodal RAG Catalog API",
    description="Structured Product Catalog + Multimodal RAG for PDF brochures with images, tables, and text.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files (product images)
import os
image_dir = os.path.abspath(settings.IMAGE_DIR)
os.makedirs(image_dir, exist_ok=True)
app.mount("/static/images", StaticFiles(directory=image_dir), name="images")

# API Routes
app.include_router(chat_router, prefix="/api")
app.include_router(products_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(admin_router, prefix="/api")


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/health", tags=["health"])
async def api_health_check():
    """API health check endpoint."""
    return {"status": "ok", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
