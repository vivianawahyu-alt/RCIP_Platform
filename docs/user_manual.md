# Panduan Pengguna RCIP

RCIP membantu organisasi membuktikan kepatuhan: setiap kewajiban dapat ditelusuri dari pasal regulasi sampai bukti pelaksanaan dan laporannya. Panduan ini disusun per peran.

## Masuk & navigasi

Buka `http://localhost:5173`, pilih persona demo (password `demo1234`). Bagian atas layar:
- **Strip atas** — organisasi, tanggal, akun dan perannya, tombol Keluar.
- **Menu** — *Pusat Regulasi* (korpus, perubahan, tanya regulasi), *Kepatuhan* (keberlakuan, kewajiban, risiko & kontrol, asesmen), *Temuan & Remediasi*, *Laporan & Audit* (laporan, jejak audit, administrasi).
- **Pencarian** — ketik kata kunci, pilih kategori (Semua/Peraturan/Kewajiban/Temuan).
- **Sitasi** (kotak emas bertanda §) — klik untuk membaca teks pasal pada versi yang tepat.

Aturan umum: tombol yang tidak sesuai peran Anda tidak ditampilkan, dan server tetap menolak aksi tersebut. Setiap keputusan bertingkat (6 titik kendali) tidak dapat disetujui oleh orang yang membuatnya.

## Analis Regulasi (`analyst`)

1. **Korpus & pasal** — daftarkan dokumen, unggah versi (.pdf/.txt), periksa hasil segmentasi pasal, lalu **Publikasikan** (versi terbit tidak dapat diubah).
2. **Klasifikasi & silsilah** (panel kanan Korpus) — konfirmasi atau hapus label saran aturan; usulkan relasi *mengubah/mencabut/menggantikan* dengan memilih pasal penetap. Bila Peninjau Hukum meminta revisi (status *Analis sedang melakukan revisi*), perbaiki jenis relasi atau pasal penetap lalu klik **Ajukan ulang**. Analis tidak dapat menyetujui relasinya sendiri.
3. **Perubahan regulasi** — klik *Bandingkan* untuk dokumen dengan dua versi terbit. Untuk tiap perubahan: pilih materialitas dan jenis, tulis alasan, **Simpan validasi**. Bila ragu secara hukum, **Eskalasi** ke Peninjau Hukum. Indikasi material dari sistem hanyalah petunjuk.

## Pejabat Kepatuhan (`officer`)

1. **Keberlakuan** — *Susun keputusan*: pilih peraturan, baca saran aturan (beserta kode alasannya), pilih keputusan, tulis alasan, centang pasal yang disitasi (dan pasal yang berlaku bila *Berlaku sebagian*), **Ajukan ke Manajer**. Perbarui profil organisasi bila izin berubah — keputusan terkait otomatis ditandai *Perlu ditinjau ulang*.
2. **Ekstrak kewajiban** — di Korpus, klik *Ekstrak kewajiban* pada pasal versi terbit yang keputusan keberlakuannya disetujui.
3. **Kewajiban** — buka *Mengapa AI mengusulkan ini?* untuk melihat frasa yang dipakai AI. Perbaiki ringkasan, pilih pemilik, centang konfirmasi tinjauan manual bila keyakinan rendah, **Validasi & ajukan persetujuan**. Kewajiban *Perlu ditinjau* (pasal sumber berubah) dibuka kembali dan dapat diarahkan ke pasal versi terbaru.
4. **Risiko & kontrol** — tambah risiko dan kontrol, tetapkan pemilik, petakan ke kewajiban aktif. Tinjau bukti (Terima/Tolak + rasional). Catat kesimpulan **desain** dan **operasional** beserta rasional, lalu **Ajukan sign-off**. Hasil sebagian/tidak efektif otomatis membuat temuan.
5. **Temuan & Remediasi** — *Pindai kesenjangan* untuk kewajiban tanpa kontrol; *Catat temuan* manual; tambah tindakan remediasi (tenggat dibatasi jendela tingkat keparahan); terima bukti penutupan.
6. **Laporan** — *Bangkitkan draf*, periksa 10 bagian, **Ajukan penerbitan**.

## Pemilik Bisnis/Kontrol (`owner`, `owner_it`, …)

Hanya melihat temuan, tindakan, dan bukti milik sendiri.
1. **Risiko & kontrol** — unggah bukti untuk kontrol yang Anda miliki.
2. **Temuan** — pada tindakan Anda: *Mulai kerjakan*, unggah bukti penutupan, tunggu bukti diterima Pejabat, *Tandai selesai*; bila perlu *Perpanjang jatuh tempo* (alasan wajib, tanggal asli tetap tercatat). Setelah semua tindakan selesai: **Ajukan penutupan**.

## Peninjau Hukum (`legal`)

