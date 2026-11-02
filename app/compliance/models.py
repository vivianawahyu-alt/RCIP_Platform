import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.shared.database import Base

S = {"schema": "compliance"}
U = lambda: UUID(as_uuid=True)  # noqa: E731


def _now():
    return datetime.now(timezone.utc)


class OrganisationProfile(Base):
    __tablename__ = "organisation_profile"
    __table_args__ = S
    id = Column(U(), primary_key=True, default=uuid.uuid4)
    organisation_name = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    licenses = Column(JSONB, nullable=False, default=list)
    business_lines = Column(JSONB, nullable=False, default=list)
    version = Column(Integer, nullable=False, default=1)


class ApplicabilityDecision(Base):
    __tablename__ = "applicability_decision"
    __table_args__ = S
    id = Column(U(), primary_key=True, default=uuid.uuid4)
    target_version_id = Column(U(), ForeignKey("corpus.document_version.id", ondelete="RESTRICT"), nullable=False)
    profile_id = Column(U(), ForeignKey("compliance.organisation_profile.id", ondelete="RESTRICT"), nullable=False)
    decision_value = Column(String, nullable=False)
    reason_text = Column(String, nullable=False)
    relied_upon_attributes = Column(JSONB, nullable=False, default=dict)
    maker_id = Column(U(), ForeignKey("platform.app_user.id"), nullable=False)
    approver_id = Column(U(), ForeignKey("platform.app_user.id"))
    created_at = Column(DateTime(timezone=True), default=_now)
    state = Column(String, nullable=False, default="IN_ASSESSMENT")
    cited_provision_version_ids = Column(JSONB, nullable=False, default=list)
    scope_provision_version_ids = Column(JSONB, nullable=False, default=list)
    legal_question = Column(Text)
    legal_answer = Column(Text)
    legal_reviewer_id = Column(U(), ForeignKey("platform.app_user.id"))
    submitted_at = Column(DateTime(timezone=True))
    decided_at = Column(DateTime(timezone=True))
    return_reason = Column(Text)
    review_owner_id = Column(U(), ForeignKey("platform.app_user.id"))
    review_target_date = Column(Date)
    suggested_value = Column(String)
    superseded_by = Column(U(), ForeignKey("compliance.applicability_decision.id"))


class Obligation(Base):
    __tablename__ = "obligation"
    __table_args__ = S
    id = Column(U(), primary_key=True, default=uuid.uuid4)
    applicability_decision_id = Column(U(), ForeignKey("compliance.applicability_decision.id", ondelete="RESTRICT"), nullable=False)
    primary_citation_id = Column(U(), ForeignKey("corpus.provision_version.id", ondelete="RESTRICT"), nullable=False)
    original_text = Column(Text, nullable=False)
    plain_language_summary = Column(Text)
    required_actions = Column(JSONB, nullable=False, default=list)
    frequency = Column(String)
    deadline_expression = Column(String)
    required_evidence = Column(String)
    confidence = Column(Numeric(3, 2))
    derived_from_ai = Column(Boolean, nullable=False, default=True)
    owner_id = Column(U(), ForeignKey("platform.app_user.id"))
    validator_id = Column(U(), ForeignKey("platform.app_user.id"))
    approver_id = Column(U(), ForeignKey("platform.app_user.id"))
    state = Column(String, nullable=False, default="AI_DRAFT")
    created_at = Column(DateTime(timezone=True), default=_now)
    supporting_phrases = Column(JSONB, nullable=False, default=list)
    ai_call_id = Column(U(), ForeignKey("platform.ai_call_log.id"))
    model_id = Column(String)
    low_confidence = Column(Boolean, nullable=False, default=False)
    low_confidence_reviewed_by = Column(U(), ForeignKey("platform.app_user.id"))
    reopen_reason = Column(Text)


class Risk(Base):
    __tablename__ = "risk"
    __table_args__ = S
    id = Column(U(), primary_key=True, default=uuid.uuid4)
    obligation_id = Column(U(), ForeignKey("compliance.obligation.id", ondelete="RESTRICT"), nullable=False)
    title = Column(String, nullable=False)
    severity = Column(String, nullable=False, default="MEDIUM")


class Control(Base):
    __tablename__ = "control"
    __table_args__ = S
    id = Column(U(), primary_key=True, default=uuid.uuid4)
    risk_id = Column(U(), ForeignKey("compliance.risk.id", ondelete="RESTRICT"))
    title = Column(String, nullable=False)
    owner_id = Column(U(), ForeignKey("platform.app_user.id"))
    source_changed = Column(Boolean, nullable=False, default=False)


