from typing import Any, Optional

from sqlalchemy.orm import Session

from app.platform.models import Approval, AuditEvent
from app.shared.errors import AppError
from app.shared.observability import count_event, current_correlation_id


def enforce_maker_checker(checker_id, maker_id, last_editor_id=None) -> None:
    """Checker tidak boleh sama dengan Maker maupun Penyunting Terakhir (SoD)."""
    if str(checker_id) == str(maker_id):
        count_event("sod_violation_blocked")
        raise AppError(403, "SOD_VIOLATION", "Checker tidak boleh sama dengan Maker")
    if last_editor_id is not None and str(checker_id) == str(last_editor_id):
        raise AppError(403, "SOD_VIOLATION", "Checker tidak boleh sama dengan Penyunting Terakhir")


def audit(db: Session, actor_id, action: str, object_type: str, object_id=None,
          before: Optional[dict] = None, after: Optional[dict] = None, correlation_id=None) -> None:
    """Append-only (dilindungi trigger DB). Di-commit bersama transaksi pemanggil."""
    db.add(AuditEvent(actor_type="USER" if actor_id else "SYSTEM", actor_id=actor_id, action=action,
                      object_type=object_type, object_id=object_id, before_state=before, after_state=after,
                      correlation_id=correlation_id or current_correlation_id()))


def record_approval(db: Session, *, object_type: str, object_id, control_point: int, maker_id,
                    last_editor_id, checker_id, outcome: str, reason: Optional[str], snapshot: dict[str, Any]) -> Approval:
    enforce_maker_checker(checker_id, maker_id, last_editor_id)
    ap = Approval(object_type=object_type, object_id=object_id, control_point=control_point, maker_id=maker_id,
                  last_editor_id=last_editor_id, checker_id=checker_id, outcome=outcome, reason=reason,
                  object_state_snapshot=snapshot)
    db.add(ap)
    return ap
