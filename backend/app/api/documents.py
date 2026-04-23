"""Document API — PDF upload and processing."""

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, HTTPException

from app.api.schemas import DocumentUploadResponse
from app.core.config import settings
from app.core.logging import get_logger
from app.processors.pipeline import DocumentPipeline
from app.services.data_import import DataImportService

logger = get_logger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """Upload a PDF brochure and extract structured data.

    Process:
    1. Save uploaded file
    2. Run document extraction pipeline
    3. Import extracted data into database
    """
    if not file.filename or not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    file_id = str(uuid.uuid4())
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / f"{file_id}_{file.filename}"

    try:
        # Save file
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        logger.info("PDF uploaded", filename=file.filename, path=str(file_path))

        # Run extraction pipeline (VLM-enabled for complex price tables)
        pipeline = DocumentPipeline(use_vlm=True)
        result = pipeline.process(str(file_path))

        # Import to database
        import_service = DataImportService()
        stats = import_service.import_from_extraction_result(
            result.products, result.text_chunks
        )

        return DocumentUploadResponse(
            message="Document processed successfully",
            file_id=file_id,
            pages=result.metadata["total_pages"],
            products_extracted=stats["products_imported"],
            text_chunks=stats["chunks_imported"],
        )

    except Exception as e:
        logger.error("Document upload failed", error=str(e), filename=file.filename)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

    finally:
        file.file.close()
