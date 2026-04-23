"""Storage service — supports MinIO or local filesystem fallback."""

import io
import os
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class LocalStorage:
    """Fallback local filesystem storage when MinIO is unavailable."""

    def __init__(self, base_dir: str = "./data/images") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.bucket_name = settings.MINIO_BUCKET_NAME

    def upload_file(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        path = self.base_dir / object_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        # Return web-accessible URL for frontend static file serving
        url = f"/static/images/{quote(object_name)}"
        logger.info("Saved file locally", object_name=object_name, path=str(path))
        return url

    def get_file(self, object_name: str) -> Optional[bytes]:
        path = self.base_dir / object_name
        if path.exists():
            return path.read_bytes()
        return None

    def get_presigned_url(self, object_name: str, expires: int = 3600) -> Optional[str]:
        path = self.base_dir / object_name
        if path.exists():
            return f"/static/images/{quote(object_name)}"
        return None

    def delete_file(self, object_name: str) -> bool:
        path = self.base_dir / object_name
        if path.exists():
            path.unlink()
            return True
        return False

    def list_objects(self, prefix: str = ""):
        base = self.base_dir / prefix
        if not base.exists():
            return []
        return list(base.rglob("*"))


class MinIOStorage:
    """MinIO object storage wrapper."""

    def __init__(self) -> None:
        from minio import Minio
        from minio.error import S3Error

        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self.bucket_name = settings.MINIO_BUCKET_NAME
        self.S3Error = S3Error
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket_name):
            self.client.make_bucket(self.bucket_name)
            logger.info("Created bucket", bucket=self.bucket_name)

    def upload_file(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        try:
            self.client.put_object(
                self.bucket_name,
                object_name,
                io.BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
            url = f"minio://{self.bucket_name}/{object_name}"
            logger.info("Uploaded file", object_name=object_name, url=url)
            return url
        except self.S3Error as e:
            logger.error("Failed to upload file", error=str(e), object_name=object_name)
            raise

    def get_file(self, object_name: str) -> Optional[bytes]:
        try:
            response = self.client.get_object(self.bucket_name, object_name)
            return response.read()
        except self.S3Error as e:
            logger.error("Failed to get file", error=str(e), object_name=object_name)
            return None

    def get_presigned_url(self, object_name: str, expires: int = 3600) -> Optional[str]:
        try:
            return self.client.presigned_get_object(self.bucket_name, object_name, expires=expires)
        except self.S3Error as e:
            logger.error("Failed to generate presigned URL", error=str(e), object_name=object_name)
            return None

    def delete_file(self, object_name: str) -> bool:
        try:
            self.client.remove_object(self.bucket_name, object_name)
            logger.info("Deleted file", object_name=object_name)
            return True
        except self.S3Error as e:
            logger.error("Failed to delete file", error=str(e), object_name=object_name)
            return False

    def list_objects(self, prefix: str = ""):
        return list(self.client.list_objects(self.bucket_name, prefix=prefix, recursive=True))


def _create_storage():
    """Try MinIO first, fall back to local filesystem."""
    try:
        storage = MinIOStorage()
        logger.info("Using MinIO storage")
        return storage
    except Exception as e:
        logger.warning("MinIO unavailable, using local filesystem fallback", error=str(e))
        return LocalStorage(base_dir=settings.IMAGE_DIR)


# Singleton instance
storage_service = _create_storage()
