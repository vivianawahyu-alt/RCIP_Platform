"""Membangkitkan docs/data_dictionary.md dan docs/erd.md langsung dari skema database yang sudah dimigrasi,
sehingga dokumentasi selalu sesuai dengan DDL (bukan ditulis tangan). `python -m seed.data_dictionary`"""
from collections import defaultdict
from pathlib import Path

from sqlalchemy import text

from app.shared.database import SessionLocal

DOCS = Path(__file__).resolve().parents[1] / "docs"
SCHEMAS = ("platform", "corpus", "compliance")
TABLES = {
    "platform.app_user": "Akun pengguna dan perannya (8 persona + tambahan sintetis). Password PBKDF2.",
    "platform.audit_event": "Jejak audit append-only (trigger menolak UPDATE/DELETE). Setiap transisi status.",
    "platform.outbox": "Event domain (transactional outbox) untuk pemrosesan asinkron oleh worker.",
    "platform.approval": "Keputusan maker-checker pada 6 titik kendali; append-only; snapshot status objek.",
    "platform.ai_call_log": "Setiap panggilan AI: templat+versi, model, prompt, respons mentah, validasi skema, grounding.",
    "platform.config": "Parameter runtime teraudit (FR-GOV-007) dengan batas min/maks.",
    "corpus.regulatory_source": "Otoritas/portal asal dokumen (OJK, BI, JDIH).",
    "corpus.document": "Identitas peraturan (nomor kanonik unik) dan status keberlakuannya.",
    "corpus.document_version": "Versi imutabel sebuah dokumen setelah PUBLISHED (trigger).",
    "corpus.provision": "Identitas ketentuan (Pasal) lintas versi.",
    "corpus.provision_version": "Teks ketentuan pada versi tertentu; target semua sitasi; imutabel bila versinya terbit.",
    "corpus.change_set": "Perbandingan dua versi dokumen.",
    "corpus.change": "Perubahan per ketentuan + status reviu W5 (titik kendali #1) dan permukaan dampak.",
    "corpus.relationship": "Silsilah antardokumen (mengubah/mencabut/merujuk) dengan sitasi penetap.",
    "corpus.taxonomy_label": "Label taksonomi terkendali (tema, populasi) — saran aturan dikonfirmasi manusia.",
    "compliance.organisation_profile": "Profil organisasi sintetis berversi; dasar keputusan keberlakuan.",
    "compliance.applicability_decision": "Keputusan keberlakuan W7 (titik kendali #2) dengan sitasi & snapshot profil.",
    "compliance.obligation": "Kewajiban terstruktur; AI_DRAFT tidak pernah dihitung/dipetakan (ditegakkan DB).",
    "compliance.risk": "Risiko ketidakpatuhan per kewajiban.",
    "compliance.control": "Kontrol mitigasi beserta pemiliknya.",
    "compliance.obligation_control_map": "Pemetaan banyak-ke-banyak kewajiban ↔ kontrol (trigger memblokir draf AI).",
    "compliance.evidence": "Bukti kontrol / bukti penutupan tindakan; ACCEPTED imutabel (trigger).",
    "compliance.assessment": "Kesimpulan efektivitas desain & operasional; sign-off (titik kendali #4).",
    "compliance.finding": "Temuan W12 dengan severity, pemilik, target, penutupan (titik kendali #5).",
    "compliance.remediation_action": "Tindakan remediasi dengan tenggat asli + riwayat perpanjangan.",
    "compliance.compliance_report": "Laporan W14; ISSUED imutabel (trigger), penerbit ≠ pembangkit (titik kendali #6).",
}
COLUMNS = {
    "state": "Status siklus hidup (kosakata tertutup, lihat CHECK).",
    "primary_citation_id": "Sitasi wajib ke provision_version — inti ketertelusuran.",
    "derived_from_ai": "True bila dibuat dari draf AI.",
    "supporting_phrases": "Kutipan verbatim dari teks pasal yang mendasari draf AI (explainability).",
    "low_confidence": "Keyakinan AI di bawah ai.confidence_floor; wajib konfirmasi tinjauan manual.",
    "relied_upon_attributes": "Snapshot atribut profil yang dijadikan dasar keputusan.",
    "object_state_snapshot": "Salinan status objek saat keputusan diambil.",
    "sha256": "Checksum isi berkas/teks.",
    "extension_history": "Riwayat perpanjangan tenggat (tanggal asli dipertahankan).",
    "impact": "Daftar objek hilir yang ditandai saat perubahan material dikonfirmasi.",
    "payload": "Isi laporan yang dibekukan saat terbit (DRR-07).",
    "correlation_id": "ID korelasi permintaan (X-Correlation-Id).",
    "text_search": "Vektor pencarian full-text bahasa Indonesia (kolom terhitung).",
}


