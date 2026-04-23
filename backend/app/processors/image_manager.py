"""Image asset manager — handles extraction, naming, and storage of product images."""

from pathlib import Path
from typing import List, Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.processors.schemas import ExtractedImage, ImageType
from app.services.storage import storage_service

logger = get_logger(__name__)


class ImageAssetManager:
    """Manages product images extracted from PDFs.

    Responsibilities:
    - Assign consistent IDs to images
    - Upload to object storage (MinIO/S3 or local filesystem)
    - Track image types (door_style, color_chip, etc.)
    - Generate accessible URLs for frontend display
    """

    def __init__(self) -> None:
        self.local_dir = Path(settings.IMAGE_DIR)
        self.local_dir.mkdir(parents=True, exist_ok=True)

    def process_images(
        self,
        images: List[ExtractedImage],
        product_family: Optional[str] = None,
        model_no: Optional[str] = None,
    ) -> List[ExtractedImage]:
        """Process a batch of images: classify, rename, and upload."""
        processed: List[ExtractedImage] = []

        for img in images:
            # Classify image type if unknown
            if img.image_type == ImageType.UNKNOWN:
                img.image_type = self._classify_image(img, product_family)

            # Generate canonical filename
            new_name = self._generate_filename(img, product_family, model_no)
            new_path = self.local_dir / new_name

            # Move/rename file if needed
            if Path(img.local_path) != new_path:
                new_path.parent.mkdir(parents=True, exist_ok=True)
                src = Path(img.local_path)
                if src.exists():
                    src.rename(new_path)
                else:
                    logger.warning("Source image not found, skipping rename", src=str(src))
                img.local_path = str(new_path)
                # Keep image_id clean — just the base name without prefixes
                img.image_id = Path(new_name).stem

            # Upload to storage
            try:
                with open(img.local_path, "rb") as f:
                    data = f.read()
                url = storage_service.upload_file(new_name, data, content_type="image/png")
                img.storage_url = url
            except Exception as e:
                logger.warning("Failed to upload image", error=str(e), image_id=img.image_id)
                img.storage_url = f"file://{img.local_path}"

            processed.append(img)

        return processed

    def _classify_image(
        self, img: ExtractedImage, product_family: Optional[str] = None
    ) -> ImageType:
        """Classify image type based on filename, context, and content heuristics."""
        filename = Path(img.local_path).name.lower()

        # Filename-based classification
        if any(kw in filename for kw in ["color", "chip", "色板", "颜色", "色卡"]):
            return ImageType.COLOR_CHIP
        if any(kw in filename for kw in ["door", "门型", "门板", "mx-"]):
            return ImageType.DOOR_STYLE
        if any(kw in filename for kw in ["effect", "效果", "场景"]):
            return ImageType.EFFECT
        if any(kw in filename for kw in ["accessory", "配件", "拉手", "铰链", "五金"]):
            return ImageType.ACCESSORY
        if any(kw in filename for kw in ["process", "工艺", "简图"]):
            return ImageType.PROCESS_DIAGRAM

        # Context-based classification
        if product_family:
            pf = product_family.lower()
            if any(kw in pf for kw in ["吸塑", "模压", "thermo"]):
                return ImageType.DOOR_STYLE
            if any(kw in pf for kw in ["pet", "门板"]):
                return ImageType.DOOR_STYLE

        return ImageType.UNKNOWN

    def _generate_filename(
        self,
        img: ExtractedImage,
        product_family: Optional[str] = None,
        model_no: Optional[str] = None,
    ) -> str:
        """Generate a canonical filename for the image.

        Format: {family}/{model_no}/{type}_{base_id}.{ext}
        """
        parts = []

        if product_family:
            parts.append(self._sanitize(product_family))

        if model_no:
            parts.append(self._sanitize(model_no))

        type_prefix = img.image_type.value if img.image_type != ImageType.UNKNOWN else "img"
        # Use only the basename of image_id, strip any existing prefixes
        base_id = Path(img.image_id).name
        # Prevent prefix stacking: if base_id already starts with {type_prefix}_
        if base_id.startswith(f"{type_prefix}_"):
            filename = f"{base_id}.png"
        else:
            filename = f"{type_prefix}_{base_id}.png"
        parts.append(filename)

        return "/".join(parts)

    def _sanitize(self, name: str) -> str:
        """Sanitize a string for use in filenames."""
        return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
