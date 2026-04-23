"""Generation layer schemas — response structures for the LLM output."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional


@dataclass
class GenerationResult:
    """Final output of the generation layer."""

    answer_text: str
    intent: str = ""
    structured_data: Optional[Dict[str, Any]] = None
    image_urls: List[str] = field(default_factory=list)
    source_chunks: List[str] = field(default_factory=list)
    source_pages: List[int] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Convert to markdown for frontend rendering."""
        parts = [self.answer_text]

        if self.image_urls:
            parts.append("\n\n**相关产品图片：**")
            for url in self.image_urls:
                parts.append(f"\n![产品图片]({url})")

        return "\n".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "answer_text": self.answer_text,
            "intent": self.intent,
            "structured_data": self.structured_data,
            "image_urls": self.image_urls,
            "source_chunks": self.source_chunks,
            "source_pages": list(set(self.source_pages)),
        }
