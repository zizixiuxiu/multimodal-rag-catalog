#!/usr/bin/env python3
"""Seed database with sample product data for API validation."""

import sys
sys.path.insert(0, "/Users/zizixiuixu/Code/kimi_code/multimodal-rag-catalog/backend")

from decimal import Decimal

from app.core.database import SessionLocal
from app.models import PriceVariant, Product, TextChunk
from app.services.models import EmbeddingService


def seed():
    db = SessionLocal()
    try:
        # Clear existing data
        db.query(TextChunk).delete()
        db.query(PriceVariant).delete()
        db.query(Product).delete()
        db.commit()
        print("Cleared existing data")

        emb = EmbeddingService()

        # ── Products ─────────────────────────────────────────────
        products_data = [
            {
                "model_no": "MX-A01",
                "name": "平板门型另配明拉手",
                "family": "饰面门板",
                "description": "简欧风格平板门，可搭配各类明装拉手",
            },
            {
                "model_no": "MX-A02",
                "name": "带LS901封边拉手门型",
                "family": "饰面门板",
                "description": "顶部集成LS901封边拉手，简约大气",
            },
            {
                "model_no": "MX-A04",
                "name": "带G型拉手门型",
                "family": "饰面门板",
                "description": "顶部G型拉手设计，现代风格",
            },
            {
                "model_no": "MX-A05",
                "name": "带WL511内嵌拉手门型",
                "family": "饰面门板",
                "description": "内嵌式WL511拉手，线条流畅",
            },
            {
                "model_no": "MX-A07",
                "name": "带LS12嵌平拉手门型",
                "family": "饰面门板",
                "description": "嵌平式LS12拉手，极简设计",
            },
            {
                "model_no": "MX-B01",
                "name": "吸塑造型门",
                "family": "吸塑门板",
                "description": "经典吸塑工艺，造型立体感强",
            },
            {
                "model_no": "MX-C01",
                "name": "PET高光门板",
                "family": "PET门板",
                "description": "PET高光表面，色泽饱满易清洁",
            },
        ]

        products = []
        for p in products_data:
            product = Product(
                model_no=p["model_no"],
                name=p["name"],
                family=p["family"],
                description=p["description"],
            )
            db.add(product)
            products.append(product)
        db.commit()
        print(f"Inserted {len(products)} products")

        # Refresh to get IDs
        for p in products:
            db.refresh(p)

        product_map = {p.model_no: p for p in products}

        # ── Price Variants ───────────────────────────────────────
        variants_data = [
            # MX-A01
            ("MX-A01", "咖啡灰", "颗粒板", 18, Decimal("318.00")),
            ("MX-A01", "咖啡灰", "多层板", 18, Decimal("358.00")),
            ("MX-A01", "象牙白", "颗粒板", 18, Decimal("298.00")),
            ("MX-A01", "象牙白", "多层板", 18, Decimal("338.00")),
            ("MX-A01", "咖啡灰", "颗粒板", 25, Decimal("368.00")),
            ("MX-A01", "咖啡灰", "多层板", 25, Decimal("408.00")),
            # MX-A02
            ("MX-A02", "深空灰", "颗粒板", 18, Decimal("328.00")),
            ("MX-A02", "深空灰", "多层板", 18, Decimal("368.00")),
            ("MX-A02", "原木色", "颗粒板", 18, Decimal("308.00")),
            # MX-A04
            ("MX-A04", "咖啡灰", "颗粒板", 18, Decimal("338.00")),
            ("MX-A04", "咖啡灰", "多层板", 18, Decimal("378.00")),
            # MX-A05
            ("MX-A05", "高级灰", "颗粒板", 18, Decimal("348.00")),
            ("MX-A05", "高级灰", "欧松板", 18, Decimal("388.00")),
            # MX-A07
            ("MX-A07", "暖白色", "颗粒板", 18, Decimal("318.00")),
            ("MX-A07", "暖白色", "多层板", 18, Decimal("358.00")),
            # MX-B01
            ("MX-B01", "经典白", "密度板", 18, Decimal("258.00")),
            ("MX-B01", "经典白", "密度板", 22, Decimal("288.00")),
            # MX-C01
            ("MX-C01", "高光白", "欧松板", 18, Decimal("458.00")),
            ("MX-C01", "高光灰", "欧松板", 18, Decimal("478.00")),
        ]

        for model_no, color, substrate, thickness, price in variants_data:
            pv = PriceVariant(
                product_id=product_map[model_no].id,
                color_name=color,
                substrate=substrate,
                thickness=thickness,
                unit_price=price,
                unit="元/㎡",
            )
            db.add(pv)
        db.commit()
        print(f"Inserted {len(variants_data)} price variants")

        # ── Text Chunks ──────────────────────────────────────────
        chunks_data = [
            {
                "content": "MX-A01 平板门型另配明拉手：简欧风格平板门，可搭配各类明装拉手。标配18mm厚度，可选颗粒板或多层板基材。",
                "source_doc": "价格手册",
                "page_no": 7,
            },
            {
                "content": "MX-A02 带LS901封边拉手门型：顶部集成LS901封边拉手，简约大气。基材可选颗粒板、多层板，厚度18mm/25mm。",
                "source_doc": "价格手册",
                "page_no": 8,
            },
            {
                "content": "MX-A04 带G型拉手门型：顶部G型拉手设计，现代风格。拉手采用铝合金材质，表面阳极氧化处理。",
                "source_doc": "价格手册",
                "page_no": 9,
            },
            {
                "content": "G型拉手安装要求：需在柜门顶部开槽，槽宽15mm，槽深8mm。安装时使用专用胶固定，24小时内避免受力。",
                "source_doc": "安装手册",
                "page_no": 15,
            },
            {
                "content": "饰面门板基材说明：颗粒板（刨花板）性价比高，稳定性好；多层板强度更高，防潮性更好；欧松板环保等级最高。",
                "source_doc": "产品手册",
                "page_no": 3,
            },
            {
                "content": "PET门板特点：PET高光表面，色泽饱满，易清洁。适合现代简约风格厨房和衣柜。",
                "source_doc": "产品手册",
                "page_no": 20,
            },
            {
                "content": "计价规则：门板按展开面积计算，单位元/㎡。包含基础五金（铰链、拉手），不含特殊五金和安装费。",
                "source_doc": "价格手册",
                "page_no": 2,
            },
            {
                "content": "MX-A05 带WL511内嵌拉手门型：内嵌式WL511拉手，线条流畅。拉手槽需工厂预制，现场不可修改。",
                "source_doc": "价格手册",
                "page_no": 10,
            },
            {
                "content": "MX-A07 带LS12嵌平拉手门型：嵌平式LS12拉手，极简设计。拉手表面与门板平齐，不凸出。",
                "source_doc": "价格手册",
                "page_no": 11,
            },
            {
                "content": "吸塑门板工艺：采用高密度板为基材，表面真空吸覆PVC膜。造型立体感强，适合欧式、美式风格。",
                "source_doc": "产品手册",
                "page_no": 25,
            },
        ]

        texts = [c["content"] for c in chunks_data]
        embeddings = emb.encode(texts)

        for i, chunk_info in enumerate(chunks_data):
            tc = TextChunk(
                content=chunk_info["content"],
                source_doc=chunk_info["source_doc"],
                page_no=chunk_info["page_no"],
                embedding=embeddings[i],
            )
            db.add(tc)
        db.commit()
        print(f"Inserted {len(chunks_data)} text chunks with embeddings")

        print("\n✅ Seed completed successfully!")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
