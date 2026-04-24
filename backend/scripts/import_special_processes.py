"""
导入特殊工艺产品和木抽盒/木分线价格数据
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

    # ── 1. 特殊工艺产品 ──
    stmt = select(Product).where(Product.name == "特殊工艺产品")
    product = db.execute(stmt).scalar_one_or_none()
    if not product:
        product = Product(family="工艺产品", name="特殊工艺产品", model_no="GY-CP", category="工艺产品", description="特殊工艺定制产品")
        db.add(product); db.commit(); db.refresh(product)

    processes = [
        # 饰面格栅
        ("饰面格栅-35厚", "多层板", 2160, "元/平方", 35, "宽150-900、高200-2400、厚35。基材35厚多层为拆装；无多层的为颗粒板，为开槽组装工艺。"),
        ("饰面格栅-27厚", "颗粒板", 2700, "元/平方", 27, "宽150-900、高200-2400、厚27。开槽组装工艺。"),
        # 圆弧护墙
        ("圆弧护墙-饰面板", "颗粒板", 1710, "元/平方", 18, "不足0.5平方按0.5平方计价，大于0.5平方小于1平方按1平方计价。标准圆弧尺寸R150-350，最高2720。按弧见光面展开平方计价，价格已含内架。"),
        ("圆弧护墙-PET", "PET", 2250, "元/平方", 18, "不足0.5平方按0.5平方计价，大于0.5平方小于1平方按1平方计价。标准圆弧尺寸R150-350，最高2720。"),
        # 圆弧线条
        ("R-24单面圆弧", "饰面包覆", 75, "元/米", 24, "线条为包覆处理，只保证见光面不漏基材。弧形线条可能产生轻微色差。不足1米按1米计价。PET颜色另加15元/米。"),
        ("R-50单内面小圆弧", "饰面包覆", 105, "元/米", 50, "线条为包覆处理，只保证见光面不漏基材。弧形线条可能产生轻微色差。不足1米按1米计价。PET颜色另加15元/米。"),
        ("R-70单内面大圆弧", "饰面包覆", 135, "元/米", 70, "线条为包覆处理，只保证见光面不漏基材。弧形线条可能产生轻微色差。不足1米按1米计价。PET颜色另加15元/米。"),
        ("R-50单外面小圆弧", "饰面包覆", 105, "元/米", 50, "线条为包覆处理，只保证见光面不漏基材。弧形线条可能产生轻微色差。不足1米按1米计价。PET颜色另加15元/米。"),
        ("R-70单外面大圆弧", "饰面包覆", 135, "元/米", 70, "线条为包覆处理，只保证见光面不漏基材。弧形线条可能产生轻微色差。不足1米按1米计价。PET颜色另加15元/米。"),
        # 铝立板
        ("铝立板", "铝材", 960, "元/米", 9, "深310，厚9mm，不出孔。现场开孔。高度订制，最高3000mm。"),
        # ABA加厚板
        ("ABA加厚板", "不限", 1140, "元/平方", 36, "9+18+9成型加厚板。中间板前方标准内退10mm，其它三边不见光。基材不限。"),
        # 免漆45度斜拼柜
        ("免漆45度斜拼柜-组装工艺费", "不限", 210, "元/平方", 18, "不足0.5平方按0.5平方计价，大于0.5平方小于1平方按1平方计价。按正面投影平方另加组装工艺费。灯条安装费另计30元/条。正面斜边工艺费另计30元/米。"),
    ]
    for name, substrate, price, unit, thickness, remark in processes:
        db.add(PriceVariant(
            product_id=product.id, color_name="同门板色", substrate=substrate,
            thickness=thickness, component_type="特殊工艺产品",
            unit_price=price, unit=unit,
            spec={"process_name": name},
            is_standard=True, applicable_models=[name],
            remark=remark,
        )); count += 1
    print(f"特殊工艺产品: 导入完成")

    # ── 2. 木抽盒/木分线 ──
    stmt = select(Product).where(Product.name == "木抽盒及分线")
    product = db.execute(stmt).scalar_one_or_none()
    if not product:
        product = Product(family="配件", name="木抽盒及分线", model_no="CH-GZ", category="配件", description="木抽盒、格子架、裤架、拉板抽、木分线")
        db.add(product); db.commit(); db.refresh(product)

    accessories = [
        ("木抽盒", "E0级实木颗粒板", 210, "个", "标准高度H=80-240mm(10倍数)，深度按导轨工艺，宽度200-1000mm。不含滑轨和抽面。"),
        ("木抽盒", "ENF级实木颗粒板", 270, "个", "标准高度H=80-240mm(10倍数)，深度按导轨工艺，宽度200-1000mm。不含滑轨和抽面。"),
        ("木抽盒", "实木复合多层板/欧松板", 300, "个", "标准高度H=80-240mm(10倍数)，深度按导轨工艺，宽度200-1000mm。不含滑轨和抽面。"),
        ("格子架", "E0级实木颗粒板", 300, "个", "高度H=100mm(含抽面)，深度D=418/468mm，导轨400/450，宽度300-1000mm。不含滑轨，含抽面，只做侧装导轨。"),
        ("格子架", "ENF级实木颗粒板", 390, "个", "高度H=100mm(含抽面)，深度D=418/468mm，导轨400/450，宽度300-1000mm。不含滑轨，含抽面，只做侧装导轨。"),
        ("格子架", "实木复合多层板/欧松板", 435, "个", "高度H=100mm(含抽面)，深度D=418/468mm，导轨400/450，宽度300-1000mm。不含滑轨，含抽面，只做侧装导轨。"),
        ("裤架", "E0级实木颗粒板", 255, "个", "高度H=100mm(含抽面)，深度D=418/468mm，导轨400/450，宽度300-1000mm。中间圆管为铝合金管。不含滑轨，含抽面，只做侧装导轨。"),
        ("裤架", "ENF级实木颗粒板", 300, "个", "高度H=100mm(含抽面)，深度D=418/468mm，导轨400/450，宽度300-1000mm。中间圆管为铝合金管。不含滑轨，含抽面，只做侧装导轨。"),
        ("裤架", "实木复合多层板/欧松板", 375, "个", "高度H=100mm(含抽面)，深度D=418/468mm，导轨400/450，宽度300-1000mm。中间圆管为铝合金管。不含滑轨，含抽面，只做侧装导轨。"),
        ("拉板抽", "E0级实木颗粒板", 150, "个", "抽面高度H=60mm，深度D=400/450mm，导轨400/450，宽度300-1000mm。不含滑轨，含抽面，只做侧装导轨。"),
        ("拉板抽", "ENF级实木颗粒板", 195, "个", "抽面高度H=60mm，深度D=400/450mm，导轨400/450，宽度300-1000mm。不含滑轨，含抽面，只做侧装导轨。"),
        ("拉板抽", "实木复合多层板/欧松板", 225, "个", "抽面高度H=60mm，深度D=400/450mm，导轨400/450，宽度300-1000mm。不含滑轨，含抽面，只做侧装导轨。"),
        ("木分线-2420×24×5", "多层板", 60, "条", "发整条。正面同护墙颜色封边，背面多层板。"),
        ("木分线-2420×20×3", "多层板", 60, "条", "发整条。与圆弧线条配套应用。正面同护墙颜色封边，背面多层板。"),
    ]
    for name, substrate, price, unit, remark in accessories:
        db.add(PriceVariant(
            product_id=product.id, color_name="同门板色", substrate=substrate,
            thickness=18, component_type="木抽盒及分线",
            unit_price=price, unit=unit,
            spec={"accessory_name": name},
            is_standard=True, applicable_models=[name],
            remark=remark,
        )); count += 1
    print(f"木抽盒及分线: 导入完成")

    db.commit()
    print(f"总计导入: {count} 条价格记录")
    db.close()

if __name__ == "__main__":
    main()
