"""FR-GOV-007: parameter runtime disimpan di DB, setiap perubahan diaudit (sebelum/sesudah + justifikasi).
Sengaja TIDAK ada kunci yang dapat mematikan audit, pemisahan tugas, atau pelabelan AI (TC-GOV-11)."""
from sqlalchemy.orm import Session

from app.platform.models import Config

DEFAULTS = {
    "ai.confidence_floor": 0.70, "ai.relevance_floor": 0.05, "change.review_sla_days": 7,
    "remediation.window_days.CRITICAL": 30, "remediation.window_days.HIGH": 60,
    "remediation.window_days.MEDIUM": 90, "remediation.window_days.LOW": 180,
    "evidence.max_file_mb": 25, "auth.max_failed_logins_per_minute": 5,
}


def get_value(db: Session, key: str) -> float:
    try:
        row = db.get(Config, key)
    except Exception:  # tabel belum dimigrasi
        db.rollback()
        row = None
    return float(row.value) if row is not None else float(DEFAULTS[key])


def window_days(db: Session, severity: str) -> int:
    return int(get_value(db, f"remediation.window_days.{severity}"))
