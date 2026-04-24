"""
Import 墙柜一体 price table from text_chunks into structured DB.

Parses Markdown tables from pages 17-19 of the PDF, cleans color names,
and creates PriceVariant records with component_type (柜身/门板/护墙).
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.models.knowledge import TextChunk
from app.models.product import PriceVariant, Product


def clean_color_name(name: str) -> str:
    """Preserve special markers (█=同色套装门, ☆=2420规格, S=表面效果不同).
    Only strip whitespace and HTML tags.
    """
    name = name.replace("<br>", "").replace("\n", "").strip()
    return name


def parse_markdown_table(content: str):
    """Parse markdown table rows from text chunk content."""
    lines = content.splitlines()
    rows = []
    in_table = False
    for line in lines:
        line = line.strip()
        if line.startswith("|") and "序号" in line and "颜色名称" in line:
            in_table = True
            continue
        if in_table and line.startswith("|") and "---" not in line:
            rows.append(line)
        elif in_table and not line.startswith("|") and line:
            # Table ended
            break
    return rows


def parse_table_row(row_text: str):
    """Parse a single markdown table row into cells."""
    cells = [c.strip() for c in row_text.strip("|").split("|")]
    return cells


def extract_min_charge_area(tech_note: str) -> dict:
    """Extract minimum charge area rules from tech note."""
    rules = {}
    # 门板/护墙/见光板 不足0.2
    if "门板和护墙及见光板单件不足0.2平方按0.2平方计价" in tech_note:
        rules["门板"] = 0.2
        rules["护墙"] = 0.2
        rules["见光板"] = 0.2
    # 抽面 不足0.1
    if "抽面单件不足0.1平方按0.1平方计价" in tech_note:
        rules["抽面"] = 0.1
    return rules


def extract_applicable_models(tech_note: str) -> list:
    """Extract applicable door models like MX-A01 from tech note."""
    match = re.search(r"可做门型[：:]\s*([A-Z\d、,，\s\-\(\)（）]+)", tech_note)
    if not match:
        return None
    text = match.group(1)
    # Split by Chinese comma /顿号
    parts = re.split(r"[、,，\s]", text)
    models = []
    for p in parts:
        p = p.strip()
        # Normalize to MX-A01 format
        if p.startswith("MX-"):
            models.append(p)
        elif re.match(r"^[A-Z]\d{2,3}[A-Z]?$", p):
            models.append(f"MX-{p}")
        elif re.match(r"^A\d{2,3}[A-Z]?$", p):
            models.append(f"MX-{p}")
    return models if models else None


def import_wall_cabinet_prices():
    db = SessionLocal()

    # 1. Create or get the "墙柜一体" product
    product = db.query(Product).filter(Product.model_no == "墙柜一体").first()
    if not product:
        product = Product(
            family="墙柜一体",
            model_no="墙柜一体",
            name="墙柜一体基础板材",
            description="墙柜一体价格表：柜身、门板、护墙基础板材价格",
            category="柜体",
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        print(f"Created product: id={product.id}, model_no={product.model_no}")
    else:
        print(f"Using existing product: id={product.id}")

    # 2. Fetch text chunks for pages 17-19
    chunks = (
        db.query(TextChunk)
        .filter(TextChunk.source_doc.contains("墙柜"))
        .filter(TextChunk.page_no.in_([17, 18, 19]))
        .order_by(TextChunk.page_no)
        .all()
    )

    # Group by page_no
    pages = {}
    for c in chunks:
        pages.setdefault(c.page_no, []).append(c)

    # 3. Parse each page
    all_variants = []
    current_substrate = ""
    current_tech_note = ""
    min_area_rules = {}
    applicable_models = None

    for page_no in sorted(pages.keys()):
        for chunk in pages[page_no]:
            rows = parse_markdown_table(chunk.content)
            for row in rows:
                cells = parse_table_row(row)
                if len(cells) < 9:
                    continue

                seq = cells[0].strip()
                color_text = cells[1].strip()
                substrate = cells[2].strip().replace("<br>", "").replace("\n", "")
                prices = [c.strip() for c in cells[3:9]]  # 9mm, 18mm柜身, 25mm, 36mm, 门板18mm, 护墙18mm
                tech_note = cells[9].strip() if len(cells) > 9 else ""

                # Skip header-like rows
                if seq in ("", "序号") or "零售价" in seq:
                    continue

                # Inherit substrate from previous row if empty
                if not substrate and current_substrate:
                    substrate = current_substrate
                elif substrate:
                    current_substrate = substrate

                # Clean substrate
                substrate = substrate.replace(" ", "").replace("\n", "")
                if not substrate:
                    continue

                # Normalize substrate names
                substrate_norm = substrate
                if "实木颗粒板" in substrate and "负氧离子抗菌因子" in substrate:
                    substrate_norm = "ENF级实木颗粒板（负氧离子抗菌因子）"
                elif "欧松板" in substrate and "负氧离子抗菌因子" in substrate:
                    substrate_norm = "ENF级欧松板（负氧离子抗菌因子）"
                elif "欧松板" in substrate and "同步木纹" in substrate:
                    substrate_norm = "ENF级欧松板（同步木纹）"
                elif "欧松板" in substrate:
                    substrate_norm = "ENF级欧松板"
                elif "实木颗粒板" in substrate and "E0级" in substrate:
                    substrate_norm = "E0级实木颗粒板"
                elif "实木颗粒板" in substrate and "ENF级" in substrate:
                    substrate_norm = "ENF级实木颗粒板"
                elif "实木颗粒板" in substrate:
                    substrate_norm = "ENF级实木颗粒板"
                elif "颗粒板" in substrate and "E0级" in substrate:
                    substrate_norm = "E0级实木颗粒板"
                elif "颗粒板" in substrate and "ENF级" in substrate:
                    substrate_norm = "ENF级实木颗粒板"
                elif "颗粒板" in substrate:
                    substrate_norm = "ENF级实木颗粒板"
                elif "多层板" in substrate:
                    substrate_norm = "复合多层板"
                elif "匠芯实木板" in substrate:
                    substrate_norm = "匠芯实木板"
                elif "橡胶木板" in substrate:
                    substrate_norm = "橡胶木板"
                elif "点缀皮革" in substrate:
                    substrate_norm = "点缀皮革"

                # Parse color names (comma/顿号 separated)
                color_text = color_text.replace("<br>", "").replace("\n", "")
                color_names = re.split(r"[、,，]", color_text)
                color_names = [clean_color_name(c) for c in color_names if clean_color_name(c)]

                if not color_names:
                    continue

                # Inherit tech note if current row has none
                if tech_note:
                    current_tech_note = tech_note
                    min_area_rules = extract_min_charge_area(tech_note)
                    applicable_models = extract_applicable_models(tech_note)
                else:
                    tech_note = current_tech_note

                # Parse prices
                price_map = {
                    ("柜身", 9): prices[0] if len(prices) > 0 else "-",
                    ("柜身", 18): prices[1] if len(prices) > 1 else "-",
                    ("柜身", 25): prices[2] if len(prices) > 2 else "-",
                    ("柜身", 36): prices[3] if len(prices) > 3 else "-",
                    ("门板", 18): prices[4] if len(prices) > 4 else "-",
                    ("护墙", 18): prices[5] if len(prices) > 5 else "-",
                }

                for color_name in color_names:
                    for (comp_type, thickness), price_str in price_map.items():
                        if price_str in ("-", "", " "):
                            continue
                        try:
                            price = float(price_str)
                        except ValueError:
                            continue

                        # Determine min_charge_area for this component
                        min_area = min_area_rules.get(comp_type)

                        variant = PriceVariant(
                            product_id=product.id,
                            color_name=color_name,
                            substrate=substrate_norm,
                            thickness=thickness,
                            component_type=comp_type,
                            unit_price=price,
                            unit="元/㎡",
                            min_charge_area=min_area,
                            applicable_models=applicable_models if comp_type == "门板" else None,
                            remark=tech_note[:500] if tech_note else None,
                            is_standard=True,
                        )
                        all_variants.append(variant)

    print(f"Parsed {len(all_variants)} variants from {len(pages)} pages")

    # 4. Insert into DB (batch insert)
    if all_variants:
        db.bulk_save_objects(all_variants)
        db.commit()
        print(f"Inserted {len(all_variants)} price variants")

        # Summary
        from collections import Counter
        comp_counts = Counter(v.component_type for v in all_variants)
        thick_counts = Counter(v.thickness for v in all_variants)
        print("Component type distribution:", dict(comp_counts))
        print("Thickness distribution:", dict(thick_counts))
    else:
        print("No variants to insert!")

    db.close()


if __name__ == "__main__":
    import_wall_cabinet_prices()