def main() -> None:
    db = SessionLocal()
    cols = db.execute(text("""SELECT table_schema, table_name, column_name, data_type, is_nullable, column_default
        FROM information_schema.columns WHERE table_schema = ANY(:s) ORDER BY table_schema, table_name, ordinal_position"""),
                      {"s": list(SCHEMAS)}).all()
    fks = db.execute(text("""SELECT tc.table_schema||'.'||tc.table_name, kcu.column_name, ccu.table_schema||'.'||ccu.table_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
        JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = ANY(:s)"""), {"s": list(SCHEMAS)}).all()
    pks = {(r[0], r[1]) for r in db.execute(text("""SELECT tc.table_schema||'.'||tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu
        ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = ANY(:s)"""), {"s": list(SCHEMAS)}).all()}
    checks = db.execute(text("""SELECT n.nspname||'.'||t.relname, c.conname, pg_get_constraintdef(c.oid)
        FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE c.contype = 'c' AND n.nspname = ANY(:s) ORDER BY 1, 2"""), {"s": list(SCHEMAS)}).all()
    triggers = db.execute(text("""SELECT event_object_schema||'.'||event_object_table, trigger_name, string_agg(event_manipulation, '/')
        FROM information_schema.triggers WHERE event_object_schema = ANY(:s) GROUP BY 1, 2 ORDER BY 1"""), {"s": list(SCHEMAS)}).all()
    rowcount = {}
    for t in TABLES:
        try:
            rowcount[t] = db.execute(text(f"SELECT count(*) FROM {t}")).scalar()
        except Exception:
            db.rollback()
    fk_map = {(a, b): c for a, b, c in fks}
    by_table = defaultdict(list)
    for s, t, c, typ, nul, default in cols:
        by_table[f"{s}.{t}"].append((c, typ, nul, default))
    chk, trg = defaultdict(list), defaultdict(list)
    for t, n, d in checks:
        chk[t].append((n, d))
    for t, n, e in triggers:
        trg[t].append((n, e))

    out = ["# Data Dictionary RCIP", "",
           "_Dibangkitkan otomatis oleh `python -m seed.data_dictionary` dari skema database (migrasi 001–003). "
           "Jangan disunting manual; jalankan ulang setelah migrasi baru._", "",
           "Konvensi: semua ID UUID v4; waktu `timestamptz` (UTC); tanggal hukum `date`. Kolom berlabel **PK**/**FK** "
           "menunjukkan kunci; FK memakai `ON DELETE RESTRICT` sehingga rantai tidak dapat terputus.", "",
           "| Tabel | Deskripsi | Baris (DB saat dibangkitkan) |", "|---|---|---|"]
    for t in by_table:
        out.append(f"| `{t}` | {TABLES.get(t, '')} | {rowcount.get(t, '-')} |")
    for t, columns in by_table.items():
        out += ["", f"## `{t}`", "", TABLES.get(t, ""), "", "| Kolom | Tipe | Null | Kunci | Keterangan |", "|---|---|---|---|---|"]
        for c, typ, nul, default in columns:
            key = "PK" if (t, c) in pks else (f"FK → `{fk_map[(t, c)]}`" if (t, c) in fk_map else "")
            note = COLUMNS.get(c, "")
            if default and "nextval" not in str(default) and "gen_random_uuid" not in str(default):
                note = (note + f" Default: `{default}`.").strip()
            out.append(f"| `{c}` | {typ} | {'ya' if nul == 'YES' else 'tidak'} | {key} | {note} |")
        if chk.get(t):
            out += ["", "Aturan (CHECK):"] + [f"- `{n}`: `{d}`" for n, d in chk[t]]
        if trg.get(t):
            out += ["", "Trigger:"] + [f"- `{n}` ({e})" for n, e in trg[t]]
    (DOCS / "data_dictionary.md").write_text("\n".join(out) + "\n", encoding="utf-8")

    erd = ["# ERD RCIP", "", "_Dibangkitkan otomatis dari foreign key database (`python -m seed.data_dictionary`)._", "",
           "Rantai inti: sumber → dokumen → versi → ketentuan → perubahan → keberlakuan → kewajiban → risiko/kontrol → "
           "asesmen → bukti → temuan → remediasi → persetujuan → laporan → audit.", "", "```mermaid", "erDiagram"]
    name = lambda t: t.replace(".", "__")  # noqa: E731
    for t, columns in by_table.items():
        erd.append(f"    {name(t)} {{")
        for c, typ, _, _ in columns[:12]:
            k = " PK" if (t, c) in pks else (" FK" if (t, c) in fk_map else "")
            erd.append(f"        {typ.replace(' ', '_')} {c}{k}")
        erd.append("    }")
    seen = set()
    for (t, c), target in sorted(fk_map.items()):
        if target == "platform.app_user" or (t, target, c) in seen:
            continue  # relasi aktor ke app_user diringkas agar diagram terbaca
        seen.add((t, target, c))
        erd.append(f'    {name(target)} ||--o{{ {name(t)} : "{c}"')
    erd += ["```", "", "Catatan: kolom aktor (`*_by`, `owner_id`, `maker_id`, …) semuanya FK ke `platform.app_user` dan "
            "tidak digambar agar diagram terbaca. Hanya 12 kolom pertama tiap tabel yang ditampilkan; daftar lengkap ada di "
            "[data_dictionary.md](data_dictionary.md)."]
    (DOCS / "erd.md").write_text("\n".join(erd) + "\n", encoding="utf-8")
    print(f"Ditulis: {DOCS / 'data_dictionary.md'} dan {DOCS / 'erd.md'} ({len(by_table)} tabel)")
    db.close()


if __name__ == "__main__":
    main()
