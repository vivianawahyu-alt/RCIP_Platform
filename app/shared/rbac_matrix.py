"""Matriks RBAC RCIP — SATU-SATUNYA sumber kebenaran hak akses per peran.

Isi file ini adalah salinan tabel "Kapabilitas × Peran" dari dokumen desain. Setiap baris tabel = satu kapabilitas
di bawah; setiap kolom tabel = satu peran, dengan urutan kolom yang SAMA dengan tabel:

    Analis Regulasi | Pejabat Kepatuhan | Pemilik Bisnis/Kontrol | Peninjau Hukum |
    Manajer Kepatuhan (Pemberi Persetujuan) | Auditor Internal | Eksekutif | Administrator Sistem

Legenda huruf (sama dengan tabel):
    C create · R read · U update · D delete (soft) · A approve/reject · X execute action · "" (kosong) = tanpa akses

Penanda lingkup setelah garis miring:
    "R/own"    → hanya objek milik sendiri (Pemilik Bisnis/Kontrol: kontrol, kewajiban, temuan, bukti miliknya)
    "C/draft"  → hanya boleh membuat DRAF (Analis pada Obligation)
    "C/propose"→ hanya boleh MENGUSULKAN (Pejabat pada penutupan Finding; keputusan tetap di Manajer)
    "R/system" → hanya event sistem (Administrator pada jejak audit)

Aturan turunan: huruf A (approve) otomatis mencakup R, karena penyetuju harus bisa membaca objek yang disetujui.

File ini sengaja TANPA import FastAPI/SQLAlchemy supaya mudah diuji murni (lihat tests/test_rbac_matrix.py) dan bisa
diekspor ke frontend (web/src/permissions.ts dibangkitkan dari file ini oleh scripts/gen_permissions_ts.py).
"""
from __future__ import annotations

from typing import Optional

from app.shared.vocabularies import AppRole

RA = AppRole.REGULATORY_ANALYST.value
CO = AppRole.COMPLIANCE_OFFICER.value
BCO = AppRole.BUSINESS_CONTROL_OWNER.value
LR = AppRole.LEGAL_REVIEWER.value
CM = AppRole.COMPLIANCE_MANAGER.value
IA = AppRole.INTERNAL_AUDITOR.value
EX = AppRole.EXECUTIVE.value
SA = AppRole.SYSTEM_ADMINISTRATOR.value

# urutan kolom tabel
ROLE_ORDER: tuple[str, ...] = (RA, CO, BCO, LR, CM, IA, EX, SA)

