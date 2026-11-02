"""Membangkitkan docs/openapi.json dan docs/api.md dari aplikasi FastAPI. `python -m app.api_docs`"""
import json
from collections import defaultdict
from pathlib import Path

from app.main import app

DOCS = Path(__file__).resolve().parents[1] / "docs"


def main() -> None:
    spec = app.openapi()
    DOCS.mkdir(exist_ok=True)
    (DOCS / "openapi.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    groups = defaultdict(list)
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            tag = (op.get("tags") or ["lain"])[0]
            desc = (op.get("description") or op.get("summary") or "").strip().splitlines()[0] if (op.get("description") or op.get("summary")) else ""
            groups[tag].append((path, method.upper(), desc))
    L = ["# Dokumentasi API RCIP v1", "",
         "_Dibangkitkan otomatis (`python -m app.api_docs`) dari kode. Spesifikasi lengkap: [openapi.json](openapi.json); "
         "Swagger interaktif saat aplikasi berjalan: http://localhost:8000/docs._", "",
         "## Konvensi", "",
         "- Base path `/api/v1`; semua endpoint kecuali `/auth/login` dan `/health` memerlukan `Authorization: Bearer <JWT>`.",
         "- Respons sukses: `{success, message, data, timestamp}`.",
         "- Error (RFC 7807 + field lama): `{success:false, error_code, message, type, title, status, code, detail, instance, correlation_id, offending}`.",
         "- Kirim `X-Correlation-Id` (UUID) untuk menelusuri permintaan; server mengembalikannya di header respons dan mencatatnya di audit.",
         "- Otorisasi ditegakkan di server per peran (matriks FRD §4.2); UI hanya cermin.", "",
         "## Kode error penting", "",
         "| Kode | Arti |", "|---|---|",
         "| `SOD_VIOLATION` | Checker sama dengan maker / penyunting terakhir / pemilik tindakan |",
         "| `AI_DRAFT_BLOCKED` | Draf AI belum divalidasi tidak boleh dipetakan/ditautkan |",
         "| `APPLICABILITY_NOT_APPROVED` | Ekstraksi butuh keputusan keberlakuan yang disetujui |",
         "| `LOW_CONFIDENCE_REVIEW_REQUIRED` | Draf berkeyakinan rendah wajib dikonfirmasi telah ditinjau |",
         "| `EVIDENCE_REQUIRED` / `CLOSURE_EVIDENCE_REQUIRED` | Butuh bukti berstatus ACCEPTED |",
         "| `EVIDENCE_IMMUTABLE` / `REPORT_IMMUTABLE` / `VERSION_IMMUTABLE` | Objek terkunci setelah diterima/terbit |",
         "| `DUE_DATE_EXCEEDS_WINDOW` | Tenggat melebihi jendela remediasi severity |",
         "| `SCAN_FAILED` | Berkas unggahan ditolak pemeriksaan keamanan |",
         "| `TOO_MANY_ATTEMPTS` | Pembatasan laju login |",
         "| `VALIDATION_ERROR` | Body/parameter tidak valid; lihat `offending.field` |", ""]
    for tag in sorted(groups):
        L += [f"## {tag}", "", "| Metode | Path | Keterangan |", "|---|---|---|"]
        for path, method, desc in sorted(groups[tag]):
            L.append(f"| {method} | `{path}` | {desc} |")
        L.append("")
    (DOCS / "api.md").write_text("\n".join(L), encoding="utf-8")
    print(f"Ditulis docs/api.md ({sum(len(v) for v in groups.values())} operasi) dan docs/openapi.json")


if __name__ == "__main__":
    main()
