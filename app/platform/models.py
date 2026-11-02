import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.shared.database import Base

S = {"schema": "platform"}


def _now():
    return datetime.now(timezone.utc)


class AppUser(Base):
    __tablename__ = "app_user"
    __table_args__ = S
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)


class AuditEvent(Base):
    __tablename__ = "audit_event"
    __table_args__ = S
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    actor_type = Column(String, nullable=False)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("platform.app_user.id"))
    action = Column(String, nullable=False)
    object_type = Column(String, nullable=False)
    object_id = Column(UUID(as_uuid=True))
    before_state = Column(JSONB)
    after_state = Column(JSONB)
    correlation_id = Column(UUID(as_uuid=True), nullable=False)
    occurred_at = Column(DateTime(timezone=True), default=_now)


class Outbox(Base):
    __tablename__ = "outbox"
    __table_args__ = S
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(String, nullable=False)
    payload = Column(JSONB, nullable=False)
    correlation_id = Column(UUID(as_uuid=True), nullable=False)
    occurred_at = Column(DateTime(timezone=True), default=_now)
    delivered_at = Column(DateTime(timezone=True))
    attempts = Column(Integer, default=0, nullable=False)


class Approval(Base):
    __tablename__ = "approval"
    __table_args__ = S
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    object_type = Column(String, nullable=False)
    object_id = Column(UUID(as_uuid=True), nullable=False)
    control_point = Column(SmallInteger, nullable=False)
    maker_id = Column(UUID(as_uuid=True), ForeignKey("platform.app_user.id"), nullable=False)
    last_editor_id = Column(UUID(as_uuid=True), ForeignKey("platform.app_user.id"), nullable=False)
    checker_id = Column(UUID(as_uuid=True), ForeignKey("platform.app_user.id"), nullable=False)
    outcome = Column(String, nullable=False)
    reason = Column(String)
    object_state_snapshot = Column(JSONB, nullable=False)
    decided_at = Column(DateTime(timezone=True), default=_now)


class AiCallLog(Base):
    __tablename__ = "ai_call_log"
    __table_args__ = S
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_name = Column(String, nullable=False)
    template_version = Column(String, nullable=False)
    model_id = Column(String, nullable=False)
    prompt_rendered = Column(Text, nullable=False)
    raw_response = Column(Text)
    schema_valid = Column(Boolean, nullable=False)
    grounding_passed = Column(Boolean, nullable=False)
    confidence = Column(Numeric(3, 2))
    created_at = Column(DateTime(timezone=True), default=_now)


class Config(Base):
    __tablename__ = "config"
    __table_args__ = S
    key = Column(String, primary_key=True)
    value = Column(Numeric, nullable=False)
    default_value = Column(Numeric, nullable=False)
    min_value = Column(Numeric, nullable=False)
    max_value = Column(Numeric, nullable=False)
    description = Column(String, nullable=False)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("platform.app_user.id"))
    updated_at = Column(DateTime(timezone=True), default=_now)
