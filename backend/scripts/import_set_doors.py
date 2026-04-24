"""
导入免漆套装门价格数据到 price_variants 表（简化版）
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.product import PriceVariant, Product
from sqlalchemy import select

def main():
    db = SessionLocal()
    
    # 查找或创建免漆套装门产品
    stmt = select(Product).where(Product.name == "免漆套装门")
    product = db.execute(stmt).scalar_one_or_none()
    if not product:
        product = Product(
            family="免漆套装门",
            name="免漆套装门",
            model_no="GE",
            category="门板",
            description="免漆平板套装门、拼装成型套装门",
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        print(f"创建产品: 免漆套装门 (id={product.id})")
    else:
        print(f"使用已有产品: 免漆套装门 (id={product.id})")
    
    # 颜色
    colors = [
        "月光白", "冰山白", "浅灰色", "帷幔紫", "奶咖色", "浅霞灰S",
        "胡椒灰", "米杏灰", "铅灰色", "燕羽灰", "济州灰", "瓦石灰",
        "高光济州灰", "雪山白", "科技木3号", "科技木1号", "直纹灰",
        "铁刀木2号", "科技木2号", "蟹青色",
    ]
    
    # 门型数据: (门型代号, 价格, 类型说明)
    door_models = [
        # 免漆平板套装门
        ("GE-0004", 1285, "平板无造型"),
        ("GE-1003", 1465, "平板拉黑色水线"),
        ("GE-1005", 1465, "平板拉黑色水线"),
        ("GE-1007", 1465, "平板拉黑色水线"),
        ("GE-1008", 1465, "平板拉黑色水线"),
        ("GE-1012", 1465, "平板拉黑色水线"),
        ("GE-1014", 1465, "平板拉黑色水线"),
        ("MW-06", 1465, "平板嵌T型黑色金属条"),
        ("MW-02", 1465, "平板嵌T型黑色金属条"),
        ("MW-03", 1675, "平板嵌T型黑色金属条"),
        ("MW-04", 1705, "平板拉水线+嵌花"),
        ("GE-4010", 1615, "平板拉水线+嵌花"),
        ("GE-4011", 1615, "平板拉水线+嵌花"),
        ("GE-4021", 1615, "平板拉水线+嵌花"),
        ("GE-4022", 1615, "平板拉水线+嵌花"),
        ("GE-5007", 1615, "平板拉水线+嵌花"),
        ("GE-4071", 1614, "黑色水线+嵌花"),
        ("GE-4072", 1614, "黑色水线+嵌花"),
        ("GE-4073", 1614, "黑色水线+嵌花"),
        ("GE-4074", 1614, "黑色水线+嵌花"),
        ("GE-4075", 1614, "黑色水线+嵌花"),
        ("GE-4076", 1704, "黑色水线+嵌花"),
        ("GE-4077", 1614, "黑色水线+嵌花"),
        ("GE-4078", 1614, "黑色水线+嵌花"),
        ("GE-4079", 1614, "黑色水线+嵌花"),
        ("GE-4080", 1614, "黑色水线+嵌花"),
        ("GE-4081", 1764, "黑色水线+嵌装饰条"),
        ("GE-4082", 1614, "黑色水线+嵌花"),
        ("GE-4083", 1764, "金色水线+嵌装饰条"),
        ("GE-4084", 1764, "嵌装饰条"),
        ("GE-4085", 1764, "嵌装饰条"),
        ("PET-35", 1465, "平板门无造型"),
        ("PET-41", 1705, "镶嵌金属条"),
        ("PET-43", 1795, "镶嵌金属条"),
        ("PET-20", 1555, "平板门拉水线+镶嵌金属条"),
        ("PET-21", 1555, "平板门拉水线+镶嵌金属条"),
        ("PET-22", 1555, "平板门拉水线+镶嵌金属条"),
        ("PET-23", 1555, "平板门拉水线+镶嵌金属条"),
        ("PET-24", 1555, "平板门拉水线+镶嵌金属条"),
        ("PET-25", 1555, "平板拉黑色水线"),
        ("PET-26", 1555, "平板拉黑色水线"),
        ("PET-27", 1555, "平板拉黑色水线"),
        ("PET-28", 1555, "平板拉黑色水线"),
        ("PET-29", 1555, "平板拉黑色水线"),
        ("PET-30", 1555, "平板拉黑色水线"),
        ("PET-31", 1555, "平板拉黑色水线"),
        ("PET-32", 1555, "平板拉黑色水线"),
        ("PET-33", 1555, "平板拉黑色水线"),
        ("PET-34", 1555, "平板拉黑色水线"),
        ("PET-36", 1555, "平板拉黑色水线"),
        ("PET-39", 1555, "平板拉黑色水线"),
        ("PET-40", 1555, "平板拉黑色水线"),
        ("PET-42", 1555, "平板拉黑色水线"),
        # 免漆拼装/成型套装门
        ("GE-5003", 2220, "拼装成型门、平板拉黑色水线"),
        ("GE-5011", 2070, "拼装成型门、平板拉黑色水线"),
        ("MW-07", 2070, "拼装成型门、平板拉黑色水线"),
        ("MW-05", 2070, "拼装成型门、平板拉黑色水线"),
        ("GE-5001", 2070, "拼装成型门、平板拉黑色水线"),
    ]
    
    count = 0
    for model_no, price, remark in door_models:
        for color in colors:
            variant = PriceVariant(
                product_id=product.id,
                color_name=color,
                substrate="复合实木芯材",
                thickness=45,
                component_type="免漆套装门",
                unit_price=price,
                unit="元/樘",
                spec={"door_type": "免漆套装门", "surface": "绿晶板/复合板"},
                is_standard=True,
                min_charge_area=None,
                applicable_models=[model_no],
                remark=f"{remark}。一樘门包含：门扇、门套板、门套线，不含五金。标准门洞高2100×宽900×厚300mm",
            )
            db.add(variant)
            count += 1
    
    db.commit()
    print(f"导入完成: {count} 条价格记录")
    db.close()

if __name__ == "__main__":
    main()
