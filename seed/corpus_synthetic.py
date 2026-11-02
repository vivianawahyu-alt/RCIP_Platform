"""Spesifikasi korpus SINTETIS untuk generator (bukan teks resmi). Nomor memakai awalan 'S-' agar tidak
tertukar dengan peraturan nyata. Setiap pasal adalah templat; versi berikutnya menimpa parameter
sehingga diff menghasilkan perubahan material (angka) maupun editorial.

kind: OBL = kewajiban (memuat 'wajib'), DEF = definisi, PROHIB = larangan ('dilarang'), PERM = kewenangan ('dapat').
"""

TOPICS = [
    {
        "key": "ti", "number": "POJK 11/POJK.03/2022", "instrument": "POJK", "source": "OJK",
        "title": "Penyelenggaraan Teknologi Informasi oleh Bank Umum",
        "decision": "APPLICABLE",
        "pasal": [
            ("1", "DEF", "Dalam Peraturan ini yang dimaksud dengan Bank adalah bank umum konvensional."),
            ("5", "OBL", "Bank wajib memiliki kebijakan keamanan siber yang disetujui direksi."),
            ("20", "OBL", "Bank wajib melakukan pengujian pemulihan bencana paling sedikit 1 (satu) kali dalam 1 (satu) tahun."),
            ("60", "OBL", "Bank wajib menyampaikan laporan insiden TI kepada Otoritas Jasa Keuangan paling lambat {jam} ({jam_w}) jam setelah insiden TI diketahui."),
        ],
        "versions": [{"date": -1480, "p": {"jam": 24, "jam_w": "dua puluh empat"}},
                     {"date": -299, "p": {"jam": 12, "jam_w": "dua belas"},
                      "add": {"61": "Bank wajib menyimpan bukti pelaporan insiden TI paling singkat 5 (lima) tahun."}}],
    },
    {
        "key": "apu", "number": "POJK S-08/2023", "instrument": "POJK", "source": "OJK",
        "title": "Penerapan Program Anti Pencucian Uang dan Pencegahan Pendanaan Terorisme di Sektor Lembaga Jasa Keuangan",
        "decision": "APPLICABLE",
        "pasal": [
            ("1", "DEF", "Dalam Peraturan ini yang dimaksud dengan Penyedia Jasa Keuangan adalah lembaga jasa keuangan yang diawasi Otoritas Jasa Keuangan."),
            ("4", "OBL", "Penyedia Jasa Keuangan wajib melakukan identifikasi dan verifikasi calon nasabah sebelum membangun hubungan usaha."),
            ("12", "OBL", "Penyedia Jasa Keuangan wajib menyampaikan laporan transaksi keuangan mencurigakan kepada PPATK paling lambat {ltkm} ({ltkm_w}) hari kerja setelah transaksi diketahui."),
            ("15", "OBL", "Penyedia Jasa Keuangan wajib melakukan pengkinian data nasabah berisiko tinggi paling sedikit {kyc} ({kyc_w}) kali dalam 1 (satu) tahun."),
            ("21", "PROHIB", "Penyedia Jasa Keuangan dilarang membuka rekening anonim atau rekening yang menggunakan nama fiktif."),
            ("30", "OBL", "Penyedia Jasa Keuangan wajib menatausahakan dokumen nasabah paling singkat 5 (lima) tahun sejak berakhirnya hubungan usaha."),
        ],
        "versions": [{"date": -720, "p": {"ltkm": 3, "ltkm_w": "tiga"}},
                     {"date": -150, "p": {"ltkm": 1, "ltkm_w": "satu"}}],
        "defaults": {"kyc": 1, "kyc_w": "satu"},
    },
    {
        "key": "konsumen", "number": "POJK S-22/2023", "instrument": "POJK", "source": "OJK",
        "title": "Pelindungan Konsumen dan Masyarakat di Sektor Lembaga Jasa Keuangan",
        "decision": "APPLICABLE",
        "pasal": [
            ("2", "DEF", "Konsumen adalah setiap orang yang memiliki dan/atau memanfaatkan produk dan/atau layanan yang disediakan oleh Pelaku Usaha Jasa Keuangan."),
            ("19", "OBL", "Pelaku Usaha Jasa Keuangan wajib menyampaikan ringkasan informasi produk dan layanan kepada calon Konsumen sebelum perjanjian ditandatangani."),
            ("33", "OBL", "Pelaku Usaha Jasa Keuangan wajib menindaklanjuti pengaduan Konsumen paling lama {adu} ({adu_w}) hari kerja setelah pengaduan diterima."),
            ("40", "PERM", "Pelaku Usaha Jasa Keuangan dapat memperpanjang jangka waktu penanganan pengaduan dalam kondisi tertentu."),
            ("44", "OBL", "Pelaku Usaha Jasa Keuangan wajib menyampaikan laporan penanganan pengaduan kepada Otoritas Jasa Keuangan setiap triwulan."),
        ],
        "versions": [{"date": -400, "p": {"adu": 20, "adu_w": "dua puluh"}},
                     {"date": -60, "p": {"adu": 10, "adu_w": "sepuluh"},
                      "add": {"50": "Pelaku Usaha Jasa Keuangan wajib menyediakan layanan pengaduan yang dapat diakses penyandang disabilitas."}}],
    },
    {
        "key": "siber", "number": "SEOJK S-29/2022", "instrument": "SEOJK", "source": "OJK",
        "title": "Ketahanan dan Keamanan Siber bagi Bank Umum",
        "decision": "APPLICABLE",
        "pasal": [
            ("3", "OBL", "Bank wajib melakukan penilaian tingkat maturitas keamanan siber paling sedikit 1 (satu) kali dalam 1 (satu) tahun."),
            ("7", "OBL", "Bank wajib melakukan uji penetrasi terhadap sistem elektronik kritikal paling sedikit {pentest} ({pentest_w}) kali dalam 1 (satu) tahun."),
            ("9", "OBL", "Bank wajib melaporkan insiden siber kepada Otoritas Jasa Keuangan paling lambat {siber} ({siber_w}) jam setelah insiden diketahui."),
            ("14", "OBL", "Bank wajib memiliki unit atau fungsi yang bertanggung jawab atas ketahanan dan keamanan siber."),
        ],
        "versions": [{"date": -500, "p": {"pentest": 1, "pentest_w": "satu", "siber": 24, "siber_w": "dua puluh empat"}},
                     {"date": -20, "p": {"pentest": 2, "pentest_w": "dua", "siber": 24, "siber_w": "dua puluh empat"}}],
    },
    {
        "key": "tatakelola", "number": "POJK S-17/2023", "instrument": "POJK", "source": "OJK",
        "title": "Penerapan Tata Kelola bagi Bank Umum",
        "decision": "APPLICABLE",
        "pasal": [
            ("5", "OBL", "Bank wajib menerapkan tata kelola yang baik dalam setiap kegiatan usaha pada seluruh tingkatan organisasi."),
            ("26", "OBL", "Direksi wajib menyusun laporan pelaksanaan tata kelola dan menyampaikannya kepada Otoritas Jasa Keuangan paling lambat {gcg} ({gcg_w}) bulan setelah tahun buku berakhir."),
            ("31", "OBL", "Bank wajib membentuk komite pemantau risiko yang diketuai oleh komisaris independen."),
            ("38", "PROHIB", "Anggota Direksi dilarang merangkap jabatan sebagai anggota Direksi pada lembaga jasa keuangan lain."),
        ],
        "versions": [{"date": -900, "p": {"gcg": 5, "gcg_w": "lima"}}, {"date": -300, "p": {"gcg": 4, "gcg_w": "empat"}},
                     {"date": -10, "p": {"gcg": 4, "gcg_w": "empat"}, "editorial": True}],
    },
    {
        "key": "pjp", "number": "PBI S-23/2021", "instrument": "PBI", "source": "BANK_INDONESIA",
        "title": "Penyelenggara Jasa Pembayaran",
        "decision": "APPLICABLE",  # disarankan NOT_APPLICABLE (entitas bank), diputuskan manusia APPLICABLE karena izin PJP
        "decision_reason": "Walau entitas bank umum, organisasi memegang izin PJP Kategori 1 sehingga terikat.",
        "pasal": [
            ("1", "DEF", "Penyelenggara Jasa Pembayaran adalah bank atau lembaga selain bank yang menyediakan jasa untuk memfasilitasi transaksi pembayaran."),
            ("47", "OBL", "Penyelenggara Jasa Pembayaran wajib menyampaikan laporan berkala kepada Bank Indonesia setiap bulan paling lambat tanggal {pjp} bulan berikutnya."),
            ("52", "OBL", "Penyelenggara Jasa Pembayaran wajib menerapkan manajemen risiko dan standar keamanan sistem informasi."),
        ],
        "versions": [{"date": -800, "p": {"pjp": 15}}],
    },
    {
        "key": "bpr", "number": "POJK S-05/2024", "instrument": "POJK", "source": "OJK",
        "title": "Tata Kelola Bank Perkreditan Rakyat (BPR)",
        "decision": "NOT_APPLICABLE",
        "decision_reason": "Organisasi adalah bank umum, bukan BPR/BPRS; dipertahankan sebagai jawaban audit 'mengapa tidak'.",
        "pasal": [("3", "OBL", "BPR wajib memiliki paling sedikit 2 (dua) anggota Direksi."),
                  ("8", "OBL", "BPR wajib menyampaikan laporan tata kelola setiap tahun.")],
        "versions": [{"date": -200, "p": {}}],
    },
    {
        "key": "pdp", "number": "UU S-27/2022", "instrument": "UU", "source": "PERATURAN_JDIH",
        "title": "Pelindungan Data Pribadi",
        "decision": "REQUIRES_FURTHER_REVIEW",
        "pasal": [
            ("20", "OBL", "Pengendali Data Pribadi wajib memiliki dasar pemrosesan Data Pribadi."),
            ("46", "OBL", "Pengendali Data Pribadi wajib menyampaikan pemberitahuan tertulis paling lambat 3 x 24 (tiga kali dua puluh empat) jam apabila terjadi kegagalan Pelindungan Data Pribadi."),
            ("53", "OBL", "Pengendali Data Pribadi wajib menunjuk pejabat yang melaksanakan fungsi Pelindungan Data Pribadi dalam hal pemrosesan dilakukan dalam skala besar."),
        ],
        "versions": [{"date": -1000, "p": {}}],
    },
    {
        "key": "alihdaya_lama", "number": "POJK S-09/2016", "instrument": "POJK", "source": "OJK",
        "title": "Prinsip Kehati-hatian dalam Alih Daya oleh Bank Umum",
        "decision": None,
        "pasal": [("6", "OBL", "Bank wajib melaporkan rencana alih daya kepada Otoritas Jasa Keuangan paling lambat 60 (enam puluh) hari sebelum perjanjian ditandatangani.")],
        "versions": [{"date": -3000, "p": {}}],
        "status": "REVOKED",
    },
    {
        "key": "alihdaya", "number": "POJK S-12/2024", "instrument": "POJK", "source": "OJK",
        "title": "Penggunaan Pihak Penyedia Jasa (Alih Daya) oleh Bank Umum",
        "decision": "APPLICABLE",
        "revokes": "alihdaya_lama",
        "pasal": [
            ("4", "OBL", "Bank wajib memiliki kebijakan dan prosedur penggunaan penyedia jasa yang disetujui Direksi."),
            ("11", "OBL", "Bank wajib melakukan evaluasi kinerja penyedia jasa paling sedikit 1 (satu) kali dalam 1 (satu) tahun."),
            ("27", "OBL", "Ketentuan sebagaimana diatur dalam POJK S-09/2016 dicabut dan dinyatakan tidak berlaku. Bank wajib menyesuaikan perjanjian alih daya paling lambat 12 (dua belas) bulan sejak Peraturan ini berlaku."),
        ],
        "versions": [{"date": -90, "p": {}}],
    },
    {
        "key": "keberlanjutan", "number": "SEOJK S-16/2021", "instrument": "SEOJK", "source": "OJK",
        "title": "Bentuk dan Isi Laporan Tahunan Emiten",
        "decision": None,
        "status": "UNKNOWN",  # edge case kualitas korpus: status belum direkonsiliasi
        "pasal": [("2", "OBL", "Emiten wajib menyampaikan laporan tahunan kepada Otoritas Jasa Keuangan paling lambat akhir bulan keempat setelah tahun buku berakhir.")],
        "versions": [{"date": -1200, "p": {}}],
    },
]


# ---------------------------------------------------------------------------------------------
# Korpus tambahan (SM-01: 30–50 dokumen, ≥ 8 per kategori sumber). Setiap entri:
# (sumber, instrumen, nomor, judul, keputusan, [(pasal, jenis, teks), ...])
# keputusan None = belum diasesmen (NOT_ASSESSED) — realistis untuk korpus yang sedang dikurasi.
# ---------------------------------------------------------------------------------------------
_EXTRA = [
    # --- Bank Indonesia ---
    ("BANK_INDONESIA", "PBI", "PBI S-22/2020", "Sistem Pembayaran", None, [
        ("1", "DEF", "Sistem Pembayaran adalah sistem yang mencakup seperangkat aturan, lembaga, mekanisme, infrastruktur, sumber dana untuk pembayaran, dan akses ke sumber dana untuk pembayaran."),
        ("9", "OBL", "Penyelenggara Sistem Pembayaran wajib memperoleh izin dari Bank Indonesia sebelum melakukan kegiatan."),
        ("15", "OBL", "Penyelenggara Sistem Pembayaran wajib menyampaikan laporan insiden operasional kepada Bank Indonesia paling lambat 1 (satu) jam setelah insiden diketahui.")]),
    ("BANK_INDONESIA", "PBI", "PBI S-14/2023", "Transparansi Suku Bunga Dasar Kredit Bank Umum", "APPLICABLE", [
        ("3", "OBL", "Bank wajib mengumumkan suku bunga dasar kredit melalui situs web Bank setiap bulan."),
        ("5", "OBL", "Bank wajib menyampaikan laporan suku bunga dasar kredit kepada Bank Indonesia paling lambat tanggal 7 (tujuh) bulan berikutnya."),
        ("8", "PERM", "Bank dapat menambahkan komponen premi risiko sesuai profil debitur.")]),
    ("BANK_INDONESIA", "PADG", "PADG S-11/2022", "Pelaporan Kegiatan Penukaran Valuta Asing oleh Bank Umum", "APPLICABLE", [
        ("2", "OBL", "Bank wajib menyampaikan laporan kegiatan penukaran valuta asing kepada Bank Indonesia setiap bulan paling lambat tanggal 10 (sepuluh) bulan berikutnya."),
        ("6", "OBL", "Bank wajib menatausahakan bukti transaksi penukaran valuta asing paling singkat 5 (lima) tahun.")]),
    ("BANK_INDONESIA", "PBI", "PBI S-07/2024", "Giro Wajib Minimum Bank Umum dalam Rupiah dan Valuta Asing", "APPLICABLE", [
        ("1", "DEF", "Giro Wajib Minimum adalah jumlah dana minimum yang wajib dipelihara oleh Bank dalam rekening giro di Bank Indonesia."),
        ("4", "OBL", "Bank wajib memenuhi Giro Wajib Minimum dalam Rupiah sebesar 9% (sembilan persen) dari dana pihak ketiga dalam Rupiah."),
        ("11", "OBL", "Bank wajib membayar sanksi kewajiban membayar apabila tidak memenuhi Giro Wajib Minimum paling lambat 5 (lima) hari kerja setelah surat pemberitahuan diterima.")]),
    ("BANK_INDONESIA", "PADG", "PADG S-24/2021", "Standar Nasional Quick Response Code untuk Pembayaran", None, [
        ("3", "OBL", "Penyelenggara Jasa Pembayaran wajib menggunakan standar QR Code yang ditetapkan Bank Indonesia."),
        ("7", "OBL", "Penyelenggara Jasa Pembayaran wajib melaporkan jumlah merchant QRIS setiap triwulan.")]),
    ("BANK_INDONESIA", "PBI", "PBI S-03/2023", "Pelindungan Konsumen Bank Indonesia bagi Lembaga Jasa Keuangan", "APPLICABLE", [
        ("8", "OBL", "Penyelenggara wajib menyediakan layanan pengaduan konsumen yang dapat diakses setiap hari kerja."),
        ("14", "OBL", "Penyelenggara wajib menyelesaikan pengaduan konsumen paling lama 20 (dua puluh) hari kerja setelah pengaduan diterima secara lengkap.")]),
    ("BANK_INDONESIA", "PBI", "PBI S-19/2022", "Penyelenggaraan Transfer Dana", None, [
        ("5", "OBL", "Penyelenggara Transfer Dana wajib mencantumkan identitas pengirim dalam setiap perintah transfer dana."),
        ("12", "OBL", "Penyelenggara Transfer Dana wajib mengembalikan dana yang gagal ditransfer paling lambat 2 (dua) hari kerja.")]),
    # --- Peraturan / JDIH ---
    ("PERATURAN_JDIH", "UU", "UU S-04/2023", "Pengembangan dan Penguatan Sektor Lembaga Jasa Keuangan", "APPLICABLE", [
        ("6", "OBL", "Lembaga Jasa Keuangan wajib menerapkan prinsip tata kelola yang baik dan manajemen risiko yang memadai."),
        ("231", "OBL", "Lembaga Jasa Keuangan wajib menyediakan unit pelaksana fungsi kepatuhan yang independen."),
        ("245", "PROHIB", "Lembaga Jasa Keuangan dilarang memberikan informasi yang menyesatkan kepada konsumen.")]),
    ("PERATURAN_JDIH", "PP", "PP S-71/2019", "Penyelenggaraan Sistem dan Transaksi Elektronik", None, [
        ("14", "OBL", "Penyelenggara Sistem Elektronik wajib melaksanakan prinsip pelindungan data pribadi dalam pemrosesan."),
        ("24", "OBL", "Penyelenggara Sistem Elektronik wajib memberitahukan secara tertulis kepada pemilik data pribadi apabila terjadi kegagalan pelindungan.")]),
    ("PERATURAN_JDIH", "UU", "UU S-08/2010", "Pencegahan dan Pemberantasan Tindak Pidana Pencucian Uang", "APPLICABLE", [
        ("18", "OBL", "Pihak Pelapor wajib menerapkan prinsip mengenali Pengguna Jasa."),
        ("23", "OBL", "Penyedia jasa keuangan wajib menyampaikan laporan transaksi keuangan tunai dalam jumlah paling sedikit Rp500.000.000,00 kepada PPATK paling lambat 14 (empat belas) hari kerja."),
        ("29", "PERM", "Pihak Pelapor dapat menolak transaksi dengan Pengguna Jasa yang tidak memenuhi ketentuan identifikasi.")]),
    ("PERATURAN_JDIH", "PP", "PP S-43/2015", "Pihak Pelapor dalam Pencegahan dan Pemberantasan Tindak Pidana Pencucian Uang", None, [
        ("2", "DEF", "Pihak Pelapor meliputi penyedia jasa keuangan dan penyedia barang dan/atau jasa lain."),
        ("8", "OBL", "Pihak Pelapor wajib menyampaikan laporan kepada PPATK sesuai bentuk dan tata cara yang ditetapkan.")]),
    ("PERATURAN_JDIH", "UU", "UU S-11/2008", "Informasi dan Transaksi Elektronik", None, [
        ("15", "OBL", "Setiap Penyelenggara Sistem Elektronik wajib menyelenggarakan Sistem Elektronik secara andal dan aman."),
        ("16", "OBL", "Penyelenggara Sistem Elektronik wajib mengoperasikan Sistem Elektronik yang dapat menampilkan kembali informasi elektronik secara utuh.")]),
    ("PERATURAN_JDIH", "PP", "PP S-80/2019", "Perdagangan melalui Sistem Elektronik", None, [
        ("13", "OBL", "Pelaku Usaha wajib menyampaikan informasi yang lengkap dan benar mengenai barang yang ditawarkan."),
        ("27", "OBL", "Pelaku Usaha wajib menyimpan data transaksi paling singkat 10 (sepuluh) tahun.")]),
    ("PERATURAN_JDIH", "PERPRES", "Perpres S-114/2020", "Strategi Nasional Keuangan Inklusif", None, [
        ("3", "DEF", "Keuangan inklusif adalah kondisi ketika setiap anggota masyarakat mempunyai akses terhadap layanan keuangan formal."),
        ("6", "PERM", "Kementerian dan lembaga dapat menyusun program pendukung keuangan inklusif.")]),
    # --- OJK tambahan ---
    ("OJK", "POJK", "POJK S-18/2016", "Penerapan Manajemen Risiko bagi Bank Umum", "APPLICABLE", [
        ("2", "OBL", "Bank wajib menerapkan manajemen risiko secara efektif baik secara individual maupun konsolidasi."),
        ("21", "OBL", "Bank wajib menyampaikan laporan profil risiko kepada Otoritas Jasa Keuangan setiap triwulan paling lambat 15 (lima belas) hari kerja setelah akhir triwulan."),
        ("25", "OBL", "Bank wajib memiliki satuan kerja manajemen risiko yang independen terhadap satuan kerja operasional.")]),
    ("OJK", "POJK", "POJK S-11/2016", "Kewajiban Penyediaan Modal Minimum Bank Umum", "APPLICABLE", [
        ("2", "OBL", "Bank wajib menyediakan modal minimum sesuai profil risiko paling rendah 8% (delapan persen) dari aset tertimbang menurut risiko."),
        ("40", "OBL", "Bank wajib menyampaikan laporan perhitungan kewajiban penyediaan modal minimum setiap bulan.")]),
    ("OJK", "POJK", "POJK S-37/2019", "Transparansi dan Publikasi Laporan Bank Umum", "APPLICABLE", [
        ("5", "OBL", "Bank wajib mempublikasikan laporan keuangan triwulanan pada situs web Bank paling lambat akhir bulan kedua setelah akhir triwulan."),
        ("9", "OBL", "Bank wajib menyampaikan laporan tahunan kepada Otoritas Jasa Keuangan paling lambat 4 (empat) bulan setelah tahun buku berakhir.")]),
    ("OJK", "POJK", "POJK S-10/2022", "Layanan Pendanaan Bersama Berbasis Teknologi Informasi (Pinjam Meminjam)", "NOT_APPLICABLE", [
        ("8", "OBL", "Penyelenggara wajib berbentuk badan hukum perseroan terbatas."),
        ("44", "OBL", "Penyelenggara wajib menyampaikan laporan bulanan kepada Otoritas Jasa Keuangan.")]),
    ("OJK", "POJK", "POJK S-05/2016", "Rencana Bisnis Bank Umum", "APPLICABLE", [
        ("4", "OBL", "Bank wajib menyusun rencana bisnis yang realistis dan disetujui Dewan Komisaris."),
        ("17", "OBL", "Bank wajib menyampaikan rencana bisnis kepada Otoritas Jasa Keuangan paling lambat akhir bulan November."),
        ("21", "OBL", "Bank wajib menyampaikan laporan realisasi rencana bisnis setiap semester.")]),
]

for _src, _ins, _num, _title, _dec, _pasal in _EXTRA:
    TOPICS.append({"key": _num.lower().replace(" ", "_").replace("/", "_"), "number": _num, "instrument": _ins,
                   "source": _src, "title": _title, "decision": _dec, "pasal": _pasal,
                   "decision_reason": ("Organisasi bukan penyelenggara layanan ini" if _dec == "NOT_APPLICABLE" else None),
                   "versions": [{"date": -400 - 37 * len(TOPICS), "p": {}}]})


def version_texts(topic: dict, vi: int) -> dict[str, str]:
    """Teks per pasal untuk versi ke-vi (1-based) — dipakai generator dan evaluasi ground truth."""
    v = topic["versions"][vi - 1]
    params = {**topic.get("defaults", {}), **v.get("p", {})}
    texts = {}
    for label, _kind, tmpl in topic["pasal"]:
        body = tmpl.format(**params) if "{" in tmpl else tmpl
        if v.get("editorial") and label == topic["pasal"][0][0]:
            body = body.replace(" dalam setiap ", " pada setiap ")
        texts[label] = body
    texts.update(v.get("add", {}))
    return texts
