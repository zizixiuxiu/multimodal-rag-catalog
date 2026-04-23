"""Application configuration using Pydantic Settings."""

import os
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env from project root (relative to this file: backend/app/core/ -> ../../../.env)
_env_path = Path(__file__).resolve().parents[3] / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=True)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # App
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = True

    # Database
    DATABASE_URL: PostgresDsn = "postgresql+psycopg2://postgres:postgres@localhost:5433/multimodal_rag"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_url(cls, v: Optional[str]) -> str:
        if isinstance(v, str):
            return v
        raise ValueError("DATABASE_URL must be a string")

    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET_NAME: str = "multimodal-rag-catalog"
    MINIO_SECURE: bool = False

    # DashScope (Aliyun) — Primary
    DASHSCOPE_API_KEY: Optional[str] = None
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # Ollama (Local Fallback)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_VLM_MODEL: str = "qwen2.5vl:7b"
    OLLAMA_LLM_MODEL: str = "qwen2.5:14b"

    # Other LLM
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    # Embedding Models
    TEXT_EMBEDDING_MODEL: str = "BAAI/bge-m3"
    TEXT_EMBEDDING_DEVICE: str = "cpu"
    TEXT_EMBEDDING_BATCH_SIZE: int = 8
    IMAGE_EMBEDDING_MODEL: str = "openai/clip-vit-base-patch32"

    # Reranker
    RERANKER_MODEL: str = "BAAI/bge-reranker-large"

    # Paths
    UPLOAD_DIR: str = "./data/pdfs"
    EXTRACTED_DIR: str = "./data/extracted"
    IMAGE_DIR: str = "./data/images"

    # Search
    VECTOR_DIMENSION_TEXT: int = 1024
    VECTOR_DIMENSION_IMAGE: int = 512
    TOP_K_RETRIEVAL: int = 10
    TOP_K_RERANK: int = 5


settings = Settings()
