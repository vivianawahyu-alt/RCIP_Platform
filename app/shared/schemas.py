from datetime import datetime, timezone
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ResponseWrapper(BaseModel, Generic[T]):
    success: bool = True
    message: str = "OK"
    data: Optional[T] = None
    error_code: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CitationResolveRequest(BaseModel):
    provision_version_ids: List[str]


class DocumentDetailDTO(BaseModel):
    id: str
    canonical_number: str
    instrument_type: str
    issuer: str
    title_id: str
    status: str


class DocumentVersionDetailDTO(BaseModel):
    id: str
    version_number: int
    effective_date: str
    is_partial: bool
    state: str


class ResolvedCitationDTO(BaseModel):
    provision_version_id: str
    text: str
    number_label: str
    provision_type: str
    hierarchical_path: str
    document_version: DocumentVersionDetailDTO
    document: DocumentDetailDTO


class CitationResolveResponse(BaseModel):
    resolved: List[ResolvedCitationDTO]
    unresolved: List[str]
