"""Import extraction result into PostgreSQL.

Usage:
    cd backend && python scripts/import_extraction.py ../data/extracted/extraction_result.json
    cd backend && python scripts/import_extraction.py --from-pdf /path/to/brochure.pdf
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import engine
from app.core.logging import configure_logging
from app.models.base import Base
from app.processors.pipeline import DocumentPipeline
from app.processors.schemas import ExtractedProduct, ExtractedTextBlock
from app.services.data_import import DataImportService


def load_from_json(json_path: str):
    """Load extraction result from a JSON file."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    products = [ExtractedProduct(**p) for p in data.get("products", [])]
    text_chunks = [ExtractedTextBlock(**t) for t in data.get("text_chunks", [])]
    return products, text_chunks


def run_from_pdf(pdf_path: str, use_vlm: bool = True):
    """Run full extraction pipeline and import."""
    pipeline = DocumentPipeline(use_vlm=use_vlm)
    result = pipeline.process(pdf_path)
    return result.products, result.text_chunks


def main():
    parser = argparse.ArgumentParser(description="Import extracted data into PostgreSQL")
    parser.add_argument("--from-json", help="Path to extraction_result.json")
    parser.add_argument("--from-pdf", help="Path to PDF file (runs full pipeline)")
    parser.add_argument("--no-vlm", action="store_true", help="Use rule-based VIE (faster, less accurate)")
    parser.add_argument("--create-tables", action="store_true", help="Create database tables if not exist")
    args = parser.parse_args()

    configure_logging("INFO")

    if args.create_tables:
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables created")

    if args.from_json:
        print(f"📄 Loading from {args.from_json}")
        products, text_chunks = load_from_json(args.from_json)
    elif args.from_pdf:
        print(f"📄 Processing PDF: {args.from_pdf}")
        products, text_chunks = run_from_pdf(args.from_pdf, use_vlm=not args.no_vlm)
    else:
        parser.print_help()
        return

    print(f"📝 Products to import: {len(products)}")
    print(f"📝 Text chunks to import: {len(text_chunks)}")

    service = DataImportService()
    stats = service.import_from_extraction_result(products, text_chunks)

    print(f"\n✅ Import complete!")
    print(f"   Products: {stats['products_imported']}")
    print(f"   Text chunks: {stats['chunks_imported']}")


if __name__ == "__main__":
    main()
