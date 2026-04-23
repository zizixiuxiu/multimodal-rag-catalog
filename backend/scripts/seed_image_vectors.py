#!/usr/bin/env python3
"""Generate CLIP embeddings for all images in IMAGE_DIR and store in image_vectors."""

import os
import sys

sys.path.insert(0, "/Users/zizixiuixu/Code/kimi_code/multimodal-rag-catalog/backend")

from pathlib import Path

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import ImageVector
from app.services.clip_service import CLIPService


def seed():
    image_dir = Path(settings.IMAGE_DIR)
    if not image_dir.exists():
        print(f"Image directory not found: {image_dir}")
        return

    # Collect image files
    image_files = []
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        image_files.extend(image_dir.glob(ext))
        image_files.extend(image_dir.glob(ext.upper()))

    if not image_files:
        print(f"No images found in {image_dir}")
        return

    print(f"Found {len(image_files)} images")

    db = SessionLocal()
    try:
        # Clear existing image vectors
        db.query(ImageVector).delete()
        db.commit()
        print("Cleared existing image vectors")

        clip = CLIPService()

        batch_size = 8
        total = len(image_files)
        inserted = 0

        for i in range(0, total, batch_size):
            batch = image_files[i : i + batch_size]
            paths = [str(p) for p in batch]

            print(f"Processing batch {i//batch_size + 1}/{(total+batch_size-1)//batch_size} ({len(batch)} images)")

            try:
                embeddings = clip.encode_images(paths)
            except Exception as e:
                print(f"  Batch failed: {e}, skipping...")
                continue

            for j, path in enumerate(batch):
                # Infer image type from filename
                fname = path.name.lower()
                if "door" in fname or "style" in fname:
                    img_type = "door_style"
                elif "color" in fname or "chip" in fname:
                    img_type = "color_chip"
                elif "effect" in fname or "scene" in fname:
                    img_type = "effect"
                else:
                    img_type = "catalog"

                # Store relative path as URL
                rel_url = f"file://{path.resolve()}"

                iv = ImageVector(
                    product_id=None,  # No direct product mapping yet
                    image_url=rel_url,
                    image_type=img_type,
                    clip_embedding=embeddings[j].tolist(),
                )
                db.add(iv)
                inserted += 1

            db.commit()

        print(f"\n✅ Inserted {inserted}/{total} image vectors")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
