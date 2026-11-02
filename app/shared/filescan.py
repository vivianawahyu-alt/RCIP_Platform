"""Pemeriksaan keamanan berkas unggahan (FR-EVR-002 (a), E11.2).

MVP: pemeriksaan statis tanpa antivirus eksternal — ekstensi berbahaya, tanda tangan biner executable,
dan string uji EICAR ditolak (SCAN_FAILED) dan tidak pernah ditulis ke penyimpanan.
Produksi: ganti/lengkapi dengan ClamAV (lihat docs/security_privacy_checklist.md)."""
from app.shared.errors import AppError

BLOCKED_EXT = {".exe", ".dll", ".bat", ".cmd", ".com", ".msi", ".ps1", ".sh", ".js", ".vbs", ".jar", ".scr", ".apk"}
SIGNATURES = {b"MZ": "Windows executable", b"\x7fELF": "ELF executable", b"#!": "skrip shell"}
EICAR = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"


def scan_upload(filename: str, data: bytes) -> None:
    name = filename.lower()
    ext = name[name.rfind("."):] if "." in name else ""
    if ext in BLOCKED_EXT:
        raise AppError(422, "SCAN_FAILED", f"Jenis berkas {ext} tidak diizinkan sebagai bukti")
    for sig, label in SIGNATURES.items():
        if data.startswith(sig):
            raise AppError(422, "SCAN_FAILED", f"Berkas dikarantina: terdeteksi {label}")
    if EICAR in data[:4096]:
        raise AppError(422, "SCAN_FAILED", "Berkas dikarantina: terdeteksi tanda uji malware (EICAR)")
