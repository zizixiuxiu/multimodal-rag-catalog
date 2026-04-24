"""
导入皮革门价格数据到 price_variants 表
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.product import PriceVariant, Product
from sqlalchemy import select

def main():
    db = SessionLocal()
    
    # 查找或创建皮革门产品
    stmt = select(Product).where(Product.name == "皮革门")
    product = db.execute(stmt).scalar_one_or_none()
    if not product:
        product = Product(
            family="皮革门",
            name="皮革门",
            model_no="DP",
            category="门板",
            description="皮革门板系列",
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        print(f"创建产品: 皮革门 (id={product.id})")
    else:
        print(f"使用已有产品: 皮革门 (id={product.id})")
    
    # 门型数据: (门型代号, 价格, 厚度, 颜色列表, 四边处理, 标配拉手, 技术说明)
    door_models = [
        ("DP01", 3504, 25, ["米白细纹", "爱马仕橙细纹"], "灰色金属包边", "LS-03灰色拉手", "基材：铝蜂窝板，价格不含拉手、门铰，皮革门厚25mm，需配加厚门门铰"),
        ("DP02", 3504, 25, ["米白细纹", "爱马仕橙细纹"], "古铜拉丝金属包边", "LS-03香槟金拉手", "基材：铝蜂窝板，价格不含拉手、门铰，皮革门厚25mm，需配加厚门门铰"),
        ("DP03", 3504, 25, ["米白平纹", "爱马仕橙平纹", "绅士灰粗纹"], "四边同色编织纹皮革车线", "LS-04灰色拉手", "基材：铝蜂窝板，价格不含拉手、门铰，皮革门厚25mm，需配加厚门门铰"),
    ]
    
    count = 0
    for model_no, price, thickness, colors, edge, handle, remark in door_models:
        for color in colors:
            variant = PriceVariant(
                product_id=product.id,
                color_name=color,
                substrate="铝蜂窝板",
                thickness=thickness,
                component_type="皮革门",
                unit_price=price,
                unit="元/㎡",
                spec={"door_type": "皮革门", "edge": edge, "handle": handle},
                is_standard=True,
                min_charge_area=0.5,
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
