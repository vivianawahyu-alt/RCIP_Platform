"""Tampilan Eksekutif (Direksi, hanya baca): ringkasan postur kepatuhan."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.compliance import services
from app.compliance.services import LATEST_SIGNED, OPEN_FINDING_STATES
from app.platform.models import AppUser
from app.platform.permissions import require
from app.shared import vocabularies as V
from app.shared.database import get_db
from app.shared.schemas import ResponseWrapper

router = APIRouter(prefix="/api/v1/compliance/executive", tags=["executive"])
R = V.AppRole
EXEC_READ = require("dashboard", "R", only=[R.EXECUTIVE])


def _pct(part: int, whole: int) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


@router.get("/posture", response_model=ResponseWrapper[dict])
def posture(db: Session = Depends(get_db), user: AppUser = Depends(EXEC_READ)):
    m = services.dashboard_metrics(db)

    regs_in_force = db.execute(text("""
        SELECT count(DISTINCT dv.document_id)
        FROM compliance.obligation o
        JOIN corpus.provision_version pv ON pv.id = o.primary_citation_id
        JOIN corpus.document_version dv ON dv.id = pv.document_version_id
        WHERE o.state = 'ACTIVE'""")).scalar() or 0

    last_report = db.execute(text("""
        SELECT id::text AS id, title, issued_at::text AS issued_at
        FROM compliance.compliance_report WHERE state = 'ISSUED'
        ORDER BY issued_at DESC NULLS LAST LIMIT 1""")).first()
    reports_issued = db.execute(text(
        "SELECT count(*) FROM compliance.compliance_report WHERE state IN ('ISSUED','SUPERSEDED')")).scalar() or 0

    by_area = [dict(r._mapping) for r in db.execute(text(f"""
        WITH ob AS (
          SELECT o.id AS obligation_id, tl.value AS area
          FROM compliance.obligation o
          JOIN corpus.provision_version pv ON pv.id = o.primary_citation_id
          JOIN corpus.document_version dv ON dv.id = pv.document_version_id
          JOIN corpus.taxonomy_label tl ON tl.document_id = dv.document_id
          WHERE o.state = 'ACTIVE' AND tl.dimension = 'THEME' AND tl.state <> 'REMOVED'
        )
        SELECT ob.area,
               count(DISTINCT ob.obligation_id) AS obligations,
               count(DISTINCT ob.obligation_id) FILTER (WHERE EXISTS (
                   SELECT 1 FROM compliance.obligation_control_map m
                   WHERE m.obligation_id = ob.obligation_id AND {LATEST_SIGNED} = 'EFFECTIVE')) AS effective,
               count(DISTINCT f.id) FILTER (WHERE f.state = ANY(:open)) AS open_findings
        FROM ob LEFT JOIN compliance.finding f ON f.obligation_id = ob.obligation_id
        GROUP BY ob.area ORDER BY count(DISTINCT ob.obligation_id) DESC, ob.area"""),
        {"open": list(OPEN_FINDING_STATES)}).all()]
    for a in by_area:
        a["effective_percent"] = _pct(a["effective"], a["obligations"])

    new_regs = [dict(r._mapping) for r in db.execute(text("""
        SELECT d.id::text AS document_id, d.canonical_number, d.title_id, d.issuer,
               dv.version_number, dv.effective_date::text AS effective_date
        FROM corpus.document_version dv JOIN corpus.document d ON d.id = dv.document_id
        WHERE dv.state = 'PUBLISHED'
        ORDER BY dv.effective_date DESC, d.canonical_number LIMIT 5""")).all()]

    return ResponseWrapper(data={
        "as_at": m["as_at"],
        "kpis": {
            "active_obligations": m["active_obligations"], "regulations_in_force": int(regs_in_force),
            "effective_percent": m["compliance_score_percent"], "effective_count": m["with_effective_control"],
            "open_findings": m["open_findings"], "overdue_findings": m["overdue_findings"],
            "reports_issued": int(reports_issued),
            "last_report": dict(last_report._mapping) if last_report else None,
        },
        "basis": m["compliance_score"]["basis"],
        "by_area": by_area,
        "new_regulations": new_regs,
    })