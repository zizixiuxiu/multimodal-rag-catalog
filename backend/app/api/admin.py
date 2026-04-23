"""Admin API — product and price variant management.

Provides full CRUD operations for maintaining the product catalog.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.schemas import (
    AdminActionResponse,
    PriceVariantOut,
    ProductCreate,
    ProductOut,
    ProductUpdate,
    VariantCreate,
    VariantUpdate,
)
from app.core.database import get_db_context
from app.core.logging import get_logger
from app.models import PriceVariant, Product

logger = get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


# ─────────────────────────────────────────────
# Products
# ─────────────────────────────────────────────

@router.get("/products", response_model=List[ProductOut])
async def list_all_products(
    family: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
):
    """List all products (admin view, higher limit)."""
    with get_db_context() as db:
        stmt = select(Product).options(selectinload(Product.variants))
        if family:
            stmt = stmt.where(Product.family == family)
        stmt = stmt.offset(skip).limit(limit)
        items = db.execute(stmt).scalars().all()
        return [ProductOut.model_validate(p) for p in items]


@router.post("/products", response_model=AdminActionResponse)
async def create_product(payload: ProductCreate):
    """Create a new product."""
    with get_db_context() as db:
        # Check duplicate model_no
        existing = db.execute(
            select(Product).where(Product.model_no == payload.model_no)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Product with model_no '{payload.model_no}' already exists",
            )

        product = Product(
            family=payload.family,
            model_no=payload.model_no,
            name=payload.name,
            description=payload.description,
            category=payload.category,
            image_urls=payload.image_urls or [],
            text_embedding=None,  # Admin can trigger embedding later if needed
        )
        db.add(product)
        db.commit()
        db.refresh(product)

        logger.info("Product created", model_no=product.model_no, id=product.id)
        return AdminActionResponse(
            success=True,
            message=f"Product '{product.model_no}' created",
            data={"id": product.id, "model_no": product.model_no},
        )


@router.get("/products/{model_no}", response_model=ProductOut)
async def get_product_detail(model_no: str):
    """Get product detail with all variants."""
    with get_db_context() as db:
        product = db.execute(
            select(Product)
            .options(selectinload(Product.variants))
            .where(Product.model_no == model_no)
        ).scalar_one_or_none()

        if not product:
            raise HTTPException(status_code=404, detail=f"Product {model_no} not found")

        return ProductOut.model_validate(product)


@router.put("/products/{model_no}", response_model=AdminActionResponse)
async def update_product(model_no: str, payload: ProductUpdate):
    """Update product info (does not touch variants)."""
    with get_db_context() as db:
        product = db.execute(
            select(Product).where(Product.model_no == model_no)
        ).scalar_one_or_none()

        if not product:
            raise HTTPException(status_code=404, detail=f"Product {model_no} not found")

        if payload.family is not None:
            product.family = payload.family
        if payload.name is not None:
            product.name = payload.name
        if payload.description is not None:
            product.description = payload.description
        if payload.category is not None:
            product.category = payload.category
        if payload.image_urls is not None:
            product.image_urls = payload.image_urls

        db.commit()
        db.refresh(product)

        logger.info("Product updated", model_no=product.model_no)
        return AdminActionResponse(
            success=True,
            message=f"Product '{model_no}' updated",
            data={"id": product.id, "model_no": product.model_no},
        )


@router.delete("/products/{model_no}", response_model=AdminActionResponse)
async def delete_product(model_no: str):
    """Delete a product and all its variants / images (cascade)."""
    with get_db_context() as db:
        product = db.execute(
            select(Product).where(Product.model_no == model_no)
        ).scalar_one_or_none()

        if not product:
            raise HTTPException(status_code=404, detail=f"Product {model_no} not found")

        db.delete(product)
        db.commit()

        logger.info("Product deleted", model_no=model_no)
        return AdminActionResponse(
            success=True,
            message=f"Product '{model_no}' and all variants deleted",
        )


# ─────────────────────────────────────────────
# Variants
# ─────────────────────────────────────────────

@router.get("/products/{model_no}/variants", response_model=List[PriceVariantOut])
async def list_product_variants(model_no: str):
    """List all price variants for a product."""
    with get_db_context() as db:
        product = db.execute(
            select(Product).where(Product.model_no == model_no)
        ).scalar_one_or_none()

        if not product:
            raise HTTPException(status_code=404, detail=f"Product {model_no} not found")

        variants = db.execute(
            select(PriceVariant).where(PriceVariant.product_id == product.id)
        ).scalars().all()

        return [PriceVariantOut.model_validate(v) for v in variants]


@router.post("/products/{model_no}/variants", response_model=AdminActionResponse)
async def create_variant(model_no: str, payload: VariantCreate):
    """Add a price variant to a product."""
    with get_db_context() as db:
        product = db.execute(
            select(Product).where(Product.model_no == model_no)
        ).scalar_one_or_none()

        if not product:
            raise HTTPException(status_code=404, detail=f"Product {model_no} not found")

        # Check duplicate (color, substrate, thickness)
        dup = db.execute(
            select(PriceVariant).where(
                PriceVariant.product_id == product.id,
                PriceVariant.color_name == payload.color_name,
                PriceVariant.substrate == payload.substrate,
                PriceVariant.thickness == payload.thickness,
            )
        ).scalar_one_or_none()

        if dup:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Variant already exists: {payload.color_name} / "
                    f"{payload.substrate} / {payload.thickness}mm"
                ),
            )

        variant = PriceVariant(
            product_id=product.id,
            color_name=payload.color_name,
            color_code=payload.color_code,
            substrate=payload.substrate,
            thickness=payload.thickness,
            unit_price=payload.unit_price,
            unit=payload.unit,
            spec=payload.spec or {},
            is_standard=payload.is_standard,
            remark=payload.remark,
        )
        db.add(variant)
        db.commit()
        db.refresh(variant)

        logger.info(
            "Variant created",
            model_no=model_no,
            color=payload.color_name,
            substrate=payload.substrate,
            thickness=payload.thickness,
        )
        return AdminActionResponse(
            success=True,
            message=f"Variant added to '{model_no}'",
            data={
                "variant_id": variant.id,
                "color_name": variant.color_name,
                "substrate": variant.substrate,
                "thickness": variant.thickness,
                "unit_price": float(variant.unit_price),
            },
        )


@router.put("/products/{model_no}/variants/{variant_id}", response_model=AdminActionResponse)
async def update_variant(
    model_no: str,
    variant_id: int,
    payload: VariantUpdate,
):
    """Update a price variant."""
    with get_db_context() as db:
        product = db.execute(
            select(Product).where(Product.model_no == model_no)
        ).scalar_one_or_none()

        if not product:
            raise HTTPException(status_code=404, detail=f"Product {model_no} not found")

        variant = db.execute(
            select(PriceVariant).where(
                PriceVariant.id == variant_id,
                PriceVariant.product_id == product.id,
            )
        ).scalar_one_or_none()

        if not variant:
            raise HTTPException(
                status_code=404,
                detail=f"Variant {variant_id} not found for product {model_no}",
            )

        # If changing key fields, check for duplicates
        new_color = payload.color_name if payload.color_name is not None else variant.color_name
        new_substrate = payload.substrate if payload.substrate is not None else variant.substrate
        new_thickness = payload.thickness if payload.thickness is not None else variant.thickness

        if (new_color, new_substrate, new_thickness) != (
            variant.color_name,
            variant.substrate,
            variant.thickness,
        ):
            dup = db.execute(
                select(PriceVariant).where(
                    PriceVariant.product_id == product.id,
                    PriceVariant.color_name == new_color,
                    PriceVariant.substrate == new_substrate,
                    PriceVariant.thickness == new_thickness,
                    PriceVariant.id != variant_id,
                )
            ).scalar_one_or_none()
            if dup:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Another variant already has: {new_color} / "
                        f"{new_substrate} / {new_thickness}mm"
                    ),
                )

        if payload.color_name is not None:
            variant.color_name = payload.color_name
        if payload.color_code is not None:
            variant.color_code = payload.color_code
        if payload.substrate is not None:
            variant.substrate = payload.substrate
        if payload.thickness is not None:
            variant.thickness = payload.thickness
        if payload.unit_price is not None:
            variant.unit_price = payload.unit_price
        if payload.unit is not None:
            variant.unit = payload.unit
        if payload.spec is not None:
            variant.spec = payload.spec
        if payload.is_standard is not None:
            variant.is_standard = payload.is_standard
        if payload.remark is not None:
            variant.remark = payload.remark

        db.commit()
        db.refresh(variant)

        logger.info("Variant updated", variant_id=variant_id, model_no=model_no)
        return AdminActionResponse(
            success=True,
            message=f"Variant {variant_id} updated",
            data={
                "variant_id": variant.id,
                "unit_price": float(variant.unit_price),
            },
        )


@router.delete("/products/{model_no}/variants/{variant_id}", response_model=AdminActionResponse)
async def delete_variant(model_no: str, variant_id: int):
    """Delete a price variant."""
    with get_db_context() as db:
        product = db.execute(
            select(Product).where(Product.model_no == model_no)
        ).scalar_one_or_none()

        if not product:
            raise HTTPException(status_code=404, detail=f"Product {model_no} not found")

        variant = db.execute(
            select(PriceVariant).where(
                PriceVariant.id == variant_id,
                PriceVariant.product_id == product.id,
            )
        ).scalar_one_or_none()

        if not variant:
            raise HTTPException(
                status_code=404,
                detail=f"Variant {variant_id} not found for product {model_no}",
            )

        db.delete(variant)
        db.commit()

        logger.info("Variant deleted", variant_id=variant_id, model_no=model_no)
        return AdminActionResponse(
            success=True,
            message=f"Variant {variant_id} deleted from '{model_no}'",
        )
