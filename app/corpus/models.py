import uuid

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Computed, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID

from app.shared.database import Base

S = {"schema": "corpus"}


class RegulatorySource(Base):
    __tablename__ = "regulatory_source"
    __table_args__ = S
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, unique=True)
    category = Column(String, nullable=False)
    issuer_name = Column(String, nullable=False)
    base_url = Column(String, nullable=False)
    permitted_use_statement = Column(String)
    status = Column(String, nullable=False, default="DRAFT")


class Document(Base):
    __tablename__ = "document"
    __table_args__ = S
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("corpus.regulatory_source.id", ondelete="RESTRICT"), nullable=False)
    canonical_number = Column(String, unique=True, nullable=False)
    instrument_type = Column(String, nullable=False)
    issuer = Column(String, nullable=False)
    title_id = Column(String, nullable=False)
    status = Column(String, nullable=False, default="DRAFT")


class DocumentVersion(Base):
    __tablename__ = "document_version"
    __table_args__ = S
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("corpus.document.id", ondelete="RESTRICT"), nullable=False)
    version_number = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    origin_url = Column(String, nullable=False)
    canonical_text_ref = Column(String, nullable=False)
    effective_date = Column(Date, nullable=False)
    state = Column(String, nullable=False, default="PARSING")
    is_partial = Column(Boolean, nullable=False, default=False)


class Provision(Base):
    __tablename__ = "provision"
    __table_args__ = S
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("corpus.document.id", ondelete="RESTRICT"), nullable=False)
    provision_key = Column(String, nullable=False)
    provision_type = Column(String, nullable=False)
    number_label = Column(String, nullable=False)
    hierarchical_path = Column(String, nullable=False)


class ProvisionVersion(Base):
    __tablename__ = "provision_version"
    __table_args__ = S
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provision_id = Column(UUID(as_uuid=True), ForeignKey("corpus.provision.id", ondelete="RESTRICT"), nullable=False)
    document_version_id = Column(UUID(as_uuid=True), ForeignKey("corpus.document_version.id", ondelete="RESTRICT"), nullable=False)
    sequence = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    segmentation_confidence = Column(Numeric(3, 2), nullable=False, default=0.85)
    corrected_by_human = Column(Boolean, nullable=False, default=False)
    text_search = Column(TSVECTOR, Computed("to_tsvector('indonesian', text)", persisted=True))


class ChangeSet(Base):
    __tablename__ = "change_set"
    __table_args__ = S
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    base_version_id = Column(UUID(as_uuid=True), ForeignKey("corpus.document_version.id", ondelete="RESTRICT"), nullable=False)
    new_version_id = Column(UUID(as_uuid=True), ForeignKey("corpus.document_version.id", ondelete="RESTRICT"), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("platform.app_user.id"))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Change(Base):
    __tablename__ = "change"
    __table_args__ = S
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    change_set_id = Column(UUID(as_uuid=True), ForeignKey("corpus.change_set.id", ondelete="RESTRICT"), nullable=False)
    provision_id = Column(UUID(as_uuid=True), ForeignKey("corpus.provision.id", ondelete="RESTRICT"), nullable=False)
    base_pv_id = Column(UUID(as_uuid=True), ForeignKey("corpus.provision_version.id", ondelete="RESTRICT"))
    new_pv_id = Column(UUID(as_uuid=True), ForeignKey("corpus.provision_version.id", ondelete="RESTRICT"))
    change_type = Column(String, nullable=False)
    similarity = Column(Numeric(5, 4))
    is_material = Column(Boolean, nullable=False, default=False)
    diff_html = Column(Text)
    review_state = Column(String, nullable=False, default="DETECTED")
    semantic_type = Column(String)
    analyst_material = Column(Boolean)
    review_reason = Column(Text)
    legal_question = Column(Text)
    legal_answer = Column(Text)
    validated_by = Column(UUID(as_uuid=True), ForeignKey("platform.app_user.id"))
    validated_at = Column(DateTime(timezone=True))
    confirmed_by = Column(UUID(as_uuid=True), ForeignKey("platform.app_user.id"))
    confirmed_at = Column(DateTime(timezone=True))
    return_reason = Column(Text)
    impact = Column(JSONB, nullable=False, default=dict)


class Relationship(Base):
    __tablename__ = "relationship"
    __table_args__ = S
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_document_id = Column(UUID(as_uuid=True), ForeignKey("corpus.document.id", ondelete="RESTRICT"), nullable=False)
    target_document_id = Column(UUID(as_uuid=True), ForeignKey("corpus.document.id", ondelete="RESTRICT"), nullable=False)
    relation_type = Column(String, nullable=False)
    citing_provision_version_id = Column(UUID(as_uuid=True), ForeignKey("corpus.provision_version.id", ondelete="RESTRICT"))
    state = Column(String, nullable=False, default="PROPOSED")
    note = Column(Text)
    proposed_by = Column(UUID(as_uuid=True), ForeignKey("platform.app_user.id"))
    confirmed_by = Column(UUID(as_uuid=True), ForeignKey("platform.app_user.id"))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class TaxonomyLabel(Base):
    __tablename__ = "taxonomy_label"
    __table_args__ = S
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("corpus.document.id", ondelete="RESTRICT"), nullable=False)
    dimension = Column(String, nullable=False)
    value = Column(String, nullable=False)
    state = Column(String, nullable=False, default="SUGGESTED")
    source = Column(String, nullable=False, default="RULE")
    reason = Column(Text)
    decided_by = Column(UUID(as_uuid=True), ForeignKey("platform.app_user.id"))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
