import uuid
from typing import Literal

from pydantic import BaseModel


class DocumentIngestionResponse(BaseModel):
    document_id: uuid.UUID
    company_id: uuid.UUID
    signal_id: uuid.UUID
    filename: str
    file_type: Literal["pdf", "csv", "txt"]
    extracted_characters: int
