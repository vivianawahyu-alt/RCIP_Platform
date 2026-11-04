"""Hapus HANYA data buatan tes otomatis dari database website, data lain tetap utuh.

    python -m seed.cleanup_test_data           # pratinjau: hanya menampilkan apa yang akan dihapus
    python -m seed.cleanup_test_data --apply   # benar-benar menghapus

Yang dihapus:
  1. Dokumen tes: nomor regulasi berpola  POJK TEST/xxxxxx, POJK GOV/xxxxxx, POJK OCR/xxxxxx, ZZZ UJI/xxxxxx
     (xxxxxx = 6 karakter heksadesimal acak yang dibuat tes, jadi dokumen buatan manusia tidak ikut terhapus)
  2. Semua yang bergantung pada dokumen itu (versi, pasal, perubahan, keberlakuan, kewajiban, risiko, kontrol,
     bukti, asesmen, temuan, remediasi), ditelusuri otomatis lewat foreign key
  3. Kontrol yang HANYA dipetakan ke kewajiban tes (kontrol yang juga dipakai kewajiban lain tetap aman)
  4. Laporan yang isinya memuat kewajiban tes (laporan itu tidak lagi valid tanpa kewajibannya)

Yang TIDAK dihapus: jejak audit, catatan persetujuan, dan log AI. Ketiganya append-only (prinsip auditabilitas).

Pengaman:
  - bawaan mode pratinjau; penghapusan hanya dengan --apply
  - semua dalam SATU transaksi; sebelum commit, seluruh foreign key diperiksa. Bila ada rujukan yang
    putus, transaksi dibatalkan dan database kembali seperti semula.
"""
import argparse
import sys
from collections import defaultdict

from sqlalchemy import text

from app.shared.database import SessionLocal

# 6 karakter heksadesimal = uuid4().hex[:6] yang dipakai tes
TEST_DOC_REGEX = r"^(POJK TEST|POJK GOV|POJK OCR|ZZZ UJI)/[0-9a-f]{6}(/|$)"


def _fk_graph(db):
    """Daftar foreign key ke kolom `id`: (tabel anak, kolom anak, tabel induk). Dibaca langsung dari katalog
    PostgreSQL, jadi tabel baru di migrasi berikutnya otomatis ikut ditelusuri."""
    rows = db.execute(text("""
        SELECT c.conrelid::regclass::text, a.attname, c.confrelid::regclass::text
        FROM pg_constraint c
        JOIN pg_attribute a  ON a.attrelid = c.conrelid  AND a.attnum = c.conkey[1]
        JOIN pg_attribute af ON af.attrelid = c.confrelid AND af.attnum = c.confkey[1]
        WHERE c.contype = 'f' AND af.attname = 'id'
          AND c.connamespace::regnamespace::text IN ('corpus', 'compliance')""")).all()
    return [(child, col, parent) for child, col, parent in rows]


def _has_id(db, table: str) -> bool:
    schema, name = table.split(".")
    return bool(db.scalar(text("""SELECT 1 FROM information_schema.columns
        WHERE table_schema = :s AND table_name = :t AND column_name = 'id'"""), {"s": schema, "t": name}))


def _expand(db, fks, todo: dict[str, set]) -> None:
    """Tambahkan ke `todo` semua baris yang (langsung/tidak langsung) merujuk baris yang akan dihapus."""
    changed = True
    while changed:  # ulangi sampai tidak ada baris baru (fixpoint)
        changed = False
        for child, col, parent in fks:
            ids = todo.get(parent)
            if not ids or not _has_id(db, child):
                continue
            found = {r[0] for r in db.execute(text(f"SELECT id FROM {child} WHERE {col} = ANY(:ids)"),
                                              {"ids": list(ids)})}
            new = found - todo[child]
            if new:
                todo[child] |= new
                changed = True