# kapabilitas → (RA, CO, BCO, LR, CM, IA, EX, SA)   — "" berarti tanda "—" pada tabel
_RAW: dict[str, tuple[str, ...]] = {
    # ---------------- Halaman 1 ----------------
    "source_registry":      ("CRU",  "R",     "",        "R",   "R",   "R", "",  "CRUD"),   # Registri Regulatory Source
    "ingestion":            ("CRUX", "R",     "",        "R",   "R",   "R", "",  "RX"),     # Ingestion dokumen (unggah/ambil URL)
    "document_version":     ("CR",   "R",     "",        "R",   "R",   "R", "R", "R"),      # Document Version (imutabel)
    "provision_correction": ("CRU",  "R",     "",        "R",   "R",   "R", "",  ""),       # Koreksi segmentasi Provision
    "relationship":         ("CRUD", "R",     "",        "RU",  "RA",  "R", "",  ""),       # Relasi regulasi
    "doc_status":           ("CRU",  "R",     "",        "R",   "RA",  "R", "",  ""),       # Perubahan status dokumen
    "taxonomy":             ("CRU",  "CRU",   "",        "R",   "R",   "R", "",  "CRUD"),   # Penetapan Taxonomy Label
    "corpus_search":        ("R",    "R",     "R",       "R",   "R",   "R", "R", "R"),      # Pencarian korpus
    "change_detection":     ("XR",   "R",     "",        "R",   "R",   "R", "",  "XR"),     # Eksekusi deteksi perubahan
    # ---------------- Halaman 2 ----------------
    "change_review":        ("CRU",  "RU",    "",        "RU",  "RA",  "R", "",  ""),       # Tinjauan Change (terima/sunting/tolak)
    "org_profile":          ("R",    "CRU",   "R",       "R",   "RA",  "R", "R", "R"),      # Organization Profile
    "applicability":        ("R",    "CRU",   "",        "RU",  "A",   "R", "R", ""),       # Applicability Decision
    "obligation":           ("C/draft R", "CRU", "R/own", "RU", "A",   "R", "R", ""),       # Obligation (validasi rekaman terstruktur)
    "obligation_owner":     ("",     "CRU",   "R",       "",    "RA",  "R", "",  ""),       # Penetapan pemilik Obligation
    "risk":                 ("R",    "CRU",   "R",       "R",   "R",   "R", "R", ""),       # Registri risiko
    "control_library":      ("R",    "CRU",   "R/own",   "R",   "R",   "R", "R", ""),       # Pustaka kontrol
    "control_owner":        ("",     "CRU",   "R",       "",    "RA",  "R", "",  ""),       # Penetapan Control Owner
    "assessment_campaign":  ("",     "CRU",   "R",       "",    "RA",  "R", "",  ""),       # Kampanye asesmen
    "self_assessment":      ("",     "RU",    "CRU/own", "",    "R",   "R", "",  ""),       # Respons self-assessment kontrol
    # ---------------- Halaman 3 ----------------
    "assessment_conclusion": ("",    "CRU",   "",        "R",   "A",   "R", "R", ""),       # Kesimpulan / pengesahan asesmen
    "evidence_request":     ("",     "CRU",   "R",       "",    "R",   "R", "",  ""),       # Permintaan bukti
    "evidence_upload":      ("",     "CR",    "CR/own",  "",    "R",   "R", "",  ""),       # Unggah bukti
    "evidence_access":      ("R",    "R",     "R/own",   "R",   "R",   "R", "",  ""),       # Akses bukti (isi berkas)
    "finding":              ("",     "CRU",   "R/own",   "",    "RA",  "R", "R", ""),       # Finding
    "remediation":          ("",     "CRU",   "RUX/own", "",    "RA",  "R", "R", ""),       # Tindakan remediasi
    "finding_closure":      ("",     "C/propose R", "",  "",    "A",   "R", "",  ""),       # Penutupan Finding
    "finding_reopen":       ("",     "CR",    "",        "",    "X",   "R", "",  ""),       # Membuka kembali Finding
    "copilot_query":        ("XR",   "XR",    "XR",      "XR",  "XR",  "XR", "XR", "XR"),   # Kueri copilot
    "copilot_promote":      ("CR",   "CR",    "",        "CR",  "R",   "",  "",  ""),       # Promosi keluaran copilot → rekaman
    "dashboard":            ("R",    "R",     "R/own",   "R",   "R",   "R", "R", "R"),      # Dasbor
    "report_draft":         ("",     "CRU",   "",        "R",   "R",   "R", "",  ""),       # Compliance Report — hasilkan draf
    # ---------------- Halaman 4 ----------------
    "report_issue":         ("",     "",      "",        "",    "A",   "R", "R", ""),       # Compliance Report — terbitkan
    "report_published":     ("R",    "R",     "R",       "R",   "R",   "R", "R", "R"),      # Laporan yang telah diterbitkan
    "audit_trail":          ("R/own", "R/own", "",       "R",   "R",   "R", "",  "R/system"),  # Jejak audit
    "user_admin":           ("",     "",      "",        "",    "",    "R", "",  "CRUD"),   # Administrasi pengguna dan peran
    "system_config":        ("",     "",      "",        "",    "",    "R", "",  "CRUDX"),  # Konfigurasi sistem / job
}

