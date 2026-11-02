"""Validasi integritas data (sintetis maupun hasil pemakaian): `python -m seed.validate`.
Keluar dengan kode 1 bila ada invarian yang dilanggar. Dipakai juga oleh test otomatis."""
import sys

from sqlalchemy import text

from app.shared.database import SessionLocal

CHECKS = {
    "TC-TRACE-01 kewajiban tanpa sitasi valid": """SELECT o.id FROM compliance.obligation o
        LEFT JOIN corpus.provision_version pv ON pv.id = o.primary_citation_id WHERE pv.id IS NULL""",
    # kewajiban yang dibuka kembali (pernah disetujui) boleh tetap terpetakan (W9: pemetaan ikut ditinjau)
    "Draf AI (belum pernah divalidasi) terpetakan ke kontrol": """SELECT m.obligation_id FROM compliance.obligation_control_map m
        JOIN compliance.obligation o ON o.id = m.obligation_id WHERE o.state IN ('AI_DRAFT','IN_VALIDATION')
        AND NOT EXISTS (SELECT 1 FROM platform.approval a WHERE a.object_id = o.id AND a.outcome = 'APPROVED')""",
    "Kewajiban aktif tanpa pemilik": "SELECT id FROM compliance.obligation WHERE state IN ('ACTIVE','PENDING_APPROVAL') AND owner_id IS NULL",
    "Persetujuan dengan checker = maker (SoD)": "SELECT id FROM platform.approval WHERE checker_id = maker_id OR checker_id = last_editor_id",
    "Kewajiban ACTIVE tanpa persetujuan titik 3": """SELECT o.id FROM compliance.obligation o WHERE o.state='ACTIVE'
        AND o.approver_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM platform.approval a WHERE a.object_id=o.id AND a.outcome='APPROVED')""",
    "Temuan CLOSED tanpa persetujuan titik 5": """SELECT f.id FROM compliance.finding f WHERE f.state='CLOSED'
        AND NOT EXISTS (SELECT 1 FROM platform.approval a WHERE a.object_id=f.id AND a.control_point=5 AND a.outcome='APPROVED')""",
    "Temuan CLOSED dengan tindakan belum selesai": """SELECT f.id FROM compliance.finding f JOIN compliance.remediation_action r
        ON r.finding_id=f.id WHERE f.state='CLOSED' AND r.state NOT IN ('DONE','CANCELLED')""",
    "Tindakan DONE tanpa bukti ACCEPTED": """SELECT r.id FROM compliance.remediation_action r WHERE r.state='DONE'
        AND NOT EXISTS (SELECT 1 FROM compliance.evidence e WHERE e.remediation_action_id=r.id AND e.state='ACCEPTED')""",
    "Bukti ACCEPTED tanpa rasional": "SELECT id FROM compliance.evidence WHERE state='ACCEPTED' AND (review_rationale IS NULL OR review_rationale='')",
    "Asesmen SIGNED_OFF oleh asesor sendiri": "SELECT id FROM compliance.assessment WHERE state='SIGNED_OFF' AND (signed_off_by IS NULL OR signed_off_by=assessed_by)",
    "Asesmen tanpa bukti ACCEPTED pada kontrol": """SELECT a.id FROM compliance.assessment a WHERE NOT EXISTS
        (SELECT 1 FROM compliance.evidence e WHERE e.control_id=a.control_id AND e.state='ACCEPTED')
        AND a.design_rationale NOT LIKE 'Dimigrasikan%'""",
    "Laporan ISSUED/SUPERSEDED tanpa penerbit berbeda": """SELECT id FROM compliance.compliance_report WHERE state IN ('ISSUED','SUPERSEDED')
        AND (issued_by IS NULL OR (issued_by = generated_by AND disclaimer_version <> 'legacy'))""",
    "Keputusan keberlakuan APPROVED tanpa penyetuju": "SELECT id FROM compliance.applicability_decision WHERE state='APPROVED' AND approver_id IS NULL AND submitted_at IS NOT NULL",
    "Perubahan MATERIAL_CONFIRMED tanpa persetujuan titik 1": """SELECT c.id FROM corpus.change c WHERE c.review_state='MATERIAL_CONFIRMED'
        AND NOT EXISTS (SELECT 1 FROM platform.approval a WHERE a.object_id=c.id AND a.control_point=1)""",
    "Temuan tanpa kewajiban tertaut": "SELECT f.id FROM compliance.finding f LEFT JOIN compliance.obligation o ON o.id=f.obligation_id WHERE o.id IS NULL",
}

WARNINGS = {
    "Asesmen warisan (sebelum tahap 2) perlu diulang dengan bukti diterima":
        "SELECT id FROM compliance.assessment WHERE design_rationale LIKE 'Dimigrasikan%'",
    "Kontrol tanpa pemilik": "SELECT id FROM compliance.control WHERE owner_id IS NULL",
    "Tindakan lewat tenggat": "SELECT id FROM compliance.remediation_action WHERE state IN ('OPEN','IN_PROGRESS') AND due_date < current_date",
    "Dokumen berstatus UNKNOWN": "SELECT id FROM corpus.document WHERE status = 'UNKNOWN'",
}

SUMMARY = {
    "dokumen": "SELECT count(*) FROM corpus.document", "versi": "SELECT count(*) FROM corpus.document_version",
    "pasal (versi)": "SELECT count(*) FROM corpus.provision_version", "perubahan": "SELECT count(*) FROM corpus.change",
    "keputusan keberlakuan": "SELECT count(*) FROM compliance.applicability_decision",
    "kewajiban": "SELECT count(*) FROM compliance.obligation", "kontrol": "SELECT count(*) FROM compliance.control",
    "bukti": "SELECT count(*) FROM compliance.evidence", "asesmen": "SELECT count(*) FROM compliance.assessment",
    "temuan": "SELECT count(*) FROM compliance.finding", "temuan ditutup": "SELECT count(*) FROM compliance.finding WHERE state='CLOSED'",
    "tindakan": "SELECT count(*) FROM compliance.remediation_action", "persetujuan": "SELECT count(*) FROM platform.approval",
    "event audit": "SELECT count(*) FROM platform.audit_event", "laporan": "SELECT count(*) FROM compliance.compliance_report",
}


def run_checks(db) -> dict[str, list]:
    return {name: [str(r[0]) for r in db.execute(text(sql)).all()] for name, sql in CHECKS.items()}


def main() -> None:
    db = SessionLocal()
    try:
        bad = 0
        print("Ringkasan data:")
        for k, sql in SUMMARY.items():
            print(f"  {k:<24} {db.execute(text(sql)).scalar()}")
        print("\nInvarian:")
        for name, rows in run_checks(db).items():
            ok = not rows
            bad += not ok
            print(f"  [{'OK' if ok else 'GAGAL'}] {name}" + ("" if ok else f" — {len(rows)}: {', '.join(rows[:3])}"))
        print("\nPeringatan (bukan pelanggaran; anomali/data warisan yang perlu ditindaklanjuti):")
        for name, sql in WARNINGS.items():
            print(f"  [{len(db.execute(text(sql)).all())}] {name}")
        print("\nHASIL:", "SEMUA INVARIAN TERPENUHI" if not bad else f"{bad} invarian dilanggar")
        sys.exit(1 if bad else 0)
    finally:
        db.close()


if __name__ == "__main__":
    main()