def collect(db) -> dict[str, set]:
    fks = _fk_graph(db)
    todo: dict[str, set] = defaultdict(set)

    # 1) dokumen tes
    todo["corpus.document"] = {r[0] for r in db.execute(
        text("SELECT id FROM corpus.document WHERE canonical_number ~ :re"), {"re": TEST_DOC_REGEX})}
    _expand(db, fks, todo)

    # 3) kontrol yang semua pemetaannya ke kewajiban tes
    if todo["compliance.obligation"]:
        todo["compliance.control"] |= {r[0] for r in db.execute(text("""
            SELECT m.control_id FROM compliance.obligation_control_map m
            GROUP BY m.control_id
            HAVING bool_and(m.obligation_id = ANY(:ob))"""), {"ob": list(todo["compliance.obligation"])})}
        _expand(db, fks, todo)

    # 4) laporan yang memuat kewajiban tes (+ rantai revisinya)
    reports = set()
    for oid in todo["compliance.obligation"]:
        reports |= {r[0] for r in db.execute(text(
            "SELECT id FROM compliance.compliance_report WHERE payload::text LIKE :p"), {"p": f"%{oid}%"})}
    while True:  # laporan lama yang superseded_by-nya menunjuk laporan yang dihapus ikut dihapus
        more = {r[0] for r in db.execute(text(
            "SELECT id FROM compliance.compliance_report WHERE superseded_by = ANY(:ids)"), {"ids": list(reports)})} - reports
        if not more:
            break
        reports |= more
    todo["compliance.compliance_report"] |= reports
    return {k: v for k, v in todo.items() if v}


def _dangling(db) -> list[str]:
    """Cari foreign key yang menunjuk baris yang sudah tidak ada (di seluruh skema aplikasi)."""
    bad = []
    rows = db.execute(text("""
        SELECT c.conrelid::regclass::text, a.attname, c.confrelid::regclass::text, af.attname
        FROM pg_constraint c
        JOIN pg_attribute a  ON a.attrelid = c.conrelid  AND a.attnum = c.conkey[1]
        JOIN pg_attribute af ON af.attrelid = c.confrelid AND af.attnum = c.confkey[1]
        WHERE c.contype = 'f'""")).all()
    for child, col, parent, pcol in rows:
        n = db.scalar(text(f"""SELECT count(*) FROM {child} ch WHERE ch.{col} IS NOT NULL
            AND NOT EXISTS (SELECT 1 FROM {parent} p WHERE p.{pcol} = ch.{col})"""))
        if n:
            bad.append(f"{child}.{col} → {parent}: {n} baris")
    return bad


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="benar-benar menghapus (tanpa ini hanya pratinjau)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        todo = collect(db)
        docs = db.execute(text("SELECT canonical_number FROM corpus.document WHERE id = ANY(:ids) ORDER BY 1"),
                          {"ids": list(todo.get("corpus.document", []))}).scalars().all()
        print(f"Dokumen tes yang akan dihapus ({len(docs)}):")
        for d in docs:
            print("  -", d)
        print("\nJumlah baris per tabel:")
        for table, ids in sorted(todo.items()):
            print(f"  {table:<38} {len(ids)}")
        if not todo:
            print("  (tidak ada data tes)")
            return
        if not args.apply:
            print("\nPRATINJAU saja, belum ada yang dihapus. Jalankan lagi dengan --apply untuk menghapus.")
            return

        # Trigger imutabilitas (versi terbit, bukti, laporan) dinonaktifkan HANYA di transaksi ini.
        # Karena foreign key juga ikut tidak diperiksa, urutan & kelengkapan dijaga sendiri lalu diverifikasi.
        db.execute(text("SET LOCAL session_replication_role = replica"))
        fks = _fk_graph(db)
        ids_of = {t: list(v) for t, v in todo.items()}
        # tabel tanpa kolom id (mis. obligation_control_map): hapus berdasarkan kolom foreign key-nya
        for child, col, parent in fks:
            if parent in ids_of and not _has_id(db, child):
                db.execute(text(f"DELETE FROM {child} WHERE {col} = ANY(:ids)"), {"ids": ids_of[parent]})
        for table, ids in ids_of.items():
            db.execute(text(f"DELETE FROM {table} WHERE id = ANY(:ids)"), {"ids": ids})
        db.execute(text("SET LOCAL session_replication_role = origin"))

        bad = _dangling(db)
        if bad:
            db.rollback()
            print("\nDIBATALKAN: ada rujukan yang akan putus, tidak ada yang dihapus:")
            for b in bad:
                print("  -", b)
            sys.exit(1)
        db.commit()
        print("\nSELESAI: data tes dihapus. Jalankan `python -m seed.validate` untuk memeriksa integritas.")
    finally:
        db.close()


if __name__ == "__main__":
    main()