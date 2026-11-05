"""Bangkitkan web/src/permissions.ts dari app/shared/rbac_matrix.py (satu sumber kebenaran).
Jalankan: python scripts/gen_permissions_ts.py   (opsi --stdout hanya mencetak)"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.shared import rbac_matrix as M

data = {cap: {r: "".join(cells[r].keys()) for r in M.ROLE_ORDER if cells[r]} for cap, cells in M.MATRIX.items()}
out = ("// DIBANGKITKAN dari app/shared/rbac_matrix.py — jangan diedit tangan. Jalankan: python scripts/gen_permissions_ts.py\n"
       "export const MATRIX: Record<string, Record<string, string>> = "
       + json.dumps(data, indent=2, ensure_ascii=False) + ";\n\n"
       "/** Apakah peran boleh melakukan aksi (C/R/U/D/A/X) pada kapabilitas? 'A' mencakup 'R'. */\n"
       "export const canDo = (role: string, cap: string, letter: string): boolean => {\n"
       "  const cell = MATRIX[cap]?.[role] || \"\";\n"
       "  return cell.includes(letter) || (letter === \"R\" && cell.includes(\"A\"));\n"
       "};\n")
if "--stdout" in sys.argv:
    sys.stdout.write(out)
else:
    Path(__file__).resolve().parent.parent.joinpath("web/src/permissions.ts").write_text(out, encoding="utf-8")