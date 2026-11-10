"""Daftar korpus terbaru di atas + segmenter toleran terhadap salah baca OCR pada judul pasal."""
import uuid

from app.corpus.segmenter import segment_text
from tests.conftest import P, login


def test_newest_document_listed_first(client):
    a = login(client, "analyst")
    # nomor diawali "ZZZ" agar secara abjad pasti di urutan terakhir → membuktikan urutan berdasarkan waktu
    number = f"ZZZ UJI/{uuid.uuid4().hex[:6]}"
    r = client.post(f"{P}/corpus/documents", headers=a, json={"canonical_number": number, "title_id": "Uji urutan"})
    assert r.status_code == 200, r.text
    docs = client.get(f"{P}/corpus/documents", headers=a).json()["data"]
    assert docs[0]["canonical_number"] == number  # dokumen yang baru dibuat harus paling atas


def test_segmenter_tolerates_common_ocr_errors():
    # berbagai salah baca OCR pada nomor pasal mana pun harus tetap terpecah menjadi pasal tersendiri
    heads = ["Pasal1", "Pasal 2", "Pasal27", "PASAL 5", "PasaI 8", "Pasa1 9", "Pasal 10.", "Pasal 3a"]
    text = "\n".join(f"{h}\nIsi pasal ini cukup panjang untuk diuji." for h in heads)
    assert [s.number_label for s in segment_text(text)] == [
        "Pasal 1", "Pasal 2", "Pasal 27", "Pasal 5", "Pasal 8", "Pasal 9", "Pasal 10", "Pasal 3A"]


def test_segmenter_ignores_references_inside_sentences():
    # "Pasal 2" di tengah kalimat adalah rujukan, bukan judul pasal baru
    text = "Pasal 1\nTugas sebagaimana dimaksud dalam Pasal 2 ayat (1) dilaksanakan OJK.\nPasal 2\nIsi pasal dua cukup panjang."
    segs = segment_text(text)
    assert [s.number_label for s in segs] == ["Pasal 1", "Pasal 2"] and "dimaksud dalam Pasal 2" in segs[0].text



def test_segmenter_regulation_structure_from_ocr():
    # pola nyata dari OCR POJK 15/2026: "Pasal" & nomor terpisah baris, nomor halaman "-3-", penutup,
    # dan bagian PENJELASAN yang memuat "Pasal N" lagi
    text = """MEMUTUSKAN:
Pasal
1
Dalam Peraturan ini yang dimaksud dengan Bursa adalah sistem pasar.
Pasal 2
(1) Otoritas berwenang mengawasi Bursa sesuai peraturan perundang-
undangan.
-3-
(2) Ketentuan lebih lanjut diatur OJK.
Pasal 3
Peraturan ini mulai berlaku sejak tanggal diundangkan.
Agar
setiap
orang
mengetahuinya, memerintahkan pengundangan.
Ditetapkan di Jakarta
KETUA DEWAN KOMISIONER
PENJELASAN
ATAS
PERATURAN OTORITAS JASA KEUANGAN
I. UMUM
Uraian umum.
II. PASAL DEMI PASAL
Pasal 1
Cukup jelas.
Pasal 2
Yang dimaksud dengan peraturan perundang-undangan antara lain Peraturan Presiden.
Pasal 3
Cukup jelas.
TAMBAHAN LEMBARAN NEGARA REPUBLIK INDONESIA NOMOR 208"""
    segs = segment_text(text)
    assert [s.number_label for s in segs] == ["Pasal 1", "Pasal 2", "Pasal 3", "Penjelasan Pasal 2"]
    p1, p2, p3, pj2 = segs
    assert "sistem pasar" in p1.text                                   # "Pasal\n1" tetap dikenali
    assert "-3-" not in p2.text and "perundang-undangan" in p2.text    # nomor halaman & pemenggalan dibersihkan
    assert "Cukup jelas" not in p2.text and "Peraturan Presiden" not in p2.text  # penjelasan tidak tercampur
    assert "Agar" not in p3.text and "KETUA" not in p3.text            # penutup & tanda tangan tidak ikut
    assert pj2.provision_type == "PENJELASAN" and pj2.hierarchical_path == "Penjelasan/Pasal 2"
    assert "TAMBAHAN LEMBARAN" not in pj2.text

def test_segmenter_amendment_regulation_keeps_inner_pasal():
    # peraturan perubahan: hanya dipotong per Pasal romawi; "Pasal 5" di dalamnya adalah isi perubahan
    text = """MEMUTUSKAN:
Pasal I
Beberapa ketentuan dalam POJK 1/2021 diubah sebagai berikut:
1. Ketentuan Pasal 5 diubah sehingga berbunyi sebagai berikut:
Pasal 5
Laporan disampaikan paling lambat 5 (lima) hari kerja.
Pasal II
Peraturan ini mulai berlaku pada tanggal diundangkan.
Agar setiap orang mengetahuinya, memerintahkan pengundangan."""
    segs = segment_text(text)
    assert [s.number_label for s in segs] == ["Pasal I", "Pasal II"]
    assert "Pasal 5" in segs[0].text and "5 (lima) hari kerja" in segs[0].text


def test_segmenter_ocr_pasal_I_in_normal_regulation_is_pasal_1():
    # tanpa kata "diubah", "Pasal I" adalah salah baca OCR untuk "Pasal 1"
    segs = segment_text("Pasal I\nIsi pasal satu cukup panjang.\nPasal 2\nIsi pasal dua cukup panjang.")
    assert [s.number_label for s in segs] == ["Pasal 1", "Pasal 2"]


def test_segmenter_circular_letter_sections_and_points():
    text = """SURAT EDARAN OTORITAS JASA KEUANGAN
Yth. Direksi Bank Umum
I. KETENTUAN UMUM
1. Dalam Surat Edaran ini yang dimaksud dengan Bank adalah bank umum.
2. Bank wajib menyusun rencana strategis teknologi informasi.
Rencana mencakup periode 2027 sampai 2029.
II. PELAPORAN
Bank menyampaikan laporan sebagai berikut:
1. laporan tahunan paling lambat akhir Maret;
2. laporan insiden paling lambat 24 jam.
III. PENUTUP
Ketentuan dalam Surat Edaran ini mulai berlaku pada tanggal ditetapkan.
Ditetapkan di Jakarta"""
    segs = segment_text(text)
    assert [s.provision_key for s in segs] == ["BAGIAN-I-ANGKA-1", "BAGIAN-I-ANGKA-2", "BAGIAN-II", "BAGIAN-II-ANGKA-1",
                                               "BAGIAN-II-ANGKA-2", "BAGIAN-III"]
    assert segs[0].hierarchical_path == "Bagian I – Ketentuan Umum/Angka 1" and segs[0].provision_type == "ANGKA"
    assert "periode 2027" in segs[1].text                        # baris lanjutan tetap di angka 2
    assert "Ditetapkan" not in segs[-1].text                       # penutup tidak ikut