class ObligationControlMap(Base):
    __tablename__ = "obligation_control_map"
    __table_args__ = S
    obligation_id = Column(U(), ForeignKey("compliance.obligation.id", ondelete="RESTRICT"), primary_key=True)
    control_id = Column(U(), ForeignKey("compliance.control.id", ondelete="RESTRICT"), primary_key=True)


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = S
    id = Column(U(), primary_key=True, default=uuid.uuid4)
    control_id = Column(U(), ForeignKey("compliance.control.id", ondelete="RESTRICT"))
    remediation_action_id = Column(U(), ForeignKey("compliance.remediation_action.id", ondelete="RESTRICT"))
    filename = Column(String, nullable=False)
    object_key = Column(String, nullable=False)
    sha256 = Column(String(64), nullable=False)
    description = Column(String)
    size_bytes = Column(BigInteger)
    state = Column(String, nullable=False, default="SUBMITTED")
    uploaded_by = Column(U(), ForeignKey("platform.app_user.id"))
    uploaded_at = Column(DateTime(timezone=True), default=_now)
    reviewed_by = Column(U(), ForeignKey("platform.app_user.id"))
    reviewed_at = Column(DateTime(timezone=True))
    review_rationale = Column(String)


class Assessment(Base):
    __tablename__ = "assessment"
    __table_args__ = S
    id = Column(U(), primary_key=True, default=uuid.uuid4)
    control_id = Column(U(), ForeignKey("compliance.control.id", ondelete="RESTRICT"), nullable=False)
    result = Column(String, nullable=False)  # ringkasan = efektivitas operasional (kompatibel dgn versi lama)
    notes = Column(String)
    design_result = Column(String)
    operating_result = Column(String)
    design_rationale = Column(String)
    operating_rationale = Column(String)
    state = Column(String, nullable=False, default="CONCLUDED")
    assessed_by = Column(U(), ForeignKey("platform.app_user.id"))
    assessed_at = Column(DateTime(timezone=True), default=_now)
    submitted_by = Column(U(), ForeignKey("platform.app_user.id"))
    submitted_at = Column(DateTime(timezone=True))
    signed_off_by = Column(U(), ForeignKey("platform.app_user.id"))
    signed_off_at = Column(DateTime(timezone=True))
    return_reason = Column(String)


class Finding(Base):
    __tablename__ = "finding"
    __table_args__ = S
    id = Column(U(), primary_key=True, default=uuid.uuid4)
    obligation_id = Column(U(), ForeignKey("compliance.obligation.id", ondelete="RESTRICT"), nullable=False)
    kind = Column(String, nullable=False)
    title = Column(String)
    description = Column(String, nullable=False)
    severity = Column(String, nullable=False, default="MEDIUM")
    source_type = Column(String, nullable=False, default="MANUAL")
    control_id = Column(U(), ForeignKey("compliance.control.id", ondelete="RESTRICT"))
    assessment_id = Column(U(), ForeignKey("compliance.assessment.id", ondelete="RESTRICT"))
    owner_id = Column(U(), ForeignKey("platform.app_user.id"))
    raised_by = Column(U(), ForeignKey("platform.app_user.id"))
    target_closure_date = Column(Date)
    state = Column(String, nullable=False, default="OPEN")
    closure_submitted_by = Column(U(), ForeignKey("platform.app_user.id"))
    closure_submitted_at = Column(DateTime(timezone=True))
    closed_by = Column(U(), ForeignKey("platform.app_user.id"))
    closed_at = Column(DateTime(timezone=True))
    closure_rationale = Column(String)
    risk_acceptance_rationale = Column(String)
    risk_accepted_by = Column(U(), ForeignKey("platform.app_user.id"))
    risk_review_date = Column(Date)
    reopened_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class RemediationAction(Base):
    __tablename__ = "remediation_action"
    __table_args__ = S
    id = Column(U(), primary_key=True, default=uuid.uuid4)
    finding_id = Column(U(), ForeignKey("compliance.finding.id", ondelete="RESTRICT"), nullable=False)
    description = Column(String, nullable=False)
    expected_outcome = Column(String)
    due_date = Column(Date, nullable=False)
    original_due_date = Column(Date, nullable=False)
    extension_history = Column(JSONB, nullable=False, default=list)
    owner_id = Column(U(), ForeignKey("platform.app_user.id"))
    state = Column(String, nullable=False, default="OPEN")
    created_by = Column(U(), ForeignKey("platform.app_user.id"))
    created_at = Column(DateTime(timezone=True), default=_now)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    completion_note = Column(String)
    cancelled_reason = Column(String)


class ComplianceReport(Base):
    __tablename__ = "compliance_report"
    __table_args__ = S
    id = Column(U(), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    payload = Column(JSONB, nullable=False)
    state = Column(String, nullable=False, default="DRAFT")
    created_by = Column(U(), ForeignKey("platform.app_user.id"))
    created_at = Column(DateTime(timezone=True), default=_now)
    generated_by = Column(U(), ForeignKey("platform.app_user.id"))
    submitted_at = Column(DateTime(timezone=True))
    issued_by = Column(U(), ForeignKey("platform.app_user.id"))
    issued_at = Column(DateTime(timezone=True))
    return_reason = Column(String)
    withdrawn_reason = Column(String)
    withdrawn_at = Column(DateTime(timezone=True))
    superseded_by = Column(U(), ForeignKey("compliance.compliance_report.id"))
    disclaimer_version = Column(String)
