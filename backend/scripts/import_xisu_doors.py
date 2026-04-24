"""
导入吸塑柜门价格数据到 price_variants 表
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.product import PriceVariant, Product
from sqlalchemy import select

def main():
    db = SessionLocal()
    
    # 查找或创建吸塑柜门产品
    stmt = select(Product).where(Product.name == "吸塑柜门")
    product = db.execute(stmt).scalar_one_or_none()
    if not product:
        product = Product(
            family="吸塑门板",
            name="吸塑柜门",
            model_no="XS-M",
            category="门板",
            description="吸塑门板、包覆门板系列",
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        print(f"创建产品: 吸塑柜门 (id={product.id})")
    else:
        print(f"使用已有产品: 吸塑柜门 (id={product.id})")
    
    # 吸塑颜色列表
    colors = [
        "肤感橘", "绅士灰", "肤感白", "橡木灰", "肤感灰", "象牙黄",
        "玫瑰粉", "湖水蓝", "高光灰", "高光白", "赤金", "橘红格纹",
        "金丝樱桃", "黑檀木S"
    ]
    
    # 门型数据: (门型代号, 价格, 基材, 厚度, 最高高度mm, 备注)
    # 注意: PDF 中 MX-M00/M23/M24/M25/M26 有 2419以下和2420以上两个价格
    # 简化处理: 2419以下为基础价, 2420以上为超高加价
    door_models = [
        ("MX-M00", 525, "18mm中纤板", 18, 2720, "所有颜色可选"),
        ("MX-M23", 525, "18mm中纤板", 18, 2420, "正面嵌金色金属条,所有颜色可选"),
        ("MX-M24", 525, "18mm中纤板", 18, 2420, "所有颜色可选"),
        ("MX-M25", 525, "18mm中纤板", 18, 1200, "所有颜色可选"),
        ("MX-M26", 525, "18mm中纤板", 18, 2420, "所有颜色可选"),
        ("MX-M15", 810, "21mm中纤板", 21, 2420, "所有颜色可选"),
        ("MX-M16", 810, "21mm中纤板", 21, 2420, "所有颜色可选"),
        ("MX-M17", 810, "21mm中纤板", 21, 2420, "所有颜色可选"),
        ("MX-M04", 570, "18mm中纤板", 18, 2420, "所有颜色可选"),
        ("MX-M34", 810, "18mm中纤板", 18, 2420, "所有颜色可选"),
        ("MX-M21", 810, "18mm中纤板", 18, 1600, "门厚25mm,所有颜色可选"),
        ("MX-M22", 810, "18mm中纤板", 18, 1600, "所有颜色可选"),
        ("MX-M33", 810, "21mm中纤板", 21, 1600, "门厚25mm,所有颜色可选"),
        ("MX-M06", 570, "18mm中纤板", 18, 1600, "可选颜色:橡木灰/象牙黄/橘红格纹/金丝樱桃/黑檀木S"),
        ("MX-M07", 570, "18mm中纤板", 18, 1600, "所有颜色可选"),
        ("MX-M01", 570, "21mm中纤板", 21, 1600, "门厚25mm,所有颜色可选"),
        ("MX-M03", 570, "21mm中纤板", 21, 1600, "门厚25mm,所有颜色可选"),
        ("MX-M09", 810, "18mm中纤板", 18, 2100, "所有颜色可选"),
        ("MX-M31", 810, "18mm中纤板", 18, 2100, "所有颜色可选"),
        ("MX-M35", 960, "18mm中纤板", 18, 2100, "所有颜色可选"),
        ("MX-M18", 840, "18mm中纤板", 18, 2420, "所有颜色可选"),
        ("MX-M20", 810, "21mm中纤板", 21, 2420, "所有颜色可选"),
        ("MX-M19", 960, "21mm中纤板", 21, 2420, "所有颜色可选"),
        ("MX-M27", 1110, "21mm中纤板", 21, 2420, "正面嵌金色金属条,所有颜色可选"),
        ("MX-M28", 810, "21mm中纤板", 21, 2420, "所有颜色可选"),
        ("MX-M29", 1110, "21mm中纤板", 21, 2420, "正面嵌金色金属条,所有颜色可选"),
        ("MX-M30", 1170, "21mm中纤板", 21, 2420, "所有颜色可选"),
        ("波浪装饰板", 1035, "25mm中纤板", 25, 2420, "凸18宽×7mm高,标准间距22固定,适用于装饰背板,不可开连接孔"),
        ("吸塑格栅", 861, "18mm中纤板", 18, 2420, "所有颜色可选"),
    ]
    
    # 超高加价门型 (2419以下基础价, 2420以上加价)
    # PDF: MX-M00/M23/M24/M25/M26 2420以上 900元/㎡
    # 即加价: 900-525=375元/㎡
    ultra_high_models = {"MX-M00", "MX-M23", "MX-M24", "MX-M25", "MX-M26"}
    
    count = 0
    for model_no, price, substrate, thickness, max_height, remark in door_models:
        for color in colors:
            # MX-M06 部分颜色限制
            if model_no == "MX-M06":
                limited_colors = {"橡木灰", "象牙黄", "橘红格纹", "金丝樱桃", "黑檀木S"}
                if color not in limited_colors:
                    continue
            
            spec = {
                "max_height_mm": max_height,
                "door_type": "吸塑门板",
            }
            if model_no in ultra_high_models:
                spec["ultra_high_price"] = 900
                spec["ultra_high_threshold_mm"] = 2420
            
            variant = PriceVariant(
                product_id=product.id,
                color_name=color,
                substrate=substrate,
                thickness=thickness,
                component_type="吸塑柜门",
                unit_price=price,
                unit="元/㎡",
                spec=spec,
                is_standard=True,
                min_charge_area=0.3,
                applicable_models=[model_no],
                remark=remark,
            )
            db.add(variant)
            count += 1
    
    db.commit()
    print(f"导入完成: {count} 条价格记录")
    db.close()

if __name__ == "__main__":
    main()
