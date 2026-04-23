"""Visual Information Extractor (VIE) — extracts structured triplets from images.

Production: DashScope Qwen-VL-Max API (cloud)
Fallback: Local Ollama qwen2.5vl:7b
Development: Rule-based heuristic
"""

import json
import re
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, List, Optional

from app.core.logging import get_logger
from app.processors.schemas import (
    ExtractedImage,
    ExtractedPage,
    ExtractedProduct,
    ImageType,
    PageType,
    ProductVariant,
)
from app.services.models import vlm_service

logger = get_logger(__name__)


# Shared prompt for all page types
VLM_EXTRACTION_PROMPT = """你是一个家居定制行业的产品信息抽取专家。
请仔细分析这张图片，提取所有可见的产品信息，并以严格的 JSON 数组格式返回。

图片可能是以下类型之一：
- 门型/颜色对照表：包含门型照片、型号、颜色色板
- 价格表：包含颜色、基材、厚度、价格
- 吸塑门板图集：包含门型图、代号、价格
- 配件/工艺图：包含配件名称、简图、价格

每个产品对象必须包含以下字段：
- product_family: 产品族。必须从以下值中选择："墙柜一体"、"PET门板"、"吸塑门板"、"饰面门板"、"特殊工艺"
- model_no: 型号（如"MX-A01"、"WLS-08"）
- model_name: 门型名称（如"平板门型"、"G型拉手门型"）
- description: 描述/说明（可选）
- variants: 价格变体数组。如果图片中有价格信息，每个变体必须包含：
  - color_name: 颜色名称
  - color_code: 色卡编号（如有）
  - substrate: 基材（如"ENF级实木颗粒板"、"多层实木板"）
  - thickness: 厚度（mm，整数，如18、25）
  - unit_price: 单价（数字，精确到分，如318.00）
  - unit: 计价单位（如"元/㎡"、"元/米"、"元/套"）
  - remark: 备注（如非标说明，可选）

重要规则：
1. 如果图片中没有价格，variants 可以为空数组 []
2. 不要编造任何图片中没有的信息
3. 只返回 JSON 数组，不要任何 Markdown 标记或其他文字
4. 如果图片是目录/封面/无产品信息，返回空数组 []
"""


class VIEExtractor(ABC):
    """Abstract base class for Visual Information Extraction."""

    @abstractmethod
    def extract_from_page(
        self, page: ExtractedPage, price_map: Optional[Dict[str, List[ProductVariant]]] = None
    ) -> List[ExtractedProduct]:
        """Extract structured products from a single page."""
        pass


class DashScopeVIEExtractor(VIEExtractor):
    """VIE using DashScope Qwen-VL-Max API.

    This is the production implementation.
    """

    def extract_from_page(
        self, page: ExtractedPage, price_map: Optional[Dict[str, List[ProductVariant]]] = None
    ) -> List[ExtractedProduct]:
        """Extract products using Qwen-VL-Max vision model."""
        if not page.raw_image_path:
            logger.warning("No page image for VLM extraction", page_no=page.page_no)
            return []

        if page.page_type == PageType.COVER_OR_INDEX:
            return []

        try:
            raw_output = vlm_service.chat_with_image(
                image_path=page.raw_image_path,
                prompt=VLM_EXTRACTION_PROMPT,
                max_tokens=4096,
                temperature=0.1,
            )
            products = self._parse_vlm_output(raw_output, page, price_map)
            logger.info(
                "VLM extracted products",
                page_no=page.page_no,
                count=len(products),
                types=[p.product_family for p in products],
            )
            return products

        except Exception as e:
            logger.error("VLM extraction failed", error=str(e), page_no=page.page_no)
            # Fallback to rule-based
            logger.info("Falling back to rule-based VIE", page_no=page.page_no)
            fallback = RuleBasedVIEExtractor()
            return fallback.extract_from_page(page, price_map)

    def _parse_vlm_output(
        self,
        raw: str,
        page: ExtractedPage,
        price_map: Optional[Dict[str, List[ProductVariant]]],
    ) -> List[ExtractedProduct]:
        """Parse VLM JSON output into ExtractedProduct objects."""
        try:
            # Extract JSON from markdown code blocks if present
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0]

            data = json.loads(raw.strip())
            if not isinstance(data, list):
                data = [data] if data else []

            products: List[ExtractedProduct] = []
            for item in data:
                model_no = item.get("model_no", "").strip()
                if not model_no or model_no == "UNKNOWN":
                    continue

                # Build variants from VLM output, or fallback to price_map
                variants = self._build_variants(item, price_map, model_no)

                # Assign images by spatial proximity (if bbox available)
                images = self._assign_images(page, model_no, item.get("model_name", ""))

                product = ExtractedProduct(
                    product_family=item.get("product_family", "未分类"),
                    model_no=model_no,
                    model_name=item.get("model_name"),
                    description=item.get("description"),
                    images=images,
                    variants=variants,
                    source_pages=[page.page_no],
                )
                products.append(product)

            return products

        except json.JSONDecodeError as e:
            logger.error("Failed to parse VLM output", error=str(e), raw=raw[:500])
            return []

    def _build_variants(
        self,
        item: dict,
        price_map: Optional[Dict[str, List[ProductVariant]]],
        model_no: str,
    ) -> List[ProductVariant]:
        """Build variants from VLM output or cross-page price map."""
        variants: List[ProductVariant] = []

        # 1. Try VLM-extracted variants first
        for v in item.get("variants", []):
            try:
                variants.append(
                    ProductVariant(
                        color_name=v.get("color_name", "默认"),
                        color_code=v.get("color_code"),
                        substrate=v.get("substrate", "待确认"),
                        thickness=int(v.get("thickness", 18)),
                        unit_price=Decimal(str(v.get("unit_price", 0))),
                        unit=v.get("unit", "元/㎡"),
                        spec=v.get("spec", {}),
                        remark=v.get("remark"),
                    )
                )
            except (ValueError, TypeError):
                continue

        # 2. If VLM gave no variants, try cross-page price map
        if not variants and price_map and model_no in price_map:
            variants = price_map[model_no]

        return variants

    def _assign_images(
        self, page: ExtractedPage, model_no: str, model_name: str
    ) -> List[ExtractedImage]:
        """Assign page images to product based on spatial proximity and naming.

        Simple heuristic: if the page has many images (like a grid),
        we can't easily assign without exact bbox matching.
        For now, return all images on the page — image manager will dedup.
        """
        # TODO: Implement spatial matching when exact model positions are known
        return [img for img in page.images if img.bbox is not None]


