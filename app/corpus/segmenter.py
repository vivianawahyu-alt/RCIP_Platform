"""Segmentasi peraturan perundang-undangan Indonesia berbasis regex. Fungsi murni, mudah diuji.

Struktur dokumen yang dikenali (sesuai UU 12/2011 tentang Pembentukan Peraturan Perundang-undangan):

    [pembukaan: judul, Menimbang, Mengingat, MEMUTUSKAN]
    BATANG TUBUH   → BAB (opsional) → Pasal 1, Pasal 2, ...
    [penutup: "Agar setiap orang mengetahuinya ...", "Ditetapkan di ...", tanda tangan, pengundangan]
    PENJELASAN     → I. UMUM, II. PASAL DEMI PASAL → Pasal 1, Pasal 2, ...  (opsional)

Pasal batang tubuh menjadi segmen "Pasal N". Penjelasan per pasal menjadi segmen terpisah
"Penjelasan Pasal N" (dikelompokkan di bawah "Penjelasan"); penjelasan yang hanya berbunyi
"Cukup jelas." dilewati karena tidak menambah informasi.
"""
import re
from dataclasses import dataclass

BAB_RE = re.compile(r"^[ \t]*BAB[ \t]+([IVXLCDM]+)[ \t]*$", re.M | re.I)
# Judul pasal = satu baris yang isinya HANYA "Pasal <nomor>". Dibuat toleran terhadap salah baca OCR
# yang umum, dan berlaku untuk SEMUA nomor pasal (\d+ = angka berapa pun: 1, 3, 27, 105, ...):
#   Pasa[lI1]  → huruf "l" sering terbaca "I" (i besar) atau "1"  : "PasaI 8", "Pasa1 9"
#   [ \t]*     → spasi boleh hilang                                : "Pasal3", "Pasal27"
#   \.?        → titik di belakang nomor boleh ada                  : "Pasal 10."
#   re.I       → huruf besar/kecil diabaikan                       : "PASAL 5"
# "Pasal" dan nomornya yang terpisah ke dua baris ("Pasal\n1", khas OCR pada teks rata kanan-kiri)
# sudah digabung lebih dulu oleh normalize_text().
# Rujukan di tengah kalimat ("dimaksud dalam Pasal 2 ayat (1)") tetap TIDAK dianggap judul,
# karena ^...$ mewajibkan baris itu tidak berisi teks lain.
PASAL_RE = re.compile(r"^[ \t]*Pasa[lI1][ \t]*(\d+[A-Z]?)[ \t]*\.?[ \t]*$", re.M | re.I)

# Awal bagian PENJELASAN: baris yang isinya hanya kata "PENJELASAN" (huruf kapital, seperti di lembaran resmi)
PENJELASAN_RE = re.compile(r"^[ \t]*PENJELASAN[ \t]*$", re.M)
# Di dalam penjelasan, penjelasan per pasal dimulai setelah judul "PASAL DEMI PASAL"
PASAL_DEMI_PASAL_RE = re.compile(r"^[ \t]*(?:[IVX1l]+\.?[ \t]*)?PASAL DEMI PASAL[ \t]*$", re.M | re.I)
# Awal bagian penutup: isi pasal terakhir berhenti di sini (tanda tangan & pengundangan tidak ikut)
#   \s+ (bukan spasi biasa): OCR sering memecah kalimat ini menjadi satu kata per baris
PENUTUP_RE = re.compile(r"^[ \t]*(Agar\s+setiap\s+orang\s+mengetahuinya|Ditetapkan\s+di)\b", re.M | re.I)
# Nomor halaman lembaran resmi, mis. "-3-" atau "- 12 -", satu baris sendiri
PAGE_NO_RE = re.compile(r"^[ \t]*-[ \t]*\d+[ \t]*-[ \t]*$", re.M)
CUKUP_JELAS_RE = re.compile(r"^\W*cukup jelas\W*$", re.I)
# Akhir penjelasan: catatan nomor Tambahan Lembaran Negara di halaman terakhir
TLN_RE = re.compile(r"^[ \t]*TAMBAHAN LEMBARAN NEGARA\b", re.M | re.I)


@dataclass
class Segment:
    provision_key: str
    number_label: str
    hierarchical_path: str
    text: str
    confidence: float
    provision_type: str = "PASAL"  # PASAL | PENJELASAN


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"_+", " ", text)  # garis bawah sisa OCR ("rangka_persiapan") → spasi
    text = re.sub(r"[ \t]+", " ", text)
    text = PAGE_NO_RE.sub("", text)  # buang nomor halaman "-3-" agar tidak tersisip di tengah isi pasal
    # "Pasal" dan nomornya terpisah baris (OCR) → satukan kembali: "Pasal\n1\n" → "Pasal 1\n"
    text = re.sub(r"^([ \t]*Pasa[lI1])[ \t]*\n[ \t]*(\d+[A-Z]?)[ \t]*\.?[ \t]*$", r"\1 \2", text, flags=re.M | re.I)
    # kata berulang yang terpotong di akhir baris: "perundang-\nundangan" → "perundang-undangan"
    return re.sub(r"(\w)-[ \t]*\n[ \t]*(?=\w)", r"\1-", text)


def _segments(text: str, *, start: int, stop: int, explanation: bool) -> list[Segment]:
    """Potong `text[start:stop]` menjadi segmen per judul pasal."""
    part = text[start:stop]
    babs = [] if explanation else [(m.start(), m.group(1).upper()) for m in BAB_RE.finditer(part)]
    pasals = list(PASAL_RE.finditer(part))
    out: list[Segment] = []
    for i, m in enumerate(pasals):
        end = pasals[i + 1].start() if i + 1 < len(pasals) else len(part)
        # potong pada BAB berikutnya agar judul bab tidak ikut ke isi pasal
        next_bab = next((p for p, _ in babs if m.end() < p < end), None)
        if next_bab is not None:
            end = next_bab
        body = part[m.end():end].strip()
        no = m.group(1).upper()  # "3a" → "3A" agar label & kunci pasal seragam (karena re.I)
        if explanation:
            if not body or CUKUP_JELAS_RE.match(body):
                continue  # "Cukup jelas." tidak perlu disimpan sebagai segmen
            label = f"Penjelasan Pasal {no}"
            out.append(Segment(f"PENJELASAN-PASAL-{no}", label, f"Penjelasan/Pasal {no}", body,
                               0.95 if len(body) > 20 else 0.5, "PENJELASAN"))
            continue
        bab = next((b for p, b in reversed(babs) if p < m.start()), None)
        label = f"Pasal {no}"
        path = f"BAB {bab}/{label}" if bab else label
        out.append(Segment(f"PASAL-{no}", label, path, body, 0.95 if len(body) > 20 else 0.5))
    return out


def segment_text(raw: str) -> list[Segment]:
    text = normalize_text(raw)
    # batas batang tubuh: sebelum bagian PENJELASAN (bila ada)
    pj = PENJELASAN_RE.search(text)
    body_end = pj.start() if pj else len(text)
    # isi pasal terakhir berhenti di awal penutup ("Agar setiap orang mengetahuinya", "Ditetapkan di")
    closing = PENUTUP_RE.search(text, 0, body_end)
    out = _segments(text, start=0, stop=closing.start() if closing else body_end, explanation=False)
    if pj:  # penjelasan per pasal, mulai dari "PASAL DEMI PASAL"
        pdp = PASAL_DEMI_PASAL_RE.search(text, pj.end())
        if pdp:
            tln = TLN_RE.search(text, pdp.end())
            out += _segments(text, start=pdp.end(), stop=tln.start() if tln else len(text), explanation=True)
    return out