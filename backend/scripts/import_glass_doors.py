"""
导入铝框玻璃门价格数据到 price_variants 表
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.product import PriceVariant, Product
from sqlalchemy import select

def main():
    db = SessionLocal()
    
    # 查找或创建铝框玻璃门产品
    stmt = select(Product).where(Product.name == "铝框玻璃门")
    product = db.execute(stmt).scalar_one_or_none()
    if not product:
        product = Product(
            family="铝框玻璃门",
            name="铝框玻璃门",
            model_no="DL",
            category="门板",
            description="铝框玻璃门系列",
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        print(f"创建产品: 铝框玻璃门 (id={product.id})")
    else:
        print(f"使用已有产品: 铝框玻璃门 (id={product.id})")
    
    # 门型数据: (门型代号, 价格, 铝框厚度mm, 铝框颜色列表, 玻璃颜色列表, 技术说明)
    door_models = [
        ("DL01S", 855, 20, ["哑黑", "灰色", "古铜拉丝"], ["超白玻", "茶玻", "灰玻"], "窄边铝框玻璃门，铝框20厚，自带拉手，另配专用窄边铝框专用门铰"),
        ("DL02", 1860, 30, ["拉丝黑", "拉丝金"], ["超白玻", "茶玻", "灰玻"], "弧形铝框玻璃门，铝框30厚，自带拉手，另配专用天地横梁、天地门铰"),
        ("DL04", 1521, 30, ["拉丝黑", "拉丝灰"], ["灰玻"], "斜边铝框玻璃门，铝框30厚，另配专用LS-05嵌入式拉手，另配常用木门门铰"),
        ("DL05", 2550, 20, ["开士米银", "ins金", "极创灰", "黄铜金", "珠光黑"], ["超白玻", "茶玻"], "T型通顶拉手铝框玻璃门，铝框20厚"),
        ("DL06", 2880, 20, ["灰色", "古铜拉丝"], ["灰玻", "金茶", "超白玻", "银镜"], "A款免拉手铝框门，铝框20厚"),
        ("DL07", 2970, 20, ["紫罗兰", "中国红"], ["灰玻", "金茶", "超白玻", "银镜"], "B款免拉手铝框门，铝框20厚"),
    ]
    
    count = 0
    for model_no, price, thickness, frame_colors, glass_colors, remark in door_models:
        for frame_color in frame_colors:
            for glass_color in glass_colors:
                variant = PriceVariant(
                    product_id=product.id,
                    color_name=frame_color,  # 铝框颜色
                    substrate=glass_color,   # 玻璃颜色
                    thickness=thickness,
                    component_type="铝框玻璃门",
                    unit_price=price,
                    unit="元/㎡",
                    spec={"door_type": "铝框玻璃门", "frame_thickness_mm": thickness},
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
