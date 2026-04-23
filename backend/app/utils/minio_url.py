"""Utilities for parsing and converting MinIO URLs."""

from urllib.parse import urlparse

from app.core.config import settings


def parse_minio_url(minio_url: str) -> tuple[str, str]:
    """Parse a minio://bucket/object URL into (bucket, object_name).

    Examples:
        >>> parse_minio_url("minio://multimodal-rag-catalog/products/door/mx-a01.png")
        ('multimodal-rag-catalog', 'products/door/mx-a01.png')
    """
    parsed = urlparse(minio_url)
    bucket = parsed.netloc
    object_name = parsed.path.lstrip("/")
    return bucket, object_name


def minio_url_to_http(minio_url: str) -> str:
    """Convert a minio:// URL to an HTTP access URL.

    Assumes MinIO console is accessible at the same endpoint.
    """
    bucket, object_name = parse_minio_url(minio_url)
    protocol = "https" if settings.MINIO_SECURE else "http"
    return f"{protocol}://{settings.MINIO_ENDPOINT}/{bucket}/{object_name}"
