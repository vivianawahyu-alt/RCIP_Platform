"""Segmentasi hirarki peraturan (BAB -> Pasal) berbasis regex. Fungsi murni, mudah diuji."""
import re
from dataclasses import dataclass

BAB_RE = re.compile(r"^[ \t]*BAB[ \t]+([IVXLCDM]+)[ \t]*$", re.M | re.I)
PASAL_RE = re.compile(r"^[ \t]*Pasal[ \t]+(\d+[A-Z]?)[ \t]*$", re.M)


@dataclass
class Segment:
    provision_key: str
    number_label: str
    hierarchical_path: str
    text: str
    confidence: float


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n")
    return re.sub(r"[ \t]+", " ", text)


def segment_text(raw: str) -> list[Segment]:
    text = normalize_text(raw)
    babs = [(m.start(), m.group(1).upper()) for m in BAB_RE.finditer(text)]
    pasals = list(PASAL_RE.finditer(text))
    out: list[Segment] = []
    for i, m in enumerate(pasals):
        end = pasals[i + 1].start() if i + 1 < len(pasals) else len(text)
        # potong pada BAB berikutnya agar judul bab tidak ikut ke isi pasal
        next_bab = next((p for p, _ in babs if m.end() < p < end), None)
        if next_bab is not None:
            end = next_bab
        body = text[m.end():end].strip()
        bab = next((b for p, b in reversed(babs) if p < m.start()), None)
        label = f"Pasal {m.group(1)}"
        path = f"BAB {bab}/{label}" if bab else label
        out.append(Segment(f"PASAL-{m.group(1)}", label, path, body, 0.95 if len(body) > 20 else 0.5))
    return out
