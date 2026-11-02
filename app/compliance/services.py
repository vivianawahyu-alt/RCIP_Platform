import hashlib
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.compliance.models import Finding, Obligation, ObligationControlMap
from app.shared.errors import AppError
from app.platform.config_service import get_value, window_days
from app.shared.vocabularies import FindingSource, ObligationState

DISCLAIMER_VERSION = "2026-10-v1"
DISCLAIMER_TEMPLATE = (
    "Keluaran ini adalah draf hasil generasi, bukan nasihat hukum. Platform ini menstrukturkan teks peraturan yang "
    "tersedia untuk publik menjadi rekaman kepatuhan. Platform ini tidak memberikan nasihat hukum, tidak menggantikan "
    "profesional hukum atau kepatuhan, dan tidak membuat keputusan kepatuhan secara otonom. Platform ini tidak "
    "menyampaikan apa pun kepada regulator mana pun. Konten yang ditandai sebagai hasil generasi didraf oleh model AI "
    "dari ketentuan yang disitasi dan memerlukan validasi manusia. Indikasi dampak hanyalah indikasi, bukan kesimpulan "
    "hukum. Keluaran ini didasarkan pada korpus terkurasi berisi {n} dokumen publik dari {sources}, yang diambil pada "
    "{date}. Keluaran ini tidak merepresentasikan cakupan peraturan Indonesia secara lengkap, dan kemutakhiran, "
    "kelengkapan, serta penafsiran hukum atas setiap ketentuan yang disitasi di sini tidak dijamin. Seluruh keputusan "
    "yang dicatat dalam platform ini dibuat oleh individu-individu yang namanya ditampilkan. Rujuklah teks peraturan "
    "asli dan konsultan hukum yang berkualifikasi sebelum mengambil tindakan."
)
OPEN_FINDING_STATES = ("OPEN", "ACTION_PLANNED", "IN_REMEDIATION", "PENDING_CLOSURE_VALIDATION", "REVIEW_REQUIRED")


def find_gaps(db: Session) -> list[Obligation]:
    """Kewajiban ACTIVE tanpa kontrol terpetakan."""
    stmt = (select(Obligation).outerjoin(ObligationControlMap, ObligationControlMap.obligation_id == Obligation.id)
            .where(Obligation.state == ObligationState.ACTIVE.value, ObligationControlMap.control_id.is_(None)))
    return list(db.scalars(stmt))


def scan_gaps_create_findings(db: Session, raised_by=None) -> list[Finding]:
    """FR-EVR-004: kesenjangan cakupan → temuan otomatis (tidak menduplikasi temuan yang masih terbuka)."""
    created = []
    for ob in find_gaps(db):
        exists = db.scalar(select(Finding.id).where(Finding.obligation_id == ob.id, Finding.kind == "COMPLIANCE_GAP",
                                                    Finding.state.in_(OPEN_FINDING_STATES)))
        if exists:
            continue
        summary = (ob.plain_language_summary or ob.original_text)[:200]
        f = Finding(obligation_id=ob.id, kind="COMPLIANCE_GAP", source_type=FindingSource.COVERAGE_GAP.value,
                    severity="HIGH", title=f"Kewajiban tanpa kontrol: {summary[:90]}{'…' if len(summary) > 90 else ''}",
                    description=f"Kewajiban aktif tanpa kontrol: {summary}", owner_id=ob.owner_id,
                    raised_by=raised_by, target_closure_date=date.today() + timedelta(days=window_days(db, "HIGH")))
        db.add(f)
        created.append(f)
    db.flush()
    return created


def verify_report_traceability(db: Session) -> None:
    """DRR-08/DRR-11: setiap kewajiban punya sitasi valid ke versi terbit; dokumen UNKNOWN memblokir."""
    orphans = db.execute(text("""
        SELECT o.id FROM compliance.obligation o
        LEFT JOIN corpus.provision_version pv ON pv.id = o.primary_citation_id
        LEFT JOIN corpus.document_version dv ON dv.id = pv.document_version_id
        WHERE pv.id IS NULL OR dv.id IS NULL""")).fetchall()
    if orphans:
        raise AppError(422, "REPORT_TRACEABILITY_CHECK_FAILED",
                       f"{len(orphans)} kewajiban tanpa sitasi valid: {', '.join(str(o.id) for o in orphans[:5])}")
    unknown = db.execute(text("""
        SELECT DISTINCT d.canonical_number FROM compliance.obligation o
        JOIN corpus.provision_version pv ON pv.id = o.primary_citation_id
        JOIN corpus.document_version dv ON dv.id = pv.document_version_id
        JOIN corpus.document d ON d.id = dv.document_id
        WHERE o.state = 'ACTIVE' AND d.status = 'UNKNOWN'""")).fetchall()
    if unknown:
        raise AppError(422, "REPORT_SCOPE_UNKNOWN_DOCUMENT",
                       f"Lingkup laporan memuat dokumen berstatus UNKNOWN: {', '.join(r[0] for r in unknown)}")


