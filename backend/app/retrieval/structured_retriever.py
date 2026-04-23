"""Structured retriever — exact SQL queries for price and product data.

This is the PRIMARY retrieval path for price queries.
LLM must NEVER generate prices directly — always go through this layer.
"""

from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db_context
from app.core.logging import get_logger
from app.models import PriceVariant, Product
from app.retrieval.schemas import ParsedQuery, StructuredResult

logger = get_logger(__name__)


class StructuredRetriever:
    """Retrieve exact product data via structured SQL queries."""

    def search(self, parsed: ParsedQuery, db: Optional[Session] = None) -> List[StructuredResult]:
        """Execute structured search based on parsed query.

        For price queries, returns exact price variants.
        For list queries, returns matching products.
        """
        should_close = db is None
        if db is None:
            context = get_db_context()
            db = context.__enter__()

        try:
            conditions = parsed.sql_filters.get("conditions", {})
            results: List[StructuredResult] = []

            if parsed.intent.value == "query_price":
                results = self._query_price(conditions, db)
            elif parsed.intent.value == "list_products":
                results = self._list_products(conditions, db)
            elif parsed.intent.value == "compare":
                results = self._query_price(conditions, db)  # Same as price, returns multiple
            else:
                # For unknown intents, try a broad product search
                results = self._search_products(conditions, db)

            logger.info(
                "Structured search",
                intent=parsed.intent.value,
                conditions=conditions,
                results=len(results),
            )
            return results

        finally:
            if should_close:
                context.__exit__(None, None, None)

    def _query_price(self, conditions: dict, db: Session) -> List[StructuredResult]:
        """Query exact price variants with product info."""
        stmt = (
            select(Product, PriceVariant)
            .join(PriceVariant)
            .limit(20)
        )

        # Apply filters
        if "model_no" in conditions:
            stmt = stmt.where(Product.model_no == conditions["model_no"])
        if "color_name" in conditions:
            stmt = stmt.where(PriceVariant.color_name == conditions["color_name"])
        if "thickness" in conditions:
            stmt = stmt.where(PriceVariant.thickness == conditions["thickness"])
        if "substrate" in conditions:
            stmt = stmt.where(PriceVariant.substrate == conditions["substrate"])

        rows = db.execute(stmt).all()

        return [
            StructuredResult(
                product_id=row.Product.id,
                model_no=row.Product.model_no,
                model_name=row.Product.name,
                family=row.Product.family,
                color_name=row.PriceVariant.color_name,
                substrate=row.PriceVariant.substrate,
                thickness=row.PriceVariant.thickness,
                unit_price=row.PriceVariant.unit_price,
                unit=row.PriceVariant.unit,
                image_urls=row.Product.image_urls or [],
            )
            for row in rows
        ]

    def _list_products(self, conditions: dict, db: Session) -> List[StructuredResult]:
        """List products matching conditions (without requiring price variants)."""
        stmt = select(Product).limit(20)

        if "model_no" in conditions:
            stmt = stmt.where(Product.model_no == conditions["model_no"])
        if "family" in conditions:
            stmt = stmt.where(Product.family == conditions["family"])

        products = db.execute(stmt).scalars().all()

        results = []
        for p in products:
            # Get first variant as representative, or None
            variant = p.variants[0] if p.variants else None
            results.append(
                StructuredResult(
                    product_id=p.id,
                    model_no=p.model_no,
                    model_name=p.name,
                    family=p.family,
                    color_name=variant.color_name if variant else None,
                    substrate=variant.substrate if variant else None,
                    thickness=variant.thickness if variant else None,
                    unit_price=variant.unit_price if variant else None,
                    unit=variant.unit if variant else None,
                    image_urls=p.image_urls or [],
                )
            )
        return results

    def _search_products(self, conditions: dict, db: Session) -> List[StructuredResult]:
        """Broad product search for unknown intents."""
        return self._list_products(conditions, db)
