"""
导入剩余未覆盖产品：PET门板、爱格板、EB板、22厚门板、吸塑配件、套装门五金
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

    # ── 1. PET门板 ──
    stmt = select(Product).where(Product.name == "PET门板")
    product = db.execute(stmt).scalar_one_or_none()
    if not product:
        product = Product(family="PET", name="PET门板", model_no="PET-M", category="门板", description="PET门板系列")
        db.add(product); db.commit(); db.refresh(product)
    
    pet_records = [
        # (颜色, 基材, 厚度, 价格, 适用门型, 备注)
        ("冰山白", "颗粒板", 18, 447, ["MX-A01","A02","A04","A07","A08","A09","A10","A17","A18","A19"], "肤感面，背面同色三胺饰面。可做干挂护墙，价格同门板。"),
        ("帷幔紫", "颗粒板", 18, 447, ["MX-A01","A02","A04","A07","A08","A09","A10","A17","A18","A19"], "肤感面，背面同色三胺饰面。可做干挂护墙，价格同门板。"),
        ("米杏灰", "欧松板", 18, 564, ["MX-A01","A02","A04","A07","A08","A09","A10","A17","A18","A19"], "双面肤感PET面。"),
        ("瓦石灰", "欧松板", 18, 564, ["MX-A01","A02","A04","A07","A08","A09","A10","A17","A18","A19"], "双面肤感PET面。"),
        ("燕羽灰", "欧松板", 18, 564, ["MX-A01","A02","A04","A07","A08","A09","A10","A17","A18","A19"], "双面肤感PET面。"),
        ("浅霞灰S", "欧松板", 18, 564, ["MX-A01","A02","A04","A07","A08","A09","A10","A17","A18","A19"], "双面肤感PET面。"),
        ("超哑暮云灰", "欧松板", 18, 564, ["MX-A01","A02","A04","A07","A08","A09","A10","A17","A18","A19"], "双面肤感PET面。"),
        ("阿克雷里灰", "欧松板", 18, 630, ["MX-A01","A02","A04","A07","A08","A09","A10","A17","A18","A19"], "双面亮光PET面。"),
        ("高光济州灰", "欧松板", 18, 630, ["MX-A01","A02","A04","A07","A08","A09","A10","A17","A18","A19"], "双面亮光PET面。"),
        ("雪峰白", "欧松板", 18, 630, ["MX-A01","A02","A04","A07","A08","A09","A10","A17","A18","A19"], "双面亮光PET面。"),
        ("宝马灰", "欧松板", 18, 630, ["MX-A01","A02","A04","A07","A08","A09","A10","A17","A18","A19"], "双面亮光PET面。"),
        ("幻彩米黄", "欧松板", 18, 594, ["MX-A01","A02","A04","A07","A08","A09","A10","A17","A18","A19"], "双面EB级漆感装饰膜。橱柜门板专用颜色。"),
        ("罗曼尼红", "欧松板", 18, 594, ["MX-A01","A02","A04","A07","A08","A09","A10","A17","A18","A19"], "双面EB级漆感装饰膜。橱柜门板专用颜色。"),
        ("香槟金拉丝", "欧松板", 18, 594, ["MX-A01","A02","A04","A07","A08","A09","A10","A17","A18","A19"], "双面PET拉丝膜。橱柜门板专用颜色。"),
        ("银河灰拉丝", "欧松板", 18, 594, ["MX-A01","A02","A04","A07","A08","A09","A10","A17","A18","A19"], "双面PET拉丝膜。橱柜门板专用颜色。"),
        ("钛银灰拉丝", "欧松板", 18, 594, ["MX-A01","A02","A04","A07","A08","A09","A10","A17","A18","A19"], "双面PET拉丝膜。橱柜门板专用颜色。"),
        # 22mm PET
        ("浅霞灰S", "欧松板", 22, 654, ["MX-A01","A07","A08","A09","A17"], "双面肤感PET面。"),
        ("燕羽灰", "欧松板", 22, 654, ["MX-A01","A07","A08","A09","A17"], "双面肤感PET面。"),
        ("瓦石灰", "欧松板", 22, 654, ["MX-A01","A07","A08","A09","A17"], "双面肤感PET面。"),
        ("宝马灰", "欧松板", 22, 720, ["MX-A01","A07","A08","A09","A17"], "双面亮光PET面。"),
    ]
    for color, substrate, thickness, price, models, remark in pet_records:
        db.add(PriceVariant(
            product_id=product.id, color_name=color, substrate=substrate,
            thickness=thickness, component_type="PET门板",
            unit_price=price, unit="元/平方",
            spec={"surface": "肤感PET" if "肤感" in remark else "亮光PET" if "亮光" in remark else "EB漆感" if "EB" in remark else "PET拉丝"},
            is_standard=True, applicable_models=models,
            remark=f"标准门宽300-550mm，高300-2720mm。宽350mm及以上、高1600mm及以上需加拉直器。价格不含拉直器和拉手。{remark}",
            min_charge_area=0.2,
        )); count += 1
    print(f"PET门板: {len(pet_records)}条导入完成")

    # ── 2. 爱格板 ──
    stmt = select(Product).where(Product.name == "爱格板")
    product = db.execute(stmt).scalar_one_or_none()
    if not product:
        product = Product(family="爱格", name="爱格板", model_no="EG-M", category="门板", description="爱格板门板/护墙")
        db.add(product); db.commit(); db.refresh(product)
    
    egger_records = [
        ("W980铂金白", "F★★★★级颗粒板", 660, ["MX-A01","A02","A04","A05","A07","A09","A10","A13"], "正面三胺饰面，背面同色带钢印三胺饰面。铂金白不可做A13门型。"),
        ("U702米兰灰绒", "F★★★★级颗粒板", 870, ["MX-A01","A02","A04","A05","A07","A09","A10","A13"], "正面三胺饰面，背面同色三胺饰面。"),
        ("H1379罗伦灰橡", "F★★★★级颗粒板", 1080, ["MX-A01","A02","A04","A05","A07","A09","A10","A13"], "正面三胺饰面，背面同色三胺饰面。"),
        ("H3158维察橡木", "F★★★★级颗粒板", 1080, ["MX-A01","A02","A04","A05","A07","A09","A10","A13"], "正面三胺饰面，背面同色三胺饰面。"),
        ("H1377托里灰橡", "F★★★★级颗粒板", 1080, ["MX-A01","A02","A04","A05","A07","A09","A10","A13"], "正面三胺饰面，背面同色三胺饰面。"),
        ("W1000典雅肤感白", "F★★★★级颗粒板", 1080, ["MX-A01","A02","A04","A05","A07","A09","A10","A13"], "正面三胺饰面，背面同色三胺饰面。"),
        ("H3342黑褐色橡木", "F★★★★级颗粒板", 1080, ["MX-A01","A02","A04","A05","A07","A09","A10","A13"], "正面三胺饰面，背面同色三胺饰面。"),
        ("H3190碳黑木纹", "F★★★★级颗粒板", 1080, ["MX-A01","A02","A04","A05","A07","A09","A10","A13"], "正面三胺饰面，背面同色三胺饰面。"),
    ]
    for color, substrate, price, models, remark in egger_records:
        db.add(PriceVariant(
            product_id=product.id, color_name=color, substrate=substrate,
            thickness=18, component_type="爱格板",
            unit_price=price, unit="元/平方",
            spec={"brand": "爱格", "grade": "F★★★★"},
            is_standard=True, applicable_models=models,
            remark=f"用于门板、护墙，同价。四边同色封边。宽350mm及以上、高1600mm及以上需加拉直器。{remark} 大板规格2800×2070×18。可做A13斜边拉手，另加30元/米。",
            min_charge_area=0.2,
        )); count += 1
    print(f"爱格板: {len(egger_records)}条导入完成")

    # ── 3. EB饰面 ──
    stmt = select(Product).where(Product.name == "EB板")
    product = db.execute(stmt).scalar_one_or_none()
    if not product:
        product = Product(family="EB", name="EB板", model_no="EB-M", category="门板", description="EB级漆感饰面板")
        db.add(product); db.commit(); db.refresh(product)
    
    eb_records = [
        ("斋浦尔红", "F★★★★LSB", 855, ["MX-A01","A02","A04","A07","A08","A09","A10","A17"], "背面同色三胺饰面，四边同色封边。"),
        ("湖水绿", "F★★★★LSB", 855, ["MX-A01","A02","A04","A07","A08","A09","A10","A17"], "背面同色三胺饰面，四边同色封边。"),
        ("伦敦灰", "F★★★★LSB", 855, ["MX-A01","A02","A04","A07","A08","A09","A10","A17"], "背面同色三胺饰面，四边同色封边。"),
        ("极光白", "F★★★★LSB", 855, ["MX-A01","A02","A04","A07","A08","A09","A10","A17"], "背面同色三胺饰面，四边同色封边。"),
        ("亚利桑那米", "F★★★★LSB", 855, ["MX-A01","A02","A04","A07","A08","A09","A10","A17"], "背面同色三胺饰面，四边同色封边。"),
        ("温太华卡其", "F★★★★LSB", 855, ["MX-A01","A02","A04","A07","A08","A09","A10","A17"], "背面同色三胺饰面，四边同色封边。"),
    ]
    for color, substrate, price, models, remark in eb_records:
        db.add(PriceVariant(
            product_id=product.id, color_name=color, substrate=substrate,
            thickness=18, component_type="EB板",
            unit_price=price, unit="元/平方",
            spec={"surface": "EB级漆感"},
            is_standard=True, applicable_models=models,
            remark=f"标准门宽300-550mm，高300-2720mm。可做干挂护墙，价格同门板。A06门型另加360元/平方(铝封边不带拉手，只可做1600mm高)；A06黑色铝封边带DS02-2拉手另加765元/平方。{remark}",
            min_charge_area=0.2,
        )); count += 1
    print(f"EB板: {len(eb_records)}条导入完成")

    # ── 4. 22厚柜门板 ──
    stmt = select(Product).where(Product.name == "22厚门板")
    product = db.execute(stmt).scalar_one_or_none()
    if not product:
        product = Product(family="22厚", name="22厚门板", model_no="22-M", category="门板", description="22厚柜门板")
        db.add(product); db.commit(); db.refresh(product)
    
    thick22_records = [
        ("淡雅杏黄", "F★★★★级颗粒板", 660, ["MX-A01","A13"], "正面同步木纹三胺饰面，背面同色三胺饰面。规格2745×1220×22。"),
        ("锯齿棕橡", "F★★★★级颗粒板", 660, ["MX-A01","A13"], "正面同步木纹三胺饰面，背面同色三胺饰面。规格2745×1220×22。"),
        ("马里兰棕", "F★★★★级颗粒板", 660, ["MX-A01","A13"], "正面同步木纹三胺饰面，背面同色三胺饰面。规格2745×1220×22。"),
        ("萨马拉白", "F★★★★级颗粒板", 660, ["MX-A01","A13"], "正面同步木纹三胺饰面，背面同色三胺饰面。规格2745×1220×22。"),
        ("拉普兰香榆", "F★★★★级颗粒板", 660, ["MX-A01","A13"], "正面同步木纹三胺饰面，背面同色三胺饰面。规格2745×1220×22。"),
    ]
    for color, substrate, price, models, remark in thick22_records:
        db.add(PriceVariant(
            product_id=product.id, color_name=color, substrate=substrate,
            thickness=22, component_type="22厚门板",
            unit_price=price, unit="元/平方",
            spec={"thickness_type": "22厚"},
            is_standard=True, applicable_models=models,
            remark=f"门厚22mm，四边同色封边。400宽以内及2400高以下可不用加拉直器。A13斜边拉手另加30元/米。{remark}",
            min_charge_area=0.2,
        )); count += 1
    print(f"22厚门板: {len(thick22_records)}条导入完成")

    # ── 5. 吸塑配件 ──
    stmt = select(Product).where(Product.name == "吸塑配件")
    product = db.execute(stmt).scalar_one_or_none()
    if not product:
        product = Product(family="吸塑配件", name="吸塑配件", model_no="XS-FJ", category="配件", description="吸塑柜门配套配件")
        db.add(product); db.commit(); db.refresh(product)
    
    xs_accessories = [
        ("罗马柱面板", "中纤板", 150, "元/米", 18, "宽60mm"),
        ("脚线-LM-M01-60", "中纤板", 150, "元/米", 18, "高80mm厚18mm"),
        ("脚线-LM-M09-60", "中纤板", 150, "元/米", 18, "高80mm厚12mm"),
        ("脚线-LM-M11-60", "中纤板", 150, "元/米", 18, "高80mm厚35mm"),
        ("脚线-LM-M02-60", "中纤板", 150, "元/米", 18, "高80mm外飘62mm"),
        ("脚线-LM-M03-60", "中纤板", 150, "元/米", 18, "高80mm外飘32mm"),
        ("脚线-LM-M05-60", "中纤板", 150, "元/米", 18, "高80mm外飘43mm"),
        ("顶线-JX-M01", "中纤板", 90, "元/米", 18, "高80mm"),
        ("顶线-JX-M02", "中纤板", 90, "元/米", 18, "高80mm"),
        ("顶线-JX-M04", "中纤板", 90, "元/米", 18, "高80mm"),
        ("灯线-DX-M01", "中纤板", 126, "元/米", 18, "高75mm外飘32mm"),
        ("灯线-DX-M03", "中纤板", 126, "元/米", 18, "高84mm外飘43mm"),
        ("灯线-DX-M011", "中纤板", 126, "元/米", 18, "高84mm"),
        ("21厚单面平板吸塑", "中纤板", 615, "元/平方", 21, "见光板、封板"),
        ("18厚单面平板吸塑", "中纤板", 525, "元/平方", 18, "见光板、封板、护墙板"),
        ("18厚双面平板吸塑", "中纤板", 1575, "元/平方", 18, "双面吸塑"),
        ("18厚台面", "中纤板", 480, "元/平方", 18, "台面"),
        ("25厚台面", "中纤板", 780, "元/平方", 25, "台面"),
        ("楣板-LX-M01", "中纤板", 249, "元/米", 18, "宽354-2400"),
        ("楣板-LX-M02", "中纤板", 249, "元/米", 18, "宽354-2400"),
        ("楣板-LX-M03", "中纤板", 249, "元/米", 18, "宽354-2400"),
        ("楣板-LX-M04", "中纤板", 249, "元/米", 18, "宽354-2400"),
        ("半月酒格-同向", "中纤板", 369, "元/米", 18, "18mm厚板，单面吸塑"),
        ("半月酒格-交错", "中纤板", 369, "元/米", 18, "18mm厚板，单面吸塑"),
        ("装饰框", "中纤板", 480, "元/平方", 18, "18mm厚板，单面吸塑"),
    ]
    for name, substrate, price, unit, thickness, remark in xs_accessories:
        db.add(PriceVariant(
            product_id=product.id, color_name="同吸塑门色", substrate=substrate,
            thickness=thickness, component_type="吸塑配件",
            unit_price=price, unit=unit,
            spec={"accessory_name": name},
            is_standard=True, applicable_models=[name],
            remark=remark,
        )); count += 1
    print(f"吸塑配件: {len(xs_accessories)}条导入完成")

    # ── 6. 套装门五金 ──
    stmt = select(Product).where(Product.name == "套装门五金")
    product = db.execute(stmt).scalar_one_or_none()
    if not product:
        product = Product(family="五金", name="套装门五金", model_no="WJ-TCM", category="五金", description="套装门及隐形门五金配件")
        db.add(product); db.commit(); db.refresh(product)
    
    hardware = [
        ("SJ001", "意式把手嵌板锁", "黑色", 384, "套", "套装门锁具"),
        ("AYZ-868", "套装门锁具", "灰色/哑黑", 450, "套", "套装门锁具"),
        ("101", "套装门锁具", "哑黑", 384, "套", "套装门锁具"),
        ("102", "套装门锁具", "哑黑", 384, "套", "套装门锁具"),
        ("CQ-GH-02", "套装门锁具", "哑黑", 225, "套", "套装门锁具"),
        ("CQ-GH-02B", "套装门锁具", "枪灰", 225, "套", "套装门锁具"),
        ("CQ-GH-03", "套装门锁具", "枪灰", 225, "套", "套装门锁具"),
        ("CQ-GH-03B", "套装门锁具", "哑黑", 225, "套", "套装门锁具"),
        ("CQ-GH-04", "套装门锁具", "枪灰", 225, "套", "套装门锁具"),
        ("CQ-GH-04B", "套装门锁具", "哑黑", 225, "套", "套装门锁具"),
        ("CQ-GH-05", "套装门锁具", "黄古铜", 234, "套", "套装门锁具"),
        ("CQ-GH-07", "套装门锁具", "枪灰/胡桃木", 267, "套", "套装门锁具"),
        ("CQ-GH-10", "套装门锁具", "象牙白", 210, "套", "套装门锁具"),
        ("ST03", "套装门锁具", "黑色", 384, "套", "套装门锁具"),
        ("ST03", "套装门锁具", "灰色", 384, "套", "套装门锁具"),
        ("ST05", "套装门锁具", "黑色", 384, "套", "套装门锁具"),
        ("ST05", "套装门锁具", "灰色", 384, "套", "套装门锁具"),
        ("TL008", "套装门锁具", "黑色", 384, "套", "套装门锁具"),
        ("MZF7203A-V27", "套装门锁具", "黑色", 504, "套", "套装门锁具"),
        ("MZF7203A-V27", "套装门锁具", "灰色", 504, "套", "套装门锁具"),
        ("MZF7203A-V73", "套装门锁具", "古铜色", 504, "套", "套装门锁具"),
        ("MZF7203A-354", "套装门锁具", "灰色", 504, "套", "套装门锁具"),
        ("MZF7203A-275", "套装门锁具", "灰色", 504, "套", "套装门锁具"),
        ("MZF7209A-351", "套装门锁具", "古铜色", 504, "套", "套装门锁具"),
        ("K-02", "生态门锁", "黑色", 504, "套", "生态门锁"),
        ("K-02", "生态门锁", "灰色", 504, "套", "生态门锁"),
        ("MZF7205-22", "套装门锁具", "灰+棕皮", 594, "套", "套装门锁具"),
        ("8809TS-A", "套装门指纹密码锁", "银色", 1740, "套", "指纹密码锁"),
        ("8809TS-B", "套装门指纹密码锁", "银色", 1740, "套", "指纹密码锁"),
        # 合页
        ("433-A", "套装门子母合页", "黄古铜", 45, "个", "子母合页"),
        ("433-B", "套装门子母合页", "白色", 45, "个", "子母合页"),
        ("433-C", "套装门子母合页", "黑色", 45, "个", "子母合页"),
        ("433-D", "套装门子母合页", "银色", 45, "个", "子母合页"),
        ("STZ-01", "三维十字隐形合叶", "黑色", 360, "个", "三维十字隐形合叶"),
        ("HY28", "免开孔合页", "黑色", 360, "个", "免开孔合页，隐藏式三维可调套板"),
        # 门吸/地吸/液压合页
        ("365A-A", "套装门门吸", "黄古铜", 30, "个", "门吸"),
        ("365A-B", "套装门门吸", "白色", 30, "个", "门吸"),
        ("365A-C", "套装门门吸", "黑色", 30, "个", "门吸"),
        ("365A-D", "套装门门吸", "银色", 30, "个", "门吸"),
        ("SYM-01", "多功能液压合页", "黑色", 360, "套", "多功能液压合页，不分左右，80KG以内配3个"),
        ("SYM-02", "内开门锁", "黑色", 165, "套", "内开门锁"),
        ("SYM-03", "门地吸", "黑色", 60, "套", "门地吸"),
    ]
    for model, name, color, price, unit, remark in hardware:
        db.add(PriceVariant(
            product_id=product.id, color_name=color, substrate="金属",
            thickness=0, component_type="套装门五金",
            unit_price=price, unit=unit,
            spec={"hardware_name": name, "model": model},
            is_standard=True, applicable_models=[model],
            remark=remark,
        )); count += 1
    print(f"套装门五金: {len(hardware)}条导入完成")

    db.commit()
    print(f"\n总计导入: {count} 条价格记录")
    db.close()

if __name__ == "__main__":
    main()
