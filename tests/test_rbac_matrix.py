"""Matriks RBAC: tes yang tidak menyentuh database (hanya data matriks) — memastikan app/shared/rbac_matrix.py identik dengan tabel desain.

Tabel di bawah ditulis ulang SECARA TERPISAH dari rbac_matrix.py dalam bentuk grid teks yang mudah dicocokkan dengan
gambar tabel. Bila seseorang mengubah matriks tanpa sengaja, tes ini gagal dan menunjuk baris + peran yang berbeda.
Kolom: RA CO BCO LR CM IA EX SA   ("-" = tanpa akses)
"""
import re
from pathlib import Path

import pytest

from app.shared import rbac_matrix as M

GRID = """
source_registry       | CRU   | R   | -     | R  | R  | R | -  | CRUD
ingestion             | CRUX  | R   | -     | R  | R  | R | -  | RX
document_version      | CR    | R   | -     | R  | R  | R | R  | R
provision_correction  | CRU   | R   | -     | R  | R  | R | -  | -
relationship          | CRUD  | R   | -     | RU | RA | R | -  | -
doc_status            | CRU   | R   | -     | R  | RA | R | -  | -
taxonomy              | CRU   | CRU | -     | R  | R  | R | -  | CRUD
corpus_search         | R     | R   | R     | R  | R  | R | R  | R
change_detection      | XR    | R   | -     | R  | R  | R | -  | XR
change_review         | CRU   | RU  | -     | RU | RA | R | -  | -
org_profile           | R     | CRU | R     | R  | RA | R | R  | R
applicability         | R     | CRU | -     | RU | A  | R | R  | -
obligation            | CR    | CRU | R     | RU | A  | R | R  | -
obligation_owner      | -     | CRU | R     | -  | RA | R | -  | -
risk                  | R     | CRU | R     | R  | R  | R | R  | -
control_library       | R     | CRU | R     | R  | R  | R | R  | -
control_owner         | -     | CRU | R     | -  | RA | R | -  | -
assessment_campaign   | -     | CRU | R     | -  | RA | R | -  | -
self_assessment       | -     | RU  | CRU   | -  | R  | R | -  | -
assessment_conclusion | -     | CRU | -     | R  | A  | R | R  | -
evidence_request      | -     | CRU | R     | -  | R  | R | -  | -
evidence_upload       | -     | CR  | CR    | -  | R  | R | -  | -
evidence_access       | R     | R   | R     | R  | R  | R | -  | -
finding               | -     | CRU | R     | -  | RA | R | R  | -
remediation           | -     | CRU | RUX   | -  | RA | R | R  | -
finding_closure       | -     | CR  | -     | -  | A  | R | -  | -
finding_reopen        | -     | CR  | -     | -  | X  | R | -  | -
copilot_query         | XR    | XR  | XR    | XR | XR | XR| XR | XR
copilot_promote       | CR    | CR  | -     | CR | R  | - | -  | -
dashboard             | R     | R   | R     | R  | R  | R | R  | R
report_draft          | -     | CRU | -     | R  | R  | R | -  | -
report_issue          | -     | -   | -     | -  | A  | R | R  | -
report_published      | R     | R   | R     | R  | R  | R | R  | R
audit_trail           | R     | R   | -     | R  | R  | R | -  | R
user_admin            | -     | -   | -     | -  | -  | R | -  | CRUD
system_config         | -     | -   | -     | -  | -  | R | -  | CRUDX
"""

# lingkup yang tidak terlihat pada grid huruf: (kapabilitas, peran, huruf) → lingkup menurut tabel
SCOPES = {
    ("obligation", M.RA, "C"): "draft",
    ("obligation", M.BCO, "R"): "own",
    ("control_library", M.BCO, "R"): "own",
    ("self_assessment", M.BCO, "C"): "own", ("self_assessment", M.BCO, "R"): "own", ("self_assessment", M.BCO, "U"): "own",
    ("evidence_upload", M.BCO, "C"): "own", ("evidence_upload", M.BCO, "R"): "own",
    ("evidence_access", M.BCO, "R"): "own",
    ("finding", M.BCO, "R"): "own",
    ("remediation", M.BCO, "R"): "own", ("remediation", M.BCO, "U"): "own", ("remediation", M.BCO, "X"): "own",
    ("finding_closure", M.CO, "C"): "propose",
    ("dashboard", M.BCO, "R"): "own",
    ("audit_trail", M.RA, "R"): "own", ("audit_trail", M.CO, "R"): "own", ("audit_trail", M.SA, "R"): "system",
}


def _grid():
    rows = {}
    for line in GRID.strip().splitlines():
        cap, *cells = [c.strip() for c in line.split("|")]
        assert len(cells) == 8, line
        rows[cap] = {role: ("" if c == "-" else c) for role, c in zip(M.ROLE_ORDER, cells)}
    return rows


EXPECTED = _grid()