LABEL_ID: dict[str, str] = {
    "source_registry": "Registri Regulatory Source", "ingestion": "Ingestion dokumen",
    "document_version": "Document Version", "provision_correction": "Koreksi segmentasi Provision",
    "relationship": "Relasi regulasi", "doc_status": "Perubahan status dokumen", "taxonomy": "Penetapan Taxonomy Label",
    "corpus_search": "Pencarian korpus", "change_detection": "Eksekusi deteksi perubahan",
    "change_review": "Tinjauan Change", "org_profile": "Organization Profile", "applicability": "Applicability Decision",
    "obligation": "Obligation", "obligation_owner": "Penetapan pemilik Obligation", "risk": "Registri risiko",
    "control_library": "Pustaka kontrol", "control_owner": "Penetapan Control Owner",
    "assessment_campaign": "Kampanye asesmen", "self_assessment": "Respons self-assessment kontrol",
    "assessment_conclusion": "Kesimpulan/pengesahan asesmen", "evidence_request": "Permintaan bukti",
    "evidence_upload": "Unggah bukti", "evidence_access": "Akses bukti", "finding": "Finding",
    "remediation": "Tindakan remediasi", "finding_closure": "Penutupan Finding",
    "finding_reopen": "Membuka kembali Finding", "copilot_query": "Kueri copilot",
    "copilot_promote": "Promosi keluaran copilot", "dashboard": "Dasbor", "report_draft": "Compliance Report (draf)",
    "report_issue": "Compliance Report (terbitkan)", "report_published": "Laporan yang telah diterbitkan",
    "audit_trail": "Jejak audit", "user_admin": "Administrasi pengguna dan peran", "system_config": "Konfigurasi sistem/job",
}

VALID_LETTERS = set("CRUDAX")
VALID_SCOPES = {"own", "draft", "propose", "system"}


def _parse_cell(cell: str) -> dict[str, Optional[str]]:
    """'C/draft R' → {'C': 'draft', 'R': None}; 'R/own' → {'R': 'own'}; 'CRU/own' → {'C': 'own', 'R': 'own', 'U': 'own'}.

    Penanda lingkup menempel pada kelompok huruf tepat di depannya (dipisah spasi)."""
    out: dict[str, Optional[str]] = {}
    for group in cell.split():
        letters, _, scope = group.partition("/")
        assert set(letters) <= VALID_LETTERS, f"huruf tidak dikenal pada sel {cell!r}"
        assert not scope or scope in VALID_SCOPES, f"lingkup tidak dikenal pada sel {cell!r}"
        for ch in letters:
            out[ch] = scope or None
    return out


MATRIX: dict[str, dict[str, dict[str, Optional[str]]]] = {}
for _cap, _cells in _RAW.items():
    assert len(_cells) == len(ROLE_ORDER), f"{_cap}: jumlah kolom harus {len(ROLE_ORDER)}"
    MATRIX[_cap] = {role: _parse_cell(cell) for role, cell in zip(ROLE_ORDER, _cells)}


def _grant(role: str, capability: str, action: str) -> Optional[tuple[bool, Optional[str]]]:
    """(diizinkan?, lingkup). 'A' mencakup 'R'."""
    cell = MATRIX[capability][role]          # KeyError = typo nama kapabilitas → sengaja keras
    if action in cell:
        return True, cell[action]
    if action == "R" and "A" in cell:
        return True, cell["A"]
    return None


def allows(role: str, capability: str, action: str) -> bool:
    """Apakah `role` boleh melakukan `action` (C/R/U/D/A/X) pada `capability`?"""
    return _grant(role, capability, action) is not None


def scope_of(role: str, capability: str, action: str) -> Optional[str]:
    """Lingkup pembatas untuk aksi tsb: 'own' | 'draft' | 'propose' | 'system' | None (tanpa batas)."""
    g = _grant(role, capability, action)
    return g[1] if g else None


def roles_allowed(capability: str, action: str) -> list[str]:
    return [r for r in ROLE_ORDER if allows(r, capability, action)]


def can_read_any(role: str, *capabilities: str) -> bool:
    return any(allows(role, c, "R") for c in capabilities)


def for_role(role: str) -> dict[str, dict[str, Optional[str]]]:
    """Izin satu peran, {kapabilitas: {huruf: lingkup}} — hanya kapabilitas yang punya minimal satu huruf."""
    return {cap: dict(cells[role]) for cap, cells in MATRIX.items() if cells[role]}