Peninjau Hukum memberi pendapat hukum, bukan keputusan. Peran ini tidak menilai materialitas, tidak memvalidasi kewajiban, dan tidak mengubah relasi (hak relasi: hanya baca).

1. **Antrian hukum** (halaman awal setelah login) — semua eskalasi yang menunggu posisi hukum dari Perubahan regulasi, Keberlakuan, dan Kewajiban, ditambah relasi yang menunggu persetujuan Manajer. Klik **Buka** untuk menuju halamannya.
2. **Jawab eskalasi** (status *Menunggu Peninjau Hukum*): tulis posisi hukum lalu pilih minimal satu pasal yang disitasi. Tanpa sitasi, jawaban ditolak. Setelah dikirim, objek kembali ke pembuatnya (Analis atau Pejabat Kepatuhan) untuk dilanjutkan.
3. **Relasi dokumen** — dari Antrian hukum atau panel Relasi dokumen: pilih **Simpan catatan** (Manajer tetap dapat memutuskan) atau **Minta revisi** (catatan wajib; Manajer harus menunggu sampai Analis mengajukan ulang).
4. Posisi hukum disimpan berversi (v1, v2, …) di tabel `compliance.legal_position` beserta versi pasal yang disitasi; nomor versinya tampil di samping tulisan *Posisi hukum*. Jawaban baru untuk objek yang sama menjadi versi berikutnya tanpa menghapus versi lama.
5. Dapat membaca jejak audit.

## Manajer Kepatuhan (`manager`, `manager2`)

Pemberi persetujuan di enam titik kendali:

| # | Titik kendali | Halaman |
|---|---|---|
| 1 | Konfirmasi materialitas perubahan | Perubahan regulasi → *Konfirmasi material* |
| 2 | Keputusan keberlakuan | Keberlakuan → *Setujui* |
| 3 | Validasi kewajiban | Kewajiban → *Setujui* |
| 4 | Sign-off asesmen | Asesmen & sign-off → *Beri sign-off* |
| 5 | Penutupan temuan | Temuan → *Tutup temuan* / *Tolak penutupan* / *Terima risiko* / *Buka kembali* |
| 6 | Penerbitan laporan | Laporan → *Terbitkan* / *Tarik laporan* |

Selain enam titik kendali di atas, Manajer memutuskan **relasi dokumen** (Korpus atau Perubahan regulasi → panel Relasi dokumen): **Setujui** mengubah status dokumen target secara otomatis (mis. *Diubah*/*Dicabut*/*Dicabut sebagian*/*Digantikan*), **Tolak** wajib alasan dan tidak mengubah status. Selama status *Analis sedang melakukan revisi*, persetujuan belum dapat diberikan.

Pengembalian/penolakan selalu wajib alasan. Bila Anda pemilik tindakan atau pembuat objek, sistem menolak (gunakan `manager2`).

## Auditor Internal (`auditor`)

Hanya-baca di seluruh aplikasi. **Jejak audit**: saring per jenis objek, aksi, atau aktor; klik baris untuk melihat status sebelum/sesudah; **Ekspor CSV**. Detail temuan menampilkan timeline audit dan keputusan maker-checker. Laporan lama tetap dapat dibuka (terbit = beku).

## Eksekutif (`executive`)

**Beranda**: postur kepatuhan sebagai kalimat (pembilang/penyebut), cakupan kontrol, temuan per tingkat, tenggat 30 hari, antrean tata kelola. Klik angka untuk menelusuri ke daftar di baliknya.

## Administrator Sistem (`admin`)

**Administrasi**: ubah parameter runtime (wajib justifikasi; tercatat di audit), lihat pengguna & peran, metrik layanan. Administrator tidak dapat membuat atau menyetujui rekaman kepatuhan.

## Tanya regulasi (semua peran)

Ajukan pertanyaan; jawaban berupa kutipan pasal bersitasi. Bila korpus tidak memuat dasar yang cukup, jawabannya *INSUFFICIENT_BASIS*. Copilot bukan nasihat hukum.

## Istilah status

| Status | Arti |
|---|---|
| Draf AI | hasil mesin, belum divalidasi; tidak dihitung di mana pun |
| Menunggu persetujuan | diajukan ke Manajer |
| Aktif / Disetujui / Terbit | catatan resmi |
| Perlu ditinjau | sumbernya berubah material atau profil berubah |
| Risiko diterima | kesenjangan yang diterima, bukan diselesaikan |
| Digantikan | ada versi/keputusan/laporan yang lebih baru; tetap dapat dibaca |
| Menunggu Peninjau Hukum | dieskalasi ke Peninjau Hukum; belum dapat diajukan atau dipetakan |
| Analis sedang melakukan revisi | relasi diminta direvisi oleh Peninjau Hukum; Manajer menunggu |
