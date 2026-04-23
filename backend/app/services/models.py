"""Model services — Embedding, VLM, LLM wrappers."""

import base64
import json
import os
from typing import List, Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    """Text embedding service using BGE-M3 (or fallback)."""

    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _load_model(self):
        """Lazy-load the embedding model."""
        if self._model is not None:
            return self._model

        from sentence_transformers import SentenceTransformer

        # Use local BGE-M3 from previous project, fallback to HuggingFace name
        local_model_path = "/Users/zizixiuixu/.cache/huggingface/hub/models--BAAI--bge-m3-local"
        model_name = local_model_path if os.path.exists(local_model_path) else settings.TEXT_EMBEDDING_MODEL

        logger.info("Loading embedding model", model=model_name)
        self._model = SentenceTransformer(
            model_name,
            device=settings.TEXT_EMBEDDING_DEVICE,
        )
        logger.info("Embedding model loaded", dim=self._model.get_sentence_embedding_dimension())
        return self._model

    def encode(self, texts: List[str], batch_size: Optional[int] = None) -> List[List[float]]:
        """Encode texts to embedding vectors."""
        model = self._load_model()
        batch_size = batch_size or settings.TEXT_EMBEDDING_BATCH_SIZE

        vectors = model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def encode_single(self, text: str) -> List[float]:
        """Encode a single text."""
        return self.encode([text])[0]

    @property
    def dimension(self) -> int:
        model = self._load_model()
        return model.get_sentence_embedding_dimension()


class VLMService:
    """Vision-Language Model service using DashScope (Qwen-VL-Max).

    Falls back to local Ollama if DashScope is unavailable.
    """

    def __init__(self):
        self.api_key = settings.DASHSCOPE_API_KEY
        self.base_url = settings.DASHSCOPE_BASE_URL
        self.model = "qwen-vl-max-latest"
        self._client = None

    def _get_client(self):
        """Lazy-load OpenAI-compatible client for DashScope."""
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._client

    def chat_with_image(
        self,
        image_path: str,
        prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> str:
        """Send an image + text prompt to VLM and get response."""
        # Read and encode image
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_b64}"
                                },
                            },
                        ],
                    }
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content

        except Exception as e:
            logger.error("DashScope VLM failed, trying Ollama fallback", error=str(e))
            return self._ollama_fallback(image_path, prompt, max_tokens, temperature)

    def _ollama_fallback(
        self, image_path: str, prompt: str, max_tokens: int, temperature: float
    ) -> str:
        """Fallback to local Ollama Qwen2.5-VL."""
        import requests

        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()

        try:
            resp = requests.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": settings.OLLAMA_VLM_MODEL,
                    "prompt": prompt,
                    "images": [image_b64],
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
        except Exception as e2:
            logger.error("Ollama fallback also failed", error=str(e2))
            raise RuntimeError(f"VLM unavailable: {e2}") from e2


class LLMService:
    """Text LLM service using DashScope (Qwen-Max/Plus).

    Falls back to local Ollama if DashScope is unavailable.
    """

    def __init__(self):
        self.api_key = settings.DASHSCOPE_API_KEY
        self.base_url = settings.DASHSCOPE_BASE_URL
        self.model = "qwen-max-latest"
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def chat(
        self,
        messages: List[dict],
        max_tokens: int = 2048,
        temperature: float = 0.3,
        json_mode: bool = False,
        tools: Optional[List[dict]] = None,
    ) -> tuple:
        """Send messages to LLM and get response.

        Returns:
            (content: str, tool_calls: list) — content may be empty if tool_calls present
        """
        try:
            client = self._get_client()
            kwargs = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            response = client.chat.completions.create(**kwargs)
            msg = response.choices[0].message
            content = msg.content or ""
            tool_calls = getattr(msg, "tool_calls", None) or []
            return content, tool_calls

        except Exception as e:
            logger.error("DashScope LLM failed, trying Ollama fallback", error=str(e))
            content = self._ollama_fallback(messages, max_tokens, temperature)
            return content, []

    def _ollama_fallback(self, messages: List[dict], max_tokens: int, temperature: float) -> str:
        """Fallback to local Ollama."""
        import requests

        prompt = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
            for m in messages
        )

        try:
            resp = requests.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": settings.OLLAMA_LLM_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
        except Exception as e2:
            logger.error("Ollama fallback also failed", error=str(e2))
            raise RuntimeError(f"LLM unavailable: {e2}") from e2


# Singleton instances
embedding_service = EmbeddingService()
vlm_service = VLMService()
llm_service = LLMService()
