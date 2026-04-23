"""Data import service — imports extracted products and text chunks into PostgreSQL.

Handles:
- Product deduplication by model_no
- Price variant deduplication by (color, substrate, thickness)
- Text embedding generation (BGE-M3)
- Image metadata tracking
- Batch import with transaction safety
"""

from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db_context
from app.core.logging import get_logger
from app.models import ImageVector, PriceVariant, Product, TextChunk
from app.processors.schemas import (
    ExtractedImage,
    ExtractedProduct,
    ExtractedTextBlock,
)
from app.services.models import embedding_service

logger = get_logger(__name__)


class DataImportService:
    """Service for importing extracted document data into the database."""

    def __init__(self) -> None:
        self._model_cache: Dict[str, int] = {}  # model_no -> product_id

    def import_products(
        self,
        products: List[ExtractedProduct],
        db: Optional[Session] = None,
    ) -> Dict[str, int]:
        """Import a list of extracted products into the database.

        Returns a mapping of model_no -> product_id for imported products.
        """
        should_close = db is None
        if db is None:
            context = get_db_context()
            db = context.__enter__()

        imported: Dict[str, int] = {}

        try:
            for prod in products:
                product_id = self._import_single_product(prod, db)
                if product_id:
                    imported[prod.model_no] = product_id

            db.commit()
            logger.info("Products imported", count=len(imported))

        except Exception as e:
            db.rollback()
            logger.error("Product import failed", error=str(e))
            raise
        finally:
            if should_close:
                context.__exit__(None, None, None)

        return imported

    def _import_single_product(
        self, prod: ExtractedProduct, db: Session
    ) -> Optional[int]:
        """Import a single product. Returns the product_id."""

        # Check cache first
        if prod.model_no in self._model_cache:
            product_id = self._model_cache[prod.model_no]
            logger.debug("Product cached", model_no=prod.model_no, id=product_id)
        else:
            # Check database
            existing = db.execute(
                select(Product).where(Product.model_no == prod.model_no)
            ).scalar_one_or_none()

            if existing:
                product_id = existing.id
                self._model_cache[prod.model_no] = product_id
                logger.debug("Product exists", model_no=prod.model_no, id=product_id)
            else:
                # Generate text embedding for product description
                text_for_embedding = f"{prod.model_no} {prod.model_name or ''} {prod.description or ''}"
                text_embedding = None
                try:
                    text_embedding = embedding_service.encode_single(text_for_embedding)
                except Exception as e:
                    logger.warning("Embedding failed for product", model_no=prod.model_no, error=str(e))

                # Create new product
                new_product = Product(
                    family=prod.product_family,
                    model_no=prod.model_no,
                    name=prod.model_name,
                    description=prod.description,
                    image_urls=[img.storage_url or f"file://{img.local_path}" for img in prod.images],
                    text_embedding=text_embedding,
                )
                db.add(new_product)
                db.flush()  # Get ID without committing
                product_id = new_product.id
                self._model_cache[prod.model_no] = product_id
                logger.info("Product created", model_no=prod.model_no, id=product_id)

        # Import price variants
        self._import_variants(product_id, prod.variants, db)

        # Import image vectors (metadata only, CLIP embedding deferred)
        self._import_image_vectors(product_id, prod.images, db)

        return product_id

    def _import_variants(
        self,
        product_id: int,
        variants: List,
        db: Session,
    ) -> None:
        """Import price variants for a product, avoiding duplicates."""
        if not variants:
            return

        # Fetch existing variants for this product
        existing = db.execute(
            select(PriceVariant).where(PriceVariant.product_id == product_id)
        ).scalars().all()

        existing_keys: Set[Tuple[str, str, int]] = {
            (v.color_name, v.substrate, v.thickness) for v in existing
        }

        added = 0
        for v in variants:
            key = (v.color_name, v.substrate, v.thickness)
            if key in existing_keys:
                continue

            new_variant = PriceVariant(
                product_id=product_id,
                color_name=v.color_name,
                color_code=v.color_code,
                substrate=v.substrate,
                thickness=v.thickness,
                unit_price=v.unit_price,
                unit=v.unit,
                spec=v.spec,
                is_standard=v.is_standard,
                remark=v.remark,
            )
            db.add(new_variant)
            existing_keys.add(key)
            added += 1

        if added:
            logger.debug("Variants added", product_id=product_id, count=added)

    def _import_image_vectors(
        self,
        product_id: int,
        images: List[ExtractedImage],
        db: Session,
    ) -> None:
        """Import image metadata. CLIP embedding is deferred to Module 4."""
        if not images:
            return

        for img in images:
            # Skip if already exists
            existing = db.execute(
                select(ImageVector).where(ImageVector.image_url == (img.storage_url or img.local_path))
            ).scalar_one_or_none()

            if existing:
                continue

            new_img = ImageVector(
                product_id=product_id,
                image_url=img.storage_url or f"file://{img.local_path}",
                image_type=img.image_type.value if img.image_type else None,
                clip_embedding=None,  # TODO: Generate CLIP embedding in Module 4
            )
            db.add(new_img)

    def import_text_chunks(
        self,
        chunks: List[ExtractedTextBlock],
        db: Optional[Session] = None,
    ) -> int:
        """Import text chunks with BGE-M3 embeddings.

        Returns the number of chunks imported.
        """
        should_close = db is None
        if db is None:
            context = get_db_context()
            db = context.__enter__()

        imported = 0

        try:
            # Batch process for efficiency
            texts = [c.text for c in chunks]
            embeddings = embedding_service.encode(texts)

            for chunk, embedding in zip(chunks, embeddings):
                new_chunk = TextChunk(
                    source_doc="extraction",
                    page_no=chunk.page_no,
                    chunk_type="process",  # Default, can be refined
                    content=chunk.text,
                    embedding=embedding,
                )
                db.add(new_chunk)
                imported += 1

            db.commit()
            logger.info("Text chunks imported", count=imported)

        except Exception as e:
            db.rollback()
            logger.error("Text chunk import failed", error=str(e))
            raise
        finally:
            if should_close:
                context.__exit__(None, None, None)

        return imported

    def import_from_extraction_result(
        self,
        products: List[ExtractedProduct],
        text_chunks: List[ExtractedTextBlock],
    ) -> Dict[str, int]:
        """Import both products and text chunks in a single transaction."""
        with get_db_context() as db:
            product_map = self.import_products(products, db=db)
            chunk_count = self.import_text_chunks(text_chunks, db=db)
            db.commit()

            return {
                "products_imported": len(product_map),
                "chunks_imported": chunk_count,
            }
