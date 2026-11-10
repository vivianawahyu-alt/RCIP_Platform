"""Segmentasi peraturan perundang-undangan Indonesia berbasis regex. Fungsi murni, mudah diuji.

Struktur dokumen yang dikenali (sesuai UU 12/2011 tentang Pembentukan Peraturan Perundang-undangan):

    [pembukaan: judul, Menimbang, Mengingat, MEMUTUSKAN]
    BATANG TUBUH   → BAB (opsional) → Pasal 1, Pasal 2, ...
    [penutup: "Agar setiap orang mengetahuinya ...", "Ditetapkan di ...", tanda tangan, pengundangan]
    PENJELASAN     → I. UMUM, II. PASAL DEMI PASAL → Pasal 1, Pasal 2, ...  (opsional)

Dua bentuk lain juga dikenali:
  - PERATURAN PERUBAHAN: batang tubuhnya "Pasal I", "Pasal II" (angka romawi). Di dalam Pasal I ada teks
    "Ketentuan Pasal 5 diubah sehingga berbunyi: Pasal 5 ...". Pasal arab di dalamnya adalah ISI perubahan,
    jadi dokumen seperti ini hanya dipotong per Pasal romawi.
  - SURAT EDARAN (SEOJK, SEBI): tanpa "Pasal"; isinya bagian romawi "I. KETENTUAN UMUM", "II. ...", masing-masing
    berisi angka "1.", "2.", .... Dipotong menjadi "Bagian I / Angka 1", dst.

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
# Pasal romawi pada peraturan perubahan: "Pasal I", "PASAL II" (spasi wajib agar "PasaII" tidak tertukar)
PASAL_ROMAN_RE = re.compile(r"^[ \t]*(?i:pasa[l1])[ \t]+([IVX]{1,6})[ \t]*\.?[ \t]*$", re.M)
# Bagian Surat Edaran: "I. KETENTUAN UMUM" — angka romawi + titik + judul berhuruf kapital
SE_SECTION_RE = re.compile(r"^[ \t]*([IVX]{1,6})\.[ \t]+([A-Z][A-Z0-9 ,&()/\-]{2,})[ \t]*$", re.M)
# Angka di dalam bagian Surat Edaran: "1. Dalam Surat Edaran ini ..."
SE_POINT_RE = re.compile(r"^[ \t]*(\d{1,2})\.[ \t]+(?=\S)", re.M)

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


def _confidence(body: str) -> float:
    return 0.95 if len(body) > 20 else 0.5


def _roman_segments(text: str, *, start: int, stop: int, explanation: bool) -> list[Segment]:
    """Peraturan perubahan: potong hanya per "Pasal I/II/..."; pasal arab di dalamnya tetap menjadi isi."""
    part = text[start:stop]
    heads = list(PASAL_ROMAN_RE.finditer(part))
    out: list[Segment] = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(part)
        body = part[m.end():end].strip()
        no = m.group(1)
        if explanation:
            if not body or CUKUP_JELAS_RE.match(body):
                continue
            out.append(Segment(f"PENJELASAN-PASAL-{no}", f"Penjelasan Pasal {no}", f"Penjelasan/Pasal {no}", body,
                               _confidence(body), "PENJELASAN"))
        else:
            out.append(Segment(f"PASAL-{no}", f"Pasal {no}", f"Pasal {no}", body, _confidence(body)))
    return out


def _circular_segments(text: str, *, stop: int) -> list[Segment]:
    """Surat Edaran: bagian romawi berjudul kapital → angka 1., 2., ... yang berurutan di dalamnya."""
    part = text[:stop]
    sections = list(SE_SECTION_RE.finditer(part))
    # bagian dianggap sah hanya bila romawinya berurutan mulai I (menyaring baris kapital lain)
    expected, valid = 1, []
    for m in sections:
        if _roman_value(m.group(1)) == expected:
            valid.append(m)
            expected += 1
    out: list[Segment] = []
    for i, m in enumerate(valid):
        end = valid[i + 1].start() if i + 1 < len(valid) else len(part)
        body = part[m.end():end]
        roman, title = m.group(1), m.group(2).strip().replace("/", "-")
        group = f"Bagian {roman} – {title.title()}"
        # angka yang berurutan 1, 2, 3 … (baris lain yang kebetulan diawali angka diabaikan)
        points, want = [], 1
        for p in SE_POINT_RE.finditer(body):
            if int(p.group(1)) == want:
                points.append(p)
                want += 1
        intro = body[:points[0].start()].strip() if points else body.strip()
        if intro and (len(intro) > 20 or not points):
            out.append(Segment(f"BAGIAN-{roman}", f"Bagian {roman}", f"{group}/Pengantar" if points else group,
                               intro, _confidence(intro), "BAGIAN"))
        for j, p in enumerate(points):
            p_end = points[j + 1].start() if j + 1 < len(points) else len(body)
            txt = body[p.end():p_end].strip()
            no = p.group(1)
            out.append(Segment(f"BAGIAN-{roman}-ANGKA-{no}", f"Angka {no}", f"{group}/Angka {no}", txt,
                               _confidence(txt), "ANGKA"))
    return out


def _is_amendment(text: str, stop: int) -> bool:
    """Peraturan perubahan = ada "Pasal I" DAN "Pasal II", dan Pasal I berisi kata perubahan.
    Syarat ketat ini mencegah salah deteksi saat OCR membaca "Pasal 1" sebagai "Pasal I"."""
    heads = {m.group(1): m for m in PASAL_ROMAN_RE.finditer(text, 0, stop)}
    if "I" not in heads or "II" not in heads:
        return False
    first = text[heads["I"].end():heads["II"].start()]
    return bool(re.search(r"\b(diubah|disisipkan|dihapus|ditambahkan)\b", first, re.I))


def _roman_value(r: str) -> int:
    vals = {"I": 1, "V": 5, "X": 10}
    total = 0
    for a, b in zip(r, r[1:] + " "):
        v = vals[a]
        total += -v if b != " " and vals.get(b, 0) > v else v
    return total


def segment_text(raw: str) -> list[Segment]:
    text = normalize_text(raw)
    # batas batang tubuh: sebelum bagian PENJELASAN (bila ada)
    pj = PENJELASAN_RE.search(text)
    body_end = pj.start() if pj else len(text)
    # isi pasal terakhir berhenti di awal penutup ("Agar setiap orang mengetahuinya", "Ditetapkan di")
    closing = PENUTUP_RE.search(text, 0, body_end)
    body_stop = closing.start() if closing else body_end

    # bentuk dokumen: peraturan perubahan (Pasal romawi) → peraturan biasa (Pasal arab) → surat edaran
    amendment = _is_amendment(text, body_stop)
    if not amendment:
        # bukan peraturan perubahan: "Pasal I"/"Pasal l" adalah salah baca OCR untuk "Pasal 1"
        text = re.sub(r"^([ \t]*(?i:pasa[lI1]))[ \t]+[Il][ \t]*\.?[ \t]*$", r"\1 1", text, flags=re.M)
        # panjang teks bisa berubah → hitung ulang batas penjelasan & penutup
        pj = PENJELASAN_RE.search(text)
        body_end = pj.start() if pj else len(text)
        closing = PENUTUP_RE.search(text, 0, body_end)
        body_stop = closing.start() if closing else body_end
    cut = _roman_segments if amendment else _segments
    out = cut(text, start=0, stop=body_stop, explanation=False)
    if not out:
        return _circular_segments(text, stop=body_stop)
    if pj:  # penjelasan per pasal, mulai dari "PASAL DEMI PASAL"
        pdp = PASAL_DEMI_PASAL_RE.search(text, pj.end())
        if pdp:
            tln = TLN_RE.search(text, pdp.end())
            out += cut(text, start=pdp.end(), stop=tln.start() if tln else len(text), explanation=True)
    return out