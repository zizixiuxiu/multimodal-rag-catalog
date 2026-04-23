"""Product API — product catalog queries."""

from typing import Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.schemas import ProductListResponse, ProductOut
from app.core.database import get_db_context
from app.core.logging import get_logger
from app.models import Product

logger = get_logger(__name__)
router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=ProductListResponse)
async def list_products(
    family: Optional[str] = None,
    model_no: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
):
    """List products with optional filtering.

    Args:
        family: Filter by product family (e.g. "饰面门板")
        model_no: Filter by model number prefix
        skip: Pagination offset
        limit: Pagination size
    """
    with get_db_context() as db:
        stmt = select(Product).options(selectinload(Product.variants))

        if family:
            stmt = stmt.where(Product.family == family)
        if model_no:
            stmt = stmt.where(Product.model_no.ilike(f"%{model_no}%"))

        total = db.query(Product).count()
        if family:
            total = db.query(Product).filter(Product.family == family).count()
        elif model_no:
            total = db.query(Product).filter(Product.model_no.ilike(f"%{model_no}%")).count()

        items = db.execute(stmt.offset(skip).limit(limit)).scalars().all()

        return ProductListResponse(
            total=total,
            items=[ProductOut.model_validate(p) for p in items],
        )


@router.get("/{model_no}", response_model=ProductOut)
async def get_product(model_no: str):
    """Get a single product by model number."""
    with get_db_context() as db:
        product = db.execute(
            select(Product)
            .options(selectinload(Product.variants))
            .where(Product.model_no == model_no)
        ).scalar_one_or_none()

        if not product:
            raise HTTPException(status_code=404, detail=f"Product {model_no} not found")

        return ProductOut.model_validate(product)
