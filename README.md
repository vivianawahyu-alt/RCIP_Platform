# RCIP — Regulatory & Compliance Intelligence Platform

Capstone 01 V-TEKI × UKDW. Aplikasi web yang menjaga rantai bukti kepatuhan sebagai relasi basis data:
**pasal pada versi tertentu → keberlakuan → kewajiban → risiko/kontrol → bukti → asesmen → temuan → remediasi → persetujuan → laporan → audit.**
AI hanya menyusun draf; enam titik kendali maker-checker ditegakkan di aplikasi dan di database.

Stack: FastAPI + PostgreSQL 16 (3 skema, trigger imutabilitas, CHECK SoD) · Celery/Redis · React 18 + TypeScript.

## Mulai cepat (instalasi baru)
```bash
cp .env.example .env
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python -m seed.run          # data minimal; ATAU di DB kosong: python -m seed.generate --seed 42
docker compose exec api pytest -q                    # 39 test
cd web && npm install && npm run dev                 # http://localhost:5173 · API http://localhost:8000/docs
```
Login: `analyst` · `officer` · `owner` · `legal` · `manager` · `auditor` · `executive` · `admin` — password `demo1234`.

## Memperbarui instalasi yang sudah berjalan (data dipertahankan)
```bash
cd /d/CapStone/rcip_new
docker exec rcip_postgres pg_dump -U rcip -d rcip_db > rcip_backup.sql   # cadangan dulu
docker compose up -d --build
docker compose exec api alembic upgrade head        # menerapkan migrasi 002 & 003
docker compose restart api worker
docker compose exec api python -m seed.validate     # cek invarian data lama
cd web && npm install && npm run dev
```
Jangan jalankan `docker compose down -v` (menghapus database). Bila `npm run dev` gagal karena izin/esbuild, hapus `web/node_modules` lalu `npm install`.
Dataset demo lengkap sebaiknya dibuat di database terpisah — lihat [docs/synthetic_data.md](docs/synthetic_data.md).

## Dokumentasi (deliverable proposal hal. 22)
| Dokumen | Isi |
|---|---|
| [docs/handover.md](docs/handover.md) | Serah terima: status deliverable, baseline, ukuran keberhasilan SM-01…14, hasil test |
| [docs/architecture.md](docs/architecture.md) | Diagram arsitektur C4 + sekuens, pagar pengaman DB, ADR |
| [docs/erd.md](docs/erd.md) · [docs/data_dictionary.md](docs/data_dictionary.md) | Skema basis data (dibangkitkan dari DB) |
| [docs/api.md](docs/api.md) · [docs/openapi.json](docs/openapi.json) | Dokumentasi API (dibangkitkan dari kode) |
| [docs/ai_model.md](docs/ai_model.md) | Komponen AI, gerbang validasi, explainability |
| [docs/ai_evaluation_report.md](docs/ai_evaluation_report.md) | Evaluasi AI terhadap target (dibangkitkan) |
| [docs/synthetic_data.md](docs/synthetic_data.md) | Generator data sintetis reproducible + kunci jawaban |
| [docs/deployment_guide.md](docs/deployment_guide.md) | Instalasi, upgrade, konfigurasi, operasional, troubleshooting |
| [docs/user_manual.md](docs/user_manual.md) | Panduan per peran |
| [docs/demo_scenario.md](docs/demo_scenario.md) | Skenario demonstrasi akhir 17 langkah |
| [docs/risk_register.md](docs/risk_register.md) | Register risiko |
| [docs/security_privacy_checklist.md](docs/security_privacy_checklist.md) | Checklist keamanan & privasi |
| [docs/known_limitations_roadmap.md](docs/known_limitations_roadmap.md) | Keterbatasan & peta jalan |

## Perintah berguna
| Perintah | Fungsi |
|---|---|
| `python -m seed.generate --seed 42 [--anchor YYYY-MM-DD]` | Dataset demo 30 dokumen, semua status (DB kosong) |
| `python -m seed.validate` | Periksa 15 invarian integritas data |
| `python -m app.ai.evaluate` | Evaluasi AI → `docs/ai_evaluation_report.md` |
| `python -m seed.data_dictionary` | Bangkitkan data dictionary + ERD |
| `python -m app.api_docs` | Bangkitkan dokumentasi API |
| `make backup` | Cadangkan database |

## Peta implementasi
| Alur FRD | Endpoint / kode | UI |
|---|---|---|
| W2–W3 ingest, segmentasi, publikasi | `corpus/router.py`, `segmenter.py` | Pusat Regulasi → Korpus |
| W4 relasi · W6 taksonomi | `corpus/review.py` | Korpus → Klasifikasi & silsilah |
| W5 reviu perubahan (titik 1) | `corpus/review.py`, `diff_engine.py` | Pusat Regulasi → Perubahan |
| W7 keberlakuan (titik 2) | `compliance/applicability.py` | Kepatuhan → Keberlakuan |
| W8 kewajiban (titik 3) | `compliance/router.py`, `ai/gateway.py` | Kepatuhan → Kewajiban |
| W9 risiko & kontrol · W10 asesmen (titik 4) | `compliance/router.py` | Risiko & kontrol · Asesmen & sign-off |
| W11 bukti · W12 temuan & remediasi (titik 5) | `compliance/findings.py` | Temuan & Remediasi |
| W14 laporan (titik 6) · dasbor | `compliance/reporting.py` | Laporan · Beranda |
| W15 copilot | `copilot/services.py` | Pusat Regulasi → Tanya regulasi |
| FR-GOV audit · konfigurasi · metrik | `platform/router.py`, `shared/observability.py` | Laporan & Audit → Jejak audit · Administrasi |

Riwayat perubahan: [CHANGELOG_TAHAP2.md](CHANGELOG_TAHAP2.md), [CHANGELOG_TAHAP3.md](CHANGELOG_TAHAP3.md).
