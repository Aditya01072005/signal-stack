import csv
import hashlib
import io
import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.company import Company
from app.models.document import Document
from app.models.signal import Signal
from app.schemas.document import DocumentIngestionResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/companies", tags=["Internal Documents"])

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_EXTRACTED_CHARACTERS = 1_000_000
ALLOWED_FILE_TYPES = {"pdf", "csv", "txt"}


def _extract_text(file_type: str, contents: bytes) -> str:
    if file_type == "pdf":
        if b"%PDF-" not in contents[:1024]:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="The uploaded file is not a valid PDF.",
            )
        try:
            reader = PdfReader(io.BytesIO(contents), strict=False)
            if reader.is_encrypted:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Encrypted PDFs are not supported.",
                )
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except (PdfReadError, ValueError, EOFError, OSError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="The PDF could not be parsed.",
            ) from exc
    else:
        try:
            text = contents.decode("utf-8-sig")
            if file_type == "csv":
                for _ in csv.reader(io.StringIO(text)):
                    pass
        except (UnicodeDecodeError, csv.Error) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"The {file_type.upper()} file must contain valid UTF-8 text.",
            ) from exc

    text = text.strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No extractable text was found in the document.",
        )
    if len(text) > MAX_EXTRACTED_CHARACTERS:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="The extracted document content exceeds the 1,000,000-character limit.",
        )
    return text


def _active_company(company_id: uuid.UUID, db: Session) -> Company:
    stmt = select(Company).where(
        Company.id == company_id,
        Company.is_deleted.is_(False),
    )
    company = db.execute(stmt).scalar_one_or_none()
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company '{company_id}' not found.",
        )
    return company


@router.post(
    "/{company_id}/documents",
    response_model=DocumentIngestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an internal company document",
)
async def upload_company_document(
    company_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> DocumentIngestionResponse:
    _active_company(company_id, db)

    filename = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not filename or len(filename) > 255:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A filename of at most 255 characters is required.",
        )
    file_type = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if file_type not in ALLOWED_FILE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF, CSV, and TXT documents are supported.",
        )

    contents = await file.read(MAX_DOCUMENT_BYTES + 1)
    if not contents:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The uploaded document is empty.",
        )
    if len(contents) > MAX_DOCUMENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="The document exceeds the 10 MB upload limit.",
        )

    extracted_text = _extract_text(file_type, contents)
    file_hash = hashlib.sha256(contents).hexdigest()
    normalized_hash = hashlib.sha256(
        " ".join(extracted_text.split()).casefold().encode("utf-8")
    ).hexdigest()
    duplicate_stmt = select(Document.id).where(
        Document.company_id == company_id,
        or_(
            Document.doc_metadata["sha256"].as_string() == file_hash,
            Document.doc_metadata["content_hash"].as_string() == normalized_hash,
        ),
    )
    if db.execute(duplicate_stmt).scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document has already been uploaded for this company.",
        )

    document_id = uuid.uuid4()
    signal_id = uuid.uuid4()
    document = Document(
        id=document_id,
        company_id=company_id,
        filename=filename,
        file_type=file_type,
        raw_text=extracted_text,
        doc_metadata={
            "sha256": file_hash,
            "content_hash": normalized_hash,
            "content_type": file.content_type,
        },
        processed=True,
    )
    signal = Signal(
        id=signal_id,
        company_id=company_id,
        source_id=None,
        title=f"Internal document: {filename}",
        content_snippet=extracted_text[:5000],
        source_url=f"internal-document://{document_id}",
        content_hash=hashlib.sha256(
            f"internal-document:{normalized_hash}".encode("utf-8")
        ).hexdigest(),
        is_verified=True,
        verbatim_quote=extracted_text[:500],
        opportunity_threat="neutral",
    )

    try:
        db.add(document)
        db.add(signal)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == "uq_company_signal_content_hash":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This document has already been uploaded for this company.",
            ) from exc
        logger.exception("Document ingestion violated a database constraint.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The document could not be saved.",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Document ingestion database operation failed.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The document could not be saved.",
        ) from exc

    return DocumentIngestionResponse(
        document_id=document_id,
        company_id=company_id,
        signal_id=signal_id,
        filename=filename,
        file_type=file_type,
        extracted_characters=len(extracted_text),
    )
