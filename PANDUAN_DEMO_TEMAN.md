# Panduan Menjalankan Demo RCIP (untuk anggota tim yang sudah punya folder lama)

Dijalankan di Windows dengan **Git Bash** + **Docker Desktop** + **Node.js 18+**.
Folder lama **tidak dihapus dan datanya tidak hilang**; demo memakai database baru yang terpisah.

---

## 0. Persiapan sekali saja

1. Buka **Docker Desktop**, tunggu sampai di pojok kiri bawah tertulis **Engine running**.
2. Ekstrak ZIP ke `D:\CapStone\` lalu **beri nama folder `rcip_final`**
   (sengaja berbeda dari folder lama `rcip_new`, supaya database demo terpisah dari data lama).

```
D:\CapStone\
├── rcip_new\      ← folder lama (biarkan)
└── rcip_final\    ← folder baru dari ZIP
```

> Nama folder menentukan nama database di Docker. Kalau folder baru juga dinamai `rcip_new`,
> data lama akan terpakai dan dataset demo tidak bisa dibuat.

---

## 1. Matikan container versi lama (data tetap aman)

Buka Git Bash:

```bash
cd /d/CapStone/rcip_new
docker compose down
```

**Jangan** pakai `docker compose down -v` (opsi `-v` menghapus database).

---

## 2. Siapkan folder baru

```bash
cd /d/CapStone/rcip_final
cp .env.example .env
```

Jika folder lama punya `.env` dengan isi khusus (misalnya API key), salin itu saja:
`cp ../rcip_new/.env .env`. Jika nama folder memakai tanda kurung, beri tanda kutip:
`cp "../nama (lama)/.env" .env`.

---

## 3. Nyalakan backend dan buat database demo

```bash
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python -m seed.generate --seed 42
docker compose exec api python -m seed.validate
```

- `up --build` pertama kali memakan beberapa menit.
- `seed.generate` membuat 30 dokumen regulasi, kewajiban, kontrol, temuan, dan laporan untuk demo.
- `seed.validate` harus berakhir dengan semua invarian **terpenuhi**.
- Jika muncul error `the input device is not a TTY`, tambahkan `-T`, contoh:
  `docker compose exec -T api python -m seed.validate`.

Cek status: `docker compose ps` → `api`, `worker`, `postgres`, `redis` harus **Up/running**.
API dapat dicek di http://localhost:8000/docs

---

## 4. Nyalakan frontend (Git Bash kedua)

```bash
cd /d/CapStone/rcip_final/web
npm install
npm run dev
```

Buka **http://localhost:5173**. Biarkan jendela ini tetap terbuka selama demo.

---

## 5. Akun demo

Semua password: **`demo1234`**

| Akun | Peran |
|---|---|
| `executive` | Eksekutif (Beranda) |
| `analyst` | Analis regulasi |
| `officer`, `officer2` | Pejabat kepatuhan (pembuat) |
| `manager`, `manager2` | Manajer kepatuhan (penyetuju) |
| `owner`, `owner_it`, `owner_ops`, `owner_fin` | Pemilik kontrol |
| `legal` | Konsultan hukum |
| `auditor` | Auditor (hanya baca) |
| `admin` | Administrator |

Tips: buka dua jendela browser (satu biasa, satu Incognito) agar bisa login sebagai pembuat dan penyetuju sekaligus.

---

## 6. Alur demo (±20 menit)

Ikuti `docs/demo_scenario.md` (17 langkah). Ringkasnya:

1. `executive` — Beranda: postur kepatuhan, kesenjangan, tenggat.
2. `analyst` — Pusat Regulasi → Korpus: 30 dokumen, label, relasi pencabutan.
3. `analyst` → `manager` — Perubahan SEOJK S-29/2022 v1→v2: diff per kata, validasi lalu konfirmasi materialitas (**titik kendali 1**).
4. `officer` → `manager` — Keberlakuan PBI S-22/2020: saran + kode alasan, lalu setujui (**titik kendali 2**). Coba setujui milik sendiri → ditolak.
5. `officer` → `manager` — Ekstrak kewajiban, buka "Mengapa AI mengusulkan ini?", lalu setujui (**titik kendali 3**).
6. `owner` → `officer` → `manager` — Unggah bukti, terima bukti, asesmen, sign-off (**titik kendali 4**).
7. `owner` → `manager` — Remediasi temuan dan penutupan (**titik kendali 5**).
8. `officer` → `manager` — Susun dan terbitkan laporan (**titik kendali 6**).
9. `auditor` — Jejak audit: filter, sebelum/sesudah, ekspor CSV.
10. Tanya regulasi: pertanyaan bersumber vs "tarif pajak penghasilan" → ditolak karena di luar korpus.
11. `admin` — Administrasi: ubah parameter dengan justifikasi → tercatat di audit.

Bukti tambahan (opsional): `docker compose exec api pytest -q` → **39 passed**.

---

## 7. Selesai demo / kembali ke versi lama

```bash
# Ctrl+C di jendela frontend, lalu:
cd /d/CapStone/rcip_final
docker compose down          # tanpa -v
```

Untuk kembali ke versi lama: `cd /d/CapStone/rcip_new && docker compose up -d`.
Hanya satu versi yang boleh menyala dalam satu waktu (port 5432/6379/8000 sama).

Untuk mengulang dataset demo dari awal (menghapus data **folder baru saja**):

```bash
cd /d/CapStone/rcip_final
docker compose down -v
docker compose up -d
docker compose exec api alembic upgrade head
docker compose exec api python -m seed.generate --seed 42
```

---

## 8. Masalah umum

| Gejala | Solusi |
|---|---|
| `port is already allocated` | Versi lama masih menyala → langkah 1 |
| `Container name "/rcip_postgres" is already in use` | `docker rm rcip_postgres` (container lama yang sudah berhenti), lalu ulangi langkah 3 |
| `Korpus tidak kosong` saat `seed.generate` | Database bukan baru → pastikan nama folder `rcip_final`, atau jalankan reset di langkah 7 |
| `vite: Permission denied` / error esbuild | Hapus folder `web/node_modules`, lalu `npm install` lagi |
| `relation ... does not exist` | Belum migrasi → `docker compose exec api alembic upgrade head` |
| Login `429 TOO_MANY_ATTEMPTS` | Terlalu banyak salah password, tunggu 1 menit |
| `docker: command not found` / tidak bisa connect | Docker Desktop belum menyala |
