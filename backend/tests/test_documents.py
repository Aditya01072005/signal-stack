import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api.v1 import documents
from app.database import get_db
from app.main import app
from app.models.company import Company
from app.models.document import Document
from app.models.signal import Signal


def _company():
    company = MagicMock(spec=Company)
    company.id = uuid.uuid4()
    company.is_deleted = False
    return company


def _result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _upload(db, company_id, filename, content, content_type="text/plain"):
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            return client.post(
                f"/api/v1/companies/{company_id}/documents",
                files={"file": (filename, content, content_type)},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_text_upload_stores_content_and_exact_signal_evidence():
    company = _company()
    db = MagicMock()
    db.execute.side_effect = [_result(company), _result(None)]
    source_text = "Internal forecast: enrollment is expected to grow."

    response = _upload(
        db, company.id, "forecast.txt", source_text.encode(), "text/plain"
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["company_id"] == str(company.id)
    assert payload["filename"] == "forecast.txt"
    assert payload["file_type"] == "txt"
    assert payload["extracted_characters"] == len(source_text)

    document = next(
        call.args[0]
        for call in db.add.call_args_list
        if isinstance(call.args[0], Document)
    )
    signal = next(
        call.args[0]
        for call in db.add.call_args_list
        if isinstance(call.args[0], Signal)
    )
    assert document.company_id == company.id
    assert document.raw_text == source_text
    assert signal.company_id == company.id
    assert signal.source_url == f"internal-document://{payload['document_id']}"
    assert signal.verbatim_quote == source_text
    assert signal.verbatim_quote in signal.content_snippet
    assert db.commit.call_count == 1


def test_duplicate_document_for_same_company_is_rejected_without_writes():
    company = _company()
    existing_document = MagicMock(spec=Document)
    db = MagicMock()
    db.execute.side_effect = [_result(company), _result(existing_document)]

    response = _upload(db, company.id, "same.txt", b"stored content")

    assert response.status_code == 409
    assert "already been uploaded" in response.json()["detail"]
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_upload_requires_company_scoped_active_company():
    company_id = uuid.uuid4()
    db = MagicMock()
    db.execute.return_value = _result(None)

    response = _upload(db, company_id, "orphan.txt", b"private content")

    assert response.status_code == 404
    db.add.assert_not_called()


def test_upload_rejects_unsupported_and_oversized_files(monkeypatch):
    company = _company()

    unsupported_db = MagicMock()
    unsupported_db.execute.return_value = _result(company)
    response = _upload(unsupported_db, company.id, "notes.docx", b"text")
    assert response.status_code == 415
    unsupported_db.add.assert_not_called()

    monkeypatch.setattr(documents, "MAX_DOCUMENT_BYTES", 4)
    oversized_db = MagicMock()
    oversized_db.execute.return_value = _result(company)
    response = _upload(oversized_db, company.id, "notes.txt", b"12345")
    assert response.status_code == 413
    oversized_db.add.assert_not_called()


def test_pdf_and_csv_extractors_preserve_document_text():
    page = MagicMock()
    page.extract_text.return_value = "Extracted PDF evidence."
    reader = MagicMock()
    reader.pages = [page]
    reader.is_encrypted = False
    with patch.object(documents, "PdfReader", return_value=reader):
        assert documents._extract_text(
            "pdf", b"%PDF-1.7 sample"
        ) == "Extracted PDF evidence."

    csv_text = "metric,value\nrevenue,42"
    assert documents._extract_text("csv", csv_text.encode()) == csv_text
