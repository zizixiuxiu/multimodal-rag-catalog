"""CLIP Service — multimodal image + text embedding.

Uses Hugging Face transformers CLIP for unified vision-language embeddings.
Supports:
- Image encoding (for image-to-image similarity search)
- Text encoding (for text-to-image search)
"""

from typing import List, Optional, Union

import numpy as np
import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class CLIPService:
    """Singleton CLIP service for image and text encoding."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._model = None
            cls._instance._processor = None
        return cls._instance

    def _load(self):
        """Lazy-load CLIP model and processor."""
        if self._model is not None:
            return

        model_name = settings.IMAGE_EMBEDDING_MODEL
        logger.info("Loading CLIP model", model=model_name)

        self._processor = CLIPProcessor.from_pretrained(model_name)
        self._model = CLIPModel.from_pretrained(model_name)
        self._model.eval()

        device = settings.TEXT_EMBEDDING_DEVICE
        if device == "cuda" and torch.cuda.is_available():
            self._model = self._model.to("cuda")
        elif device == "mps" and torch.backends.mps.is_available():
            self._model = self._model.to("mps")

        logger.info("CLIP model loaded", model=model_name, device=device)

    # ── Public API ─────────────────────────────────────────────

    def encode_image(self, image_input: Union[str, Image.Image], normalize: bool = True) -> np.ndarray:
        """Encode a single image to CLIP vector.

        Args:
            image_input: Path string or PIL Image
            normalize: Whether to L2-normalize the vector

        Returns:
            1-D numpy array of shape (VECTOR_DIMENSION_IMAGE,)
        """
        self._load()

        if isinstance(image_input, str):
            image = Image.open(image_input).convert("RGB")
        else:
            image = image_input.convert("RGB")

        inputs = self._processor(images=image, return_tensors="pt")
        device = next(self._model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            image_features = self._model.get_image_features(**inputs)

        vector = image_features.cpu().numpy().flatten()

        if normalize:
            norm = np.linalg.norm(vector)
            if norm > 0:
                vector = vector / norm

        return vector

    def encode_images(self, image_inputs: List[Union[str, Image.Image]], normalize: bool = True) -> np.ndarray:
        """Encode multiple images in batch.

        Returns:
            2-D numpy array of shape (n_images, VECTOR_DIMENSION_IMAGE)
        """
        self._load()
        images = []
        for inp in image_inputs:
            if isinstance(inp, str):
                images.append(Image.open(inp).convert("RGB"))
            else:
                images.append(inp.convert("RGB"))

        inputs = self._processor(images=images, return_tensors="pt", padding=True)
        device = next(self._model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            image_features = self._model.get_image_features(**inputs)

        vectors = image_features.cpu().numpy()

        if normalize:
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            vectors = np.where(norms > 0, vectors / norms, vectors)

        return vectors

    def encode_text(self, texts: Union[str, List[str]], normalize: bool = True) -> np.ndarray:
        """Encode text query for text-to-image search.

        Returns:
            1-D or 2-D numpy array of CLIP text embeddings
        """
        self._load()

        if isinstance(texts, str):
            texts = [texts]
            return_1d = True
        else:
            return_1d = False

        inputs = self._processor(text=texts, return_tensors="pt", padding=True, truncation=True)
        device = next(self._model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            text_features = self._model.get_text_features(**inputs)

        vectors = text_features.cpu().numpy()

        if normalize:
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            vectors = np.where(norms > 0, vectors / norms, vectors)

        if return_1d:
            return vectors[0]
        return vectors

    def compute_similarity(self, vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        """Compute cosine similarity between two normalized vectors."""
        return float(np.dot(vec_a, vec_b))
