# Panduan Deployment RCIP

Target: satu server lokal/universitas + satu lingkungan demo (asumsi A-07). Diuji dengan Docker Desktop (Windows + Git Bash) dan Linux.

## 1. Prasyarat

| Komponen | Versi |
|---|---|
| Docker Desktop / Docker Engine + Compose v2 | terbaru |
| Node.js | 18+ (disarankan 20) untuk frontend |
| Git Bash (Windows) | untuk perintah di bawah; `make` opsional |
| Port bebas | 5432 (PostgreSQL), 6379 (Redis), 8000 (API), 5173 (frontend dev) |

## 2. Instalasi baru

```bash
cd /d/CapStone/rcip_new           # folder hasil ekstrak
cp .env.example .env              # isi JWT_SECRET_KEY acak ≥ 32 karakter untuk server bersama
docker compose up -d --build
docker compose exec api alembic upgrade head      # migrasi 001 → 003
```

Pilih salah satu jenis data:

```bash
# a) data minimal (8 akun + 1 dokumen) — untuk mencoba alur dari nol
docker compose exec api python -m seed.run
# b) dataset demo lengkap (30 dokumen, semua status) — HANYA di DB kosong, jangan setelah (a)
docker compose exec api python -m seed.generate --seed 42
docker compose exec api python -m seed.validate
```

Frontend:

```bash
cd web && npm install && npm run dev      # http://localhost:5173  (API: http://localhost:8000/docs)
```

## 3. Memperbarui instalasi yang sudah berjalan (data dipertahankan)

```bash
make backup   # atau: docker exec rcip_postgres pg_dump -U rcip -d rcip_db > rcip_backup.sql
# ganti kode dengan versi baru, pertahankan .env Anda
docker compose up -d --build              # --build karena requirements/Dockerfile dapat berubah
docker compose exec api alembic upgrade head
docker compose restart api worker
docker compose exec api python -m seed.validate     # cek invarian data lama
cd web && npm install && npm run dev
```

Catatan upgrade ke versi ini:
- Keputusan keberlakuan lama otomatis dianggap **APPROVED** (warisan) agar kewajiban yang ada tetap tertelusur.
- Asesmen lama berstatus CONCLUDED dan buktinya SUBMITTED: terima bukti lalu ulangi asesmen + sign-off agar dihitung skor (validator menampilkannya sebagai peringatan).
- Ekstraksi baru kini mewajibkan keputusan keberlakuan yang disetujui (halaman Kepatuhan → Keberlakuan).
- **Jangan** menjalankan `docker compose down -v` kecuali sengaja menghapus database.

## 4. Konfigurasi

| Variabel `.env` | Fungsi |
|---|---|
| `DATABASE_URL` | koneksi PostgreSQL (`postgres:5432` di dalam Docker) |
| `REDIS_URL` | broker Celery |
| `JWT_SECRET_KEY` | wajib acak ≥ 32 karakter; aplikasi **menolak start** bila `ENVIRONMENT=production` dan secret bawaan |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | masa berlaku sesi (default 480) |
| `OPENAI_API_KEY`, `LLM_MODEL_NAME` | kosong = ekstraktor aturan; terisi = LLM via AI Gateway |
| `MINIO_*` | penyimpanan objek; bila MinIO tidak dijalankan, berkas disimpan di folder `./storage` |

Parameter runtime (jendela remediasi, ambang keyakinan AI, SLA reviu, ukuran bukti, batas login gagal) diubah lewat **Laporan & Audit → Administrasi** oleh `admin`, teraudit, dan dibatasi min/maks.

## 5. Operasional

| Kebutuhan | Perintah |
|---|---|
| Log API & worker | `docker compose logs -f api worker` (log permintaan JSON berisi `correlation_id`) |
| Kesehatan | `curl http://localhost:8000/health` |
| Metrik | `GET /api/v1/metrics` (login admin/auditor) atau halaman Administrasi |
| Backup | `make backup` → berkas `.sql`; juga salin folder `storage/` (berkas bukti) |
| Restore | DB kosong → `docker exec -i rcip_postgres psql -U rcip -d rcip_db < backup.sql` |
| Test | `docker compose exec api pytest -q` (35+ test, termasuk generator & evaluasi AI) |
| Evaluasi AI | `docker compose exec api python -m app.ai.evaluate` (perlu korpus sintetis) |
| Regenerasi dokumentasi | `python -m app.api_docs` · `python -m seed.data_dictionary` |

## 6. Build produksi frontend

```bash
cd web && npm ci && npm run build      # hasil statis di web/dist
```
Sajikan `web/dist` dengan Nginx/Caddy dan teruskan `/api` ke `api:8000` (contoh blok Nginx):
```nginx
location /api/ { proxy_pass http://api:8000; proxy_set_header X-Correlation-Id $request_id; }
location / { root /usr/share/nginx/html; try_files $uri /index.html; }
```
Gunakan HTTPS di server bersama, ubah `allow_origins` CORS di `app/main.py` sesuai domain, dan jalankan uvicorn tanpa `--reload` dengan beberapa worker (`--workers 2`).

## 7. Pemecahan masalah

| Gejala | Penyebab & solusi |
|---|---|
| `vite: Permission denied` / esbuild error | `node_modules` dari OS lain → hapus `web/node_modules`, `npm install` ulang |
| `relation ... does not exist` | migrasi belum dijalankan → `alembic upgrade head` |
| Ekstraksi `409 APPLICABILITY_NOT_APPROVED` | buat & setujui keputusan keberlakuan untuk versi tersebut |
| `seed.generate` "Korpus tidak kosong" | jalankan di DB terpisah (lihat docs/synthetic_data.md) |
| Port 5432 bentrok | hentikan PostgreSQL lokal atau ubah port di `docker-compose.yml` |
| `429 TOO_MANY_ATTEMPTS` saat login | tunggu 1 menit (batas dapat diubah di Administrasi) |