class RuleBasedVIEExtractor(VIEExtractor):
    """Rule-based VIE fallback for development (no API cost)."""

    # Patterns for model numbers
    MODEL_PATTERNS = [
        re.compile(r"(MX-[A-Z]\d{2,3})"),
        re.compile(r"(WLS-\d{2,3})"),
        re.compile(r"([A-Z]{2,3}-[A-Z]?\d{2,4})"),
    ]

    # Common color names
    COLOR_KEYWORDS = [
        "咖啡灰", "象牙白", "纯黑", "胡桃木", "橡木", "樱桃木",
        "灰", "白", "黑", "红", "黄", "蓝", "绿", "木",
    ]

    PRICE_PATTERN = re.compile(r"(\d{3,4})\s*元/?(?:㎡|米|套|个)?")

    # Family inference keywords
    FAMILY_KEYWORDS = {
        "墙柜一体": ["墙柜", "衣柜", "橱柜", "柜体", "柜身", "全屋"],
        "PET门板": ["PET", "pet", "肤感", "高光"],
        "吸塑门板": ["吸塑", "模压", "PVC", "造型", "圆弧"],
        "饰面门板": ["饰面", "双饰面", "三聚氰胺"],
        "特殊工艺": ["特殊", "异形", "圆弧", "斜切", "免拉手"],
    }

    def extract_from_page(
        self, page: ExtractedPage, price_map: Optional[Dict[str, List[ProductVariant]]] = None
    ) -> List[ExtractedProduct]:
        """Extract products using text rules."""
        if page.page_type not in (
            PageType.DOOR_STYLE_COLOR_CHART,
            PageType.PRICE_TABLE,
            PageType.THERMOFORMING_DOOR,
            PageType.SPECIAL_ACCESSORY,
        ):
            return []

        products: List[ExtractedProduct] = []
        text = " ".join(b.text for b in page.text_blocks)
        family = self._infer_family(text)

        # Extract model numbers
        models = set()
        for pattern in self.MODEL_PATTERNS:
            models.update(pattern.findall(text))

        for model_no in models:
            name = self._extract_model_name(text, model_no)
            colors = self._extract_colors_near_model(text, model_no)
            prices = self._extract_prices_near_model(text, model_no)

            variants: List[ProductVariant] = []
            if prices:
                for price in prices[:3]:
                    variants.append(
                        ProductVariant(
                            color_name=colors[0] if colors else "默认",
                            substrate="待确认",
                            thickness=18,
                            unit_price=Decimal(str(price)),
                        )
                    )

            # Fallback to price_map
            if not variants and price_map and model_no in price_map:
                variants = price_map[model_no]

            product = ExtractedProduct(
                product_family=family,
                model_no=model_no,
                model_name=name,
                images=[img for img in page.images if img.bbox is not None],
                variants=variants,
                source_pages=[page.page_no],
            )
            products.append(product)

        return products

    def _infer_family(self, text: str) -> str:
        """Infer product family from page text keywords."""
        text_lower = text.lower()
        scores = {}
        for family, keywords in self.FAMILY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw.lower() in text_lower)
            scores[family] = score
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "未分类"

    def _extract_model_name(self, text: str, model_no: str) -> Optional[str]:
        """Extract name near model number, bounded to avoid crossing into other models."""
        idx = text.find(model_no)
        if idx < 0:
            return None

        # Extract a tight window around the model number
        window = text[max(0, idx - 30) : idx + len(model_no) + 30]

        # Remove other model numbers from window to avoid contamination
        for pattern in self.MODEL_PATTERNS:
            window = pattern.sub("", window)

        parts = window.split(model_no)
        if len(parts) > 1:
            candidate = parts[1].strip(" :：,，、")
            return candidate[:30] if candidate else None
        return None

    def _extract_colors_near_model(self, text: str, model_no: str) -> List[str]:
        idx = text.find(model_no)
        if idx < 0:
            return []
        window = text[max(0, idx - 100) : idx + 100]
        colors = [c for c in self.COLOR_KEYWORDS if c in window]
        return list(dict.fromkeys(colors))

    def _extract_prices_near_model(self, text: str, model_no: str) -> List[int]:
        idx = text.find(model_no)
        if idx < 0:
            return []
        window = text[max(0, idx - 200) : idx + 200]
        prices = [int(m.group(1)) for m in self.PRICE_PATTERN.finditer(window)]
        return prices
