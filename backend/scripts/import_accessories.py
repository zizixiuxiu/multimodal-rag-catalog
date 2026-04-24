"""
导入套装门附件和异形件工艺费价格数据
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

    # ── 1. 套装门附件 ──
    stmt = select(Product).where(Product.name == "套装门附件")
    product = db.execute(stmt).scalar_one_or_none()
    if not product:
        product = Product(family="附件", name="套装门附件", model_no="FJ-TCM", category="附件", description="免漆套装门配套附件")
        db.add(product); db.commit(); db.refresh(product)

    accessories = [
        # (名称, 基材, 单价, 单位, 规格, 备注)
        ("哑口单包套", "复合", 108, "元/米", "高3000mm以内，深300mm以内，厚20mm", "深度超300mm时，每多增加10mm深度，加收零售价9元/公分。此价格不含有门套线。"),
        ("哑口单包套", "碳晶", 108, "元/米", "高3000mm以内，深300mm以内，厚20mm", "深度超300mm时，每多增加10mm深度，加收零售价9元/公分。此价格不含有门套线。"),
        ("哑口单包套", "多层", 123, "元/米", "高3000mm以内，深300mm以内，厚20mm", "深度超300mm时，每多增加10mm深度，加收零售价9元/公分。此价格不含有门套线。"),
        ("哑口双包套", "复合", 138, "元/米", "高3000mm以内，深300mm以内，厚20mm", "深度超300mm时，每多增加10mm深度，加收零售价9元/公分。此价格不含有门套线。"),
        ("哑口双包套", "碳晶", 138, "元/米", "高3000mm以内，深300mm以内，厚20mm", "深度超300mm时，每多增加10mm深度，加收零售价9元/公分。此价格不含有门套线。"),
        ("哑口双包套", "多层", 153, "元/米", "高3000mm以内，深300mm以内，厚20mm", "深度超300mm时，每多增加10mm深度，加收零售价9元/公分。此价格不含有门套线。"),
        ("门套线", "碳晶", 36, "元/米", "2400/2800×50/70，碳晶12厚", "多层15mm厚，碳晶12厚。"),
        ("门套线", "多层", 36, "元/米", "2400/2800×50/70，多层15厚", "多层15mm厚，碳晶12厚。"),
        ("踢脚线", "碳晶", 45, "元/米", "2400/2800×50/70，碳晶12厚", "多层15mm厚，碳晶12厚。"),
        ("踢脚线", "多层", 45, "元/米", "2400/2800×50/70，多层15厚", "多层15mm厚，碳晶12厚。"),
        ("门楣板", "通用", 420, "元/平方", "不足0.3平方照0.3平方计价", "平板所有颜色可选《免漆套装门颜色对照表》。"),
    ]
    for name, substrate, price, unit, spec, remark in accessories:
        db.add(PriceVariant(
            product_id=product.id, color_name="套装门同色", substrate=substrate,
            thickness=15 if substrate=="多层" else 12 if substrate=="碳晶" else 20,
            component_type="套装门附件",
            unit_price=price, unit=unit,
            spec={"accessory_name": name, "spec_range": spec},
            is_standard=True, applicable_models=[name],
            remark=remark,
        )); count += 1
    print(f"套装门附件: 导入完成")

    # ── 2. 异形件工艺费 ──
    stmt = select(Product).where(Product.name == "异形件工艺费")
    product = db.execute(stmt).scalar_one_or_none()
    if not product:
        product = Product(family="工艺费", name="异形件工艺费", model_no="GYF", category="工艺费", description="异形件特殊工艺费用")
        db.add(product); db.commit(); db.refresh(product)

    processes = [
        ("门铰开孔费A", 30, "元/扇", "门铰自备需工厂开孔时收此费用。"),
        ("门铰开孔费B", 60, "元/扇", "玻璃门，门铰自备需工厂开孔时收此费用。"),
        ("单扇小于0.2平方木架费", 30, "元/扇", "玻璃门及特定门型(MX-A02\\A10\\A04\\A05\\A15\\A16\\A18\\A19\\A20\\MX-M23\\M24\\M25\\M26\\M32)。"),
        ("单扇0.2-0.5平方木架费", 45, "元/扇", "玻璃门及特定门型。"),
        ("单扇大于0.5平方木架费", 69, "元/扇", "玻璃门及特定门型。"),
        ("灯槽开槽费", 60, "元/块", "自备灯时，开槽费另计。"),
        ("酒格工艺费", 135, "元/组", "只限于18mm厚双饰面板可做。"),
        ("圆角工艺费", 45, "元/个", "台面、侧板，圆弧层板等。"),
        ("切角工艺费", 45, "元/个", "切角柜每一个板件等。"),
        ("圆弧异形台面工艺费", 135, "元/件", "内圆弧L形台面。"),
        ("斜层板工艺费", 15, "元/件", "切斜板件等。"),
        ("圆弧板工艺费", 180, "元/件", "圆弧柜踢脚和圆弧柜顶线，标准尺寸R150.R200.R250。另加收木架费零售价90元/个。"),
        ("护墙海棠角工艺费", 30, "元/米", "按打斜尺寸计算。"),
        ("护墙阳角边工艺费", 60, "元/边", "内封边处理。"),
    ]
    for name, price, unit, remark in processes:
        db.add(PriceVariant(
            product_id=product.id, color_name="-", substrate="-",
            thickness=0, component_type="异形件工艺费",
            unit_price=price, unit=unit,
            spec={"process_name": name},
            is_standard=True, applicable_models=[name],
            remark=remark,
        )); count += 1
    print(f"异形件工艺费: 导入完成")

    db.commit()
    print(f"总计导入: {count} 条价格记录")
    db.close()

if __name__ == "__main__":
    main()
