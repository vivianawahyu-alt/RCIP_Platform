import difflib
import html
import re

MATERIAL_THRESHOLD = 0.98


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


def compare_texts(base: str, new: str) -> dict:
    """Diff deterministik (tanpa AI). change_type None bila teks identik setelah normalisasi spasi."""
    a, b = _norm(base), _norm(new)
    if a == b:
        return {"change_type": None, "similarity": 1.0, "is_material": False, "diff_html": html.escape(a)}
    m = difflib.SequenceMatcher(None, a, b, autojunk=False)
    # tampilan diff per kata (lebih terbaca untuk teks hukum); skor kemiripan tetap per karakter
    wa, wb = a.split(" "), b.split(" ")
    wm = difflib.SequenceMatcher(None, wa, wb, autojunk=False)
    parts = []
    for tag, i1, i2, j1, j2 in wm.get_opcodes():
        if tag == "equal":
            parts.append(html.escape(" ".join(wa[i1:i2])))
        else:
            if i2 > i1:
                parts.append(f"<del>{html.escape(' '.join(wa[i1:i2]))}</del>")
            if j2 > j1:
                parts.append(f"<ins>{html.escape(' '.join(wb[j1:j2]))}</ins>")
    sim = round(m.ratio(), 4)
    # angka berubah (mis. 24 jam -> 12 jam) selalu material
    numbers_changed = re.findall(r"\d+", a) != re.findall(r"\d+", b)
    return {"change_type": "TEXT_MODIFIED", "similarity": sim,
            "is_material": numbers_changed or sim < MATERIAL_THRESHOLD, "diff_html": " ".join(x for x in parts if x)}