def _ids(db: Session, sql: str, **params) -> list[str]:
    return [str(r[0]) for r in db.execute(text(sql), params).all()]


# Asesmen terakhir yang sudah SIGNED_OFF per kontrol
LATEST_SIGNED = """(SELECT a.operating_result FROM compliance.assessment a WHERE a.control_id = m.control_id
                    AND a.state = 'SIGNED_OFF' ORDER BY a.assessed_at DESC LIMIT 1)"""


def dashboard_metrics(db: Session) -> dict:
    """FRD §14: setiap angka dapat ditelusuri (drill), menyatakan as-at, pembilang & penyebut; AI_DRAFT dikecualikan."""
    q = lambda sql, **p: db.execute(text(sql), p).scalar() or 0  # noqa: E731
    today = date.today()
    active_ids = _ids(db, "SELECT id FROM compliance.obligation WHERE state='ACTIVE'")
    covered_ids = _ids(db, """SELECT DISTINCT o.id FROM compliance.obligation o
        JOIN compliance.obligation_control_map m ON m.obligation_id=o.id WHERE o.state='ACTIVE'""")
    effective_ids = _ids(db, f"""SELECT DISTINCT o.id FROM compliance.obligation o
        JOIN compliance.obligation_control_map m ON m.obligation_id=o.id
        WHERE o.state='ACTIVE' AND {LATEST_SIGNED} = 'EFFECTIVE'""")
    gap_ids = sorted(set(active_ids) - set(covered_ids))
    partial_ids = sorted(set(covered_ids) - set(effective_ids))
    states = {k: v for k, v in db.execute(text("SELECT state, count(*) FROM compliance.obligation GROUP BY state")).all()}
    validated_states = {k: v for k, v in states.items() if k not in ("AI_DRAFT", "IN_VALIDATION")}

    open_finding_ids = _ids(db, "SELECT id FROM compliance.finding WHERE state = ANY(:s)", s=list(OPEN_FINDING_STATES))
    by_sev = {s: 0 for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW")}
    by_sev.update(dict(db.execute(text("""SELECT severity, count(*) FROM compliance.finding
        WHERE state = ANY(:s) GROUP BY severity"""), {"s": list(OPEN_FINDING_STATES)}).all()))
    finding_states = dict(db.execute(text("SELECT state, count(*) FROM compliance.finding GROUP BY state")).all())
    overdue_action_ids = _ids(db, """SELECT id FROM compliance.remediation_action
        WHERE state IN ('OPEN','IN_PROGRESS') AND due_date < :t""", t=today)
    overdue_finding_ids = _ids(db, """SELECT id FROM compliance.finding
        WHERE state = ANY(:s) AND target_closure_date < :t""", s=list(OPEN_FINDING_STATES), t=today)
    review_required_ids = _ids(db, "SELECT id FROM compliance.obligation WHERE state='REVIEW_REQUIRED'")
    assess_states = dict(db.execute(text("SELECT state, count(*) FROM compliance.assessment GROUP BY state")).all())
    latest_results = dict(db.execute(text("""
        SELECT r, count(*) FROM (
          SELECT DISTINCT ON (control_id) control_id, operating_result AS r FROM compliance.assessment
          WHERE state='SIGNED_OFF' ORDER BY control_id, assessed_at DESC) t GROUP BY r""")).all())
    controls_total = q("SELECT count(*) FROM compliance.control")
    controls_no_owner = _ids(db, "SELECT id FROM compliance.control WHERE owner_id IS NULL")
    obligations_no_owner = _ids(db, "SELECT id FROM compliance.obligation WHERE state='ACTIVE' AND owner_id IS NULL")
    evidence_pending = q("SELECT count(*) FROM compliance.evidence WHERE state='SUBMITTED'")
    accepted_risk_overdue = _ids(db, """SELECT id FROM compliance.finding
        WHERE state='RISK_ACCEPTED' AND risk_review_date < :t""", t=today)

    material_gaps = [dict(r._mapping) for r in db.execute(text("""
        SELECT o.id::text AS obligation_id, o.plain_language_summary AS summary, u.username AS owner,
               d.canonical_number, p.number_label, (current_date - o.created_at::date) AS age_days
        FROM compliance.obligation o
        JOIN corpus.provision_version pv ON pv.id = o.primary_citation_id
        JOIN corpus.provision p ON p.id = pv.provision_id
        JOIN corpus.document_version dv ON dv.id = pv.document_version_id
        JOIN corpus.document d ON d.id = dv.document_id
        LEFT JOIN platform.app_user u ON u.id = o.owner_id
        WHERE o.id = ANY(CAST(:ids AS uuid[])) ORDER BY o.created_at"""), {"ids": gap_ids}).all()]
    upcoming = [dict(r._mapping) for r in db.execute(text("""
        SELECT r.id::text AS action_id, r.finding_id::text AS finding_id, r.description, r.due_date::text AS due_date,
               r.state, u.username AS owner, f.severity, (r.due_date < current_date) AS overdue
        FROM compliance.remediation_action r
        JOIN compliance.finding f ON f.id = r.finding_id
        LEFT JOIN platform.app_user u ON u.id = r.owner_id
        WHERE r.state IN ('OPEN','IN_PROGRESS') AND r.due_date <= current_date + 30
        ORDER BY r.due_date LIMIT 20""")).all()]
    corpus = dict(db.execute(text("SELECT status, count(*) FROM corpus.document GROUP BY status")).all())
    corpus_by_source = dict(db.execute(text("""SELECT s.name, count(d.id) FROM corpus.regulatory_source s
        LEFT JOIN corpus.document d ON d.source_id = s.id GROUP BY s.name""")).all())
    sla = int(get_value(db, "change.review_sla_days"))
    change_states = dict(db.execute(text("SELECT review_state, count(*) FROM corpus.change GROUP BY review_state")).all())
    changes_over_sla = _ids(db, """SELECT c.id FROM corpus.change c JOIN corpus.change_set cs ON cs.id = c.change_set_id
        WHERE c.review_state IN ('DETECTED','IN_REVIEW','ESCALATED') AND cs.created_at < now() - make_interval(days => :d)""", d=sla)
    appl_states = dict(db.execute(text("SELECT state, count(*) FROM compliance.applicability_decision GROUP BY state")).all())

    active, effective = len(active_ids), len(effective_ids)
    return {
        "as_at": datetime.now(timezone.utc).isoformat(),
        "active_obligations": active, "with_control": len(covered_ids), "with_effective_control": effective,
        "gaps": len(gap_ids), "partial_coverage": len(partial_ids),
        "open_findings": len(open_finding_ids),
        "compliance_score_percent": round(100 * effective / active, 1) if active else 0.0,
        "compliance_score": {"numerator": effective, "denominator": active,
                             "basis": "kewajiban ACTIVE dengan kontrol yang asesmen terakhirnya SIGNED_OFF & EFFECTIVE"},
        "obligations_by_state": states, "validated_obligations_by_state": validated_states,
        "excluded_ai_draft": states.get("AI_DRAFT", 0),
        "findings_by_severity": by_sev, "findings_by_state": finding_states,
        "risk_accepted": finding_states.get("RISK_ACCEPTED", 0),
        "overdue_actions": len(overdue_action_ids), "overdue_findings": len(overdue_finding_ids),
        "review_required": len(review_required_ids),
        "assessments_by_state": assess_states, "latest_signed_results": latest_results,
        "assessments_pending_signoff": assess_states.get("PENDING_SIGNOFF", 0),
        "evidence_pending_review": evidence_pending,
        "controls_total": controls_total, "controls_without_owner": len(controls_no_owner),
        "obligations_without_owner": len(obligations_no_owner),
        "accepted_risk_review_overdue": len(accepted_risk_overdue),
        "material_gaps": material_gaps, "upcoming_deadlines": upcoming, "corpus_by_status": corpus,
        "corpus_by_source": corpus_by_source, "change_review_states": change_states,
        "changes_pending_review": sum(change_states.get(k, 0) for k in ("DETECTED", "IN_REVIEW", "ESCALATED")),
        "changes_pending_confirmation": change_states.get("VALIDATED", 0), "changes_over_sla": len(changes_over_sla),
        "change_review_sla_days": sla, "applicability_by_state": appl_states,
        "applicability_pending": appl_states.get("PENDING_APPROVAL", 0) + appl_states.get("PENDING_LEGAL", 0),
        "applicability_review_required": appl_states.get("REVIEW_REQUIRED", 0),
        "drill": {"gaps": gap_ids, "partial_coverage": partial_ids, "effective": effective_ids,
                  "open_findings": open_finding_ids, "overdue_actions": overdue_action_ids,
                  "overdue_findings": overdue_finding_ids, "review_required": review_required_ids,
                  "controls_without_owner": controls_no_owner, "accepted_risk_review_overdue": accepted_risk_overdue,
                  "changes_over_sla": changes_over_sla},
    }


def corpus_basis(db: Session) -> dict:
    by_source = [dict(r._mapping) for r in db.execute(text("""
        SELECT s.name AS source, count(d.id) AS documents FROM corpus.regulatory_source s
        LEFT JOIN corpus.document d ON d.source_id = s.id GROUP BY s.name ORDER BY s.name""")).all()]
    n = sum(r["documents"] for r in by_source)
    return {"documents_total": n, "by_source": by_source,
            "sources": ", ".join(r["source"] for r in by_source if r["documents"]) or "-",
            "retrieved_at": date.today().isoformat(),
            "completeness_statement": f"Korpus terkurasi {n} dokumen; bukan cakupan regulasi Indonesia yang lengkap.",
            "quality_warnings": ["Data korpus seed bersifat SINTETIS untuk demonstrasi"] if n < 30 else []}


def disclaimer(basis: dict) -> str:
    return DISCLAIMER_TEMPLATE.format(n=basis["documents_total"], sources=basis["sources"], date=basis["retrieved_at"])


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
