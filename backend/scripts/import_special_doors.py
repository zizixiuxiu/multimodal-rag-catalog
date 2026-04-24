"""
导入特殊门型价格数据：第二代铝木门、第二代铝框隐形门、饰面隐形门
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.product import PriceVariant, Product
from sqlalchemy import select

def main():
    db = SessionLocal()
    count = 0

    # ── 1. 第二代铝木门 ──
    stmt = select(Product).where(Product.name == "第二代铝木门")
    product = db.execute(stmt).scalar_one_or_none()
    if not product:
        product = Product(family="铝木门", name="第二代铝木门", model_no="RL", category="门板", description="第二代铝木门系列")
        db.add(product); db.commit(); db.refresh(product)
    # RL-2: 外平内开平面线条铝框门，加价3300
    # RL-3: 外平外开或内平内开窄边铝框门，加价2880
    for model_no, price, desc in [("RL-2", 3300, "外平内开平面线条铝框门，门扇厚53mm"), ("RL-3", 2880, "外平外开或内平内开窄边铝框门，门扇厚43mm")]:
        for color in ["蟹青色", "月影灰", "黑色"]:
            db.add(PriceVariant(
                product_id=product.id, color_name=color, substrate="铝框+复合实木芯材",
                thickness=53 if model_no=="RL-2" else 43, component_type="第二代铝木门",
                unit_price=price, unit="元/套",
                spec={"door_type": "第二代铝木门", "frame_color": "黑色", "addon_price": True},
                is_standard=True, applicable_models=[model_no],
                remark=f"{desc}。价格为基础价另+{price}元/套，包含普通款锁具、合页、门吸。标准门洞2200×900×300mm，超出45元/公分。",
            )); count += 1
    print(f"第二代铝木门: 导入完成")

    # ── 2. 第二代铝框隐形门 ──
    stmt = select(Product).where(Product.name == "第二代铝框隐形门")
    product = db.execute(stmt).scalar_one_or_none()
    if not product:
        product = Product(family="铝框隐形门", name="第二代铝框隐形门", model_no="RL-YX", category="门板", description="第二代铝框隐形门")
        db.add(product); db.commit(); db.refresh(product)
    for color in ["月影灰", "浅灰色", "黑色"]:
        db.add(PriceVariant(
            product_id=product.id, color_name=color, substrate="铝框+复合实木芯材",
            thickness=53, component_type="第二代铝框隐形门",
            unit_price=3300, unit="元/套",
            spec={"door_type": "第二代铝框隐形门", "frame_color": "黑色", "addon_price": True},
            is_standard=True, applicable_models=["RL-1"],
            remark="18叉隐形铝框门，门扇厚53mm。价格为基础价另+3300元/套，包含普通款锁具、合页、门吸。标准门洞2200×900×300mm，超出45元/公分。",
        )); count += 1
    print(f"第二代铝框隐形门: 导入完成")

    # ── 3. 饰面隐形门 ──
    stmt = select(Product).where(Product.name == "饰面隐形门")
    product = db.execute(stmt).scalar_one_or_none()
    if not product:
        product = Product(family="隐形门", name="饰面隐形门", model_no="YX-M", category="门板", description="木质隐形门，需与平板护墙配套")
        db.add(product); db.commit(); db.refresh(product)
    for substrate, price in [("颗粒板", 2940), ("多层板", 3240)]:
        db.add(PriceVariant(
            product_id=product.id, color_name="同护墙板色", substrate=substrate,
            thickness=18, component_type="饰面隐形门",
            unit_price=price, unit="元/樘",
            spec={"door_type": "饰面隐形门"},
            is_standard=True, applicable_models=["隐形门"],
            remark=f"木质隐形门，{substrate}表面。价格包含门扇、门套，不含门地吸/液压合页/门锁。只做内开门，墙体最小60厚。标准门洞2100×900×300mm，超出9元/公分。超高2000mm需加钢管360元/樘。",
        )); count += 1
    print(f"饰面隐形门: 导入完成")

    db.commit()
    print(f"总计导入: {count} 条价格记录")
    db.close()

if __name__ == "__main__":
    main()
