# Security & Privacy Checklist RCIP

✅ = diterapkan & diuji · 🟡 = sebagian · ⬜ = belum (perlu sebelum produksi). Bukti merujuk ke kode/test.

## Autentikasi & sesi
| | Kontrol | Bukti |
|---|---|---|
| ✅ | Password di-hash PBKDF2-SHA256 120.000 iterasi + salt acak | `app/platform/auth.py` |
| ✅ | JWT bertanda tangan HS256 dengan masa berlaku (default 8 jam) | `create_token` |
| ✅ | Aplikasi menolak start di production dengan JWT secret bawaan/lemah | `Settings.assert_safe_for_environment` |
| ✅ | Pembatasan laju login gagal per akun+IP (default 5/menit, dapat disetel) + audit `LOGIN_FAILED` | `test_login_rate_limit_correlation_id_and_error_envelope` |
| ⬜ | MFA, refresh token, pencabutan token, kebijakan kompleksitas password | roadmap |

## Otorisasi
| | Kontrol | Bukti |
|---|---|---|
| ✅ | RBAC ditegakkan di server pada setiap endpoint (UI hanya cermin) | `require_roles`, `test_rbac_server_side` |
| ✅ | Auditor & Admin tanpa kapabilitas approve/create domain (R-01, R-02) | `test_sod_negative.py` |
| ✅ | Pemisahan tugas pada 6 titik kendali di aplikasi + CHECK DB | `test_sod_negative.py` (16 percobaan) |
| ✅ | Lingkup Pemilik Bisnis/Kontrol hanya objek miliknya (R-05) | `test_owner_scope_hides_foreign_findings` |
| ✅ | Jejak audit dibatasi per peran (Analis/Pejabat hanya event sendiri) | `test_audit_scope_and_export` |

## Integritas & audit
| | Kontrol | Bukti |
|---|---|---|
| ✅ | Audit & approval append-only (trigger DB) | `test_audit_is_append_only` |
| ✅ | Versi terbit, bukti ACCEPTED, laporan ISSUED imutabel (trigger) | `test_published_version_is_immutable`, `test_accepted_evidence_is_immutable_in_db`, `test_report_maker_checker_and_immutability` |
| ✅ | Setiap transisi diaudit dengan aktor, waktu, sebelum/sesudah, correlation ID | `governance.audit`, `RequestContextMiddleware` |
| ✅ | Checksum SHA-256 setiap bukti/dokumen | `store_evidence` |
| ✅ | Validator invarian data | `python -m seed.validate` |

## Input & berkas
| | Kontrol | Bukti |
|---|---|---|
| ✅ | Validasi skema request (Pydantic) dengan error yang menyebut field | `VALIDATION_ERROR` + `offending` |
| ✅ | Query SQL berparameter (SQLAlchemy / `text()` dengan bind) | seluruh `app/` |
| ✅ | Diff HTML di-escape di server (hanya `<ins>/<del>`) | `diff_engine.py` |
| ✅ | Unggahan: blok ekstensi executable, tanda tangan MZ/ELF/shebang, EICAR; batas ukuran | `app/shared/filescan.py`, `test_upload_scan_rejects_malware_and_executables` |
| ✅ | Path penyimpanan lokal dicegah keluar folder (path traversal) | `storage._local_path` |
| 🟡 | Antivirus penuh | ⬜ pasang ClamAV di produksi |

## Transport & header
| | Kontrol | Bukti |
|---|---|---|
| ✅ | Header `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Cache-Control: no-store` | `SECURITY_HEADERS` |
| ✅ | CORS dibatasi ke origin frontend | `app/main.py` |
| 🟡 | HTTPS — wajib di reverse proxy saat deployment bersama | `deployment_guide.md` §6 |

## Data & privasi
| | Kontrol | Bukti |
|---|---|---|
| ✅ | Seluruh data organisasi, pengguna, bukti, dan korpus demo sintetis (A-01, A-06) | `docs/synthetic_data.md` |
| ✅ | Hanya teks peraturan publik yang dapat dikirim ke LLM; bukti/temuan/profil tidak pernah | `docs/ai_model.md` §6 |
| ✅ | Penafian berversi di laporan & copilot; label data sintetis di UI | §13.6 |
| ✅ | Tidak ada kunci konfigurasi untuk mematikan audit/SoD/label AI | `test_runtime_config_is_admin_only_bounded_and_audited` |
| ✅ | `.env` tidak ikut repo (`.gitignore`); `.env.example` hanya nilai palsu | repo |
| ⬜ | Enkripsi berkas bukti at-rest, kebijakan retensi & penghapusan terjadwal | roadmap |
| ⬜ | DPIA bila data nyata/pribadi akan diproses | sebelum pilot |

## Operasional
| | Kontrol | Bukti |
|---|---|---|
| ✅ | Error 500 tidak membocorkan stack trace; dicatat dengan correlation ID | `register_error_handlers` |
| ✅ | Metrik layanan (Admin/Auditor) | `GET /api/v1/metrics` |
| ✅ | Backup/restore terdokumentasi | `deployment_guide.md` §5 |
| ✅ | CI menjalankan migrasi, seed, validator, seluruh test, dan build frontend | `.github/workflows/ci.yml` |
| ⬜ | Pemindaian dependensi (pip-audit / npm audit) dan lisensi open source di CI | roadmap |

## Isu kritis terbuka

Tidak ada isu keamanan kritis yang diketahui untuk lingkungan demo dengan data sintetis. Butir ⬜ wajib ditangani sebelum dipakai dengan data nyata.