def test_every_table_row_is_present_and_nothing_extra():
    assert set(EXPECTED) == set(M.MATRIX), set(EXPECTED) ^ set(M.MATRIX)
    assert len(EXPECTED) == 36  # 36 baris kapabilitas pada tabel desain


@pytest.mark.parametrize("cap", sorted(EXPECTED))
def test_row_matches_table(cap):
    for role in M.ROLE_ORDER:
        got = "".join(sorted(M.MATRIX[cap][role]))
        want = "".join(sorted(EXPECTED[cap][role]))
        assert got == want, f"{cap} / {role}: matriks={got!r}, tabel={want!r}"


def test_scopes_match_table():
    for cap, cells in M.MATRIX.items():
        for role, letters in cells.items():
            for letter, scope in letters.items():
                assert scope == SCOPES.get((cap, role, letter)), (cap, role, letter, scope)
    for (cap, role, letter), scope in SCOPES.items():
        assert M.scope_of(role, cap, letter) == scope, (cap, role, letter)


def test_approve_implies_read_but_nothing_else():
    assert M.allows(M.CM, "applicability", "R")            # tabel: CM hanya "A"
    assert not M.allows(M.CM, "applicability", "U")
    assert not M.allows(M.CM, "applicability", "C")


# ---- aturan bisnis yang paling penting, ditulis eksplisit supaya gagalnya mudah dipahami ----
def test_system_administrator_has_no_compliance_data_access():
    for cap in ("obligation", "risk", "control_library", "finding", "remediation", "assessment_conclusion",
                "evidence_access", "applicability"):
        assert not M.allows(M.SA, cap, "R"), cap


def test_executive_is_read_only_everywhere():
    for cap, cells in M.MATRIX.items():
        assert not (set(cells[M.EX]) & set("CUDAX")) or cap == "copilot_query", cap


def test_only_manager_approves_and_only_manager_reopens_findings():
    assert M.roles_allowed("finding_closure", "A") == [M.CM]
    assert M.roles_allowed("finding_reopen", "X") == [M.CM]
    assert M.roles_allowed("assessment_conclusion", "A") == [M.CM]
    assert M.roles_allowed("report_issue", "A") == [M.CM]
    assert M.roles_allowed("obligation", "A") == [M.CM]
    assert M.roles_allowed("applicability", "A") == [M.CM]


def test_business_owner_cannot_create_findings_actions_or_close():
    assert not M.allows(M.BCO, "finding", "C")
    assert not M.allows(M.BCO, "remediation", "C")
    assert not M.allows(M.BCO, "finding_closure", "C")
    assert M.scope_of(M.BCO, "remediation", "X") == "own"


def test_only_administrator_deletes_registry_and_labels_and_manages_users():
    assert M.roles_allowed("source_registry", "D") == [M.SA]
    assert M.roles_allowed("taxonomy", "D") == [M.SA]
    assert M.roles_allowed("user_admin", "C") == [M.SA]
    assert M.roles_allowed("user_admin", "R") == [M.IA, M.SA]
    assert M.roles_allowed("system_config", "U") == [M.SA]


def test_audit_trail_scopes():
    assert M.scope_of(M.IA, "audit_trail", "R") is None            # "R (all)"
    assert M.scope_of(M.SA, "audit_trail", "R") == "system"
    assert not M.allows(M.BCO, "audit_trail", "R") and not M.allows(M.EX, "audit_trail", "R")


def test_unknown_capability_fails_loudly():
    with pytest.raises(KeyError):
        M.allows(M.RA, "typo_capability", "R")


# ---- setiap require("kapabilitas","huruf") di kode harus merujuk kapabilitas yang ada ----
def test_all_guards_in_code_reference_real_capabilities():
    root = Path(__file__).resolve().parent.parent / "app"
    pat = re.compile(r'require(?:_any)?\(\s*(?:\(\s*)?"([a-z_]+)"\s*,\s*"([CRUDAX])"')
    seen = 0
    for f in root.rglob("*.py"):
        if f.name == "permissions.py":
            continue
        for cap, act in pat.findall(f.read_text(encoding="utf-8")):
            seen += 1
            assert cap in M.MATRIX, f"{f.name}: kapabilitas tidak dikenal {cap!r}"
            assert M.roles_allowed(cap, act), f"{f.name}: {cap}/{act} tidak dimiliki peran mana pun"
    assert seen > 40, "pola pencarian tidak menemukan penjagaan — periksa regex"


def test_generated_typescript_is_in_sync():
    ts = Path(__file__).resolve().parent.parent / "web" / "src" / "permissions.ts"
    if not ts.exists():
        pytest.skip("web/src/permissions.ts belum dibangkitkan (python scripts/gen_permissions_ts.py)")
    import subprocess, sys
    out = subprocess.run([sys.executable, str(ts.parent.parent.parent / "scripts" / "gen_permissions_ts.py"), "--stdout"],
                         capture_output=True, text=True, check=True).stdout
    assert ts.read_text(encoding="utf-8").replace("\r\n", "\n") == out, \
        "web/src/permissions.ts usang → jalankan: python scripts/gen_permissions_ts.py"