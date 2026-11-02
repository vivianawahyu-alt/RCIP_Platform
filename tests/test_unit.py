import pytest

from app.ai.gateway import verify_grounding, _rule_based_extract
from app.corpus.diff_engine import compare_texts
from app.corpus.segmenter import segment_text
from app.platform.governance import enforce_maker_checker
from app.shared.errors import AppError

RAW = """BAB I
KETENTUAN UMUM
Pasal 1
Dalam Peraturan ini yang dimaksud dengan Bank adalah bank umum konvensional.
BAB II
Pasal 2
Bank wajib memiliki kebijakan keamanan siber yang disetujui direksi.
Pasal 2A
Bank wajib melaporkan insiden TI paling lambat 24 (dua puluh empat) jam."""


def test_segmenter_hierarchy():
    segs = segment_text(RAW)
    assert [s.number_label for s in segs] == ["Pasal 1", "Pasal 2", "Pasal 2A"]
    assert segs[0].hierarchical_path == "BAB I/Pasal 1"
    assert segs[1].hierarchical_path == "BAB II/Pasal 2"
    assert "BAB II" not in segs[0].text


def test_diff_material_on_number_change():
    r = compare_texts("paling lambat 24 jam", "paling lambat 12 jam")
    assert r["change_type"] == "TEXT_MODIFIED" and r["is_material"]
    assert "<del>" in r["diff_html"] and "<ins>" in r["diff_html"]
    assert compare_texts("a  b", "a b")["change_type"] is None


def test_grounding():
    assert verify_grounding(["Bank wajib memiliki kebijakan"], "Bank   wajib memiliki kebijakan keamanan siber.")
    assert not verify_grounding(["kalimat karangan AI"], "Bank wajib memiliki kebijakan keamanan siber.")
    assert not verify_grounding([], "apa saja")


def test_rule_based_extractor_is_grounded():
    import json
    text = "Bank wajib menyampaikan laporan paling lambat 24 jam."
    data = json.loads(_rule_based_extract(text))
    assert data["obligations"][0]["deadline_expression"].startswith("paling lambat 24")
    assert verify_grounding(data["obligations"][0]["supporting_phrases"], text)


def test_sod_self_approval_blocked():
    with pytest.raises(AppError) as e:
        enforce_maker_checker("u1", "u1")
    assert e.value.status == 403 and e.value.code == "SOD_VIOLATION"
    with pytest.raises(AppError):
        enforce_maker_checker("u2", "u1", last_editor_id="u2")
    enforce_maker_checker("u3", "u1", last_editor_id="u2")  # tidak melempar
