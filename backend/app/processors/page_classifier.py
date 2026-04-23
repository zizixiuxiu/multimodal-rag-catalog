"""Page classifier — identifies page type from content heuristics."""

import re
from typing import List

from app.core.logging import get_logger
from app.processors.schemas import ExtractedPage, ExtractedTextBlock, PageType

logger = get_logger(__name__)


class PageClassifier:
    """Classify PDF pages into types based on content heuristics.

    Uses keyword matching and structural cues. Can be upgraded to
    a fine-tuned text/image classifier for production.
    """

    # Keywords for each page type (Chinese + English variants)
    KEYWORDS = {
        PageType.DOOR_STYLE_COLOR_CHART: [
            "门型", "颜色", "色板", "门板", "柜体", "饰面", "代号",
            "door style", "color chart", "色卡",
        ],
        PageType.PRICE_TABLE: [
            "价格", "报价", "单价", "零售价", "元/㎡", "元/米", "元/套",
            "price", "unit price", "零售价", "大格",
        ],
        PageType.PROCESS_DESCRIPTION: [
            "工艺", "计价", "说明", "规则", "非标", "标准", "备注",
            "process", "pricing", "rule", "note",
        ],
        PageType.SPECIAL_ACCESSORY: [
            "配件", "拉手", "铰链", "滑轨", "五金", "特殊工艺",
            "accessory", "hardware", "handle", "hinge",
        ],
        PageType.THERMOFORMING_DOOR: [
            "吸塑", "模压", "PVC", "造型",
            "thermoforming", "vacuum", "membrane",
        ],
        PageType.COVER_OR_INDEX: [
            "目录", "封面", "封底", "索引", "contents", "index", "catalog",
        ],
    }

    # Minimum score to classify (out of keyword matches)
    THRESHOLD = 2

    def classify(self, page: ExtractedPage) -> PageType:
        """Classify a single page."""
        text = self._concat_text(page.text_blocks)
        scores = self._score_page(text)

        best_type = PageType.UNKNOWN
        best_score = 0

        for pt, score in scores.items():
            if score > best_score and score >= self.THRESHOLD:
                best_type = pt
                best_score = score

        # Additional heuristics
        best_type = self._apply_heuristics(page, best_type, text)

        page.page_type = best_type
        logger.debug("Classified page", page_no=page.page_no, type=best_type.value, score=best_score)
        return best_type

    def classify_all(self, pages: List[ExtractedPage]) -> List[ExtractedPage]:
        """Classify all pages in a document."""
        for page in pages:
            self.classify(page)
        return pages

    def _concat_text(self, blocks: List[ExtractedTextBlock]) -> str:
        """Concatenate all text from blocks."""
        return " ".join(b.text for b in blocks)

    def _score_page(self, text: str) -> dict:
        """Score each page type by keyword matches."""
        text_lower = text.lower()
        scores = {}

        for page_type, keywords in self.KEYWORDS.items():
            score = sum(1 for kw in keywords if kw.lower() in text_lower)
            scores[page_type] = score

        return scores

    def _apply_heuristics(
        self, page: ExtractedPage, current_type: PageType, text: str
    ) -> PageType:
        """Apply additional heuristics to refine classification."""

        # Price table: has many numbers with 元 and table-like structure
        if current_type == PageType.UNKNOWN:
            yuan_count = len(re.findall(r"\d+\.?\d*\s*元", text))
            if yuan_count >= 5:
                return PageType.PRICE_TABLE

        # Door style chart: many model numbers like MX-A01, MX-A02
        model_pattern = re.compile(r"[A-Z]{1,3}-?[A-Z]?\d{2,4}")
        if model_pattern.findall(text) and len(page.images) >= 3:
            if current_type == PageType.UNKNOWN:
                return PageType.DOOR_STYLE_COLOR_CHART

        # First/last few pages are likely cover/index
        if page.page_no <= 3 or page.page_no >= 35:  # heuristic for typical brochure
            if current_type == PageType.UNKNOWN and len(text) < 200:
                return PageType.COVER_OR_INDEX

        return current_type
