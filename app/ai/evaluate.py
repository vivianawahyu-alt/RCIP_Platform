"""Evaluasi komponen AI (Gate G4, TRD §13.5). `python -m app.ai.evaluate [--out docs]`

Suite berskor, bukan lulus/gagal per kasus:
  1. Ekstraksi kewajiban — set standar (pasal korpus sintetis berlabel jenis) + set adversarial 16 jebakan.
  2. Guardrail grounding — draf halusinasi buatan harus ditolak verify_grounding.
  3. Deteksi perubahan — recall tingkat ketentuan vs kunci jawaban (SM-04 ≥ 95%) + presisi flag material.
  4. Copilot — 30 pertanyaan bersumber (hit@3, tingkat sitasi SM-09) + 10 di luar korpus (penolakan SM-10).
Butir 4 memerlukan DB berisi korpus sintetis (`python -m seed.generate`); bila tidak ada, dilewati dengan catatan.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.ai.gateway import call_extractor, parse_and_ground, verify_grounding
from app.corpus.diff_engine import compare_texts
from seed.corpus_synthetic import TOPICS, version_texts

ROOT = Path(__file__).resolve().parents[2]
TARGETS = {"change_recall": 0.95, "copilot_citation_rate": 1.0, "copilot_refusal_rate": 1.0,
           "copilot_hit_at_3": 0.80, "grounding_catch_rate": 1.0}


def _prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    return round(p, 3), round(r, 3), round(2 * p * r / (p + r), 3) if p + r else 0.0


def _extract(txt: str, variant: str):
    if variant == "v1":
        from app.ai.gateway import _rule_based_extract_v1
        return "rule-based-v1", parse_and_ground(_rule_based_extract_v1(txt), txt)
    model_id, _, raw = call_extractor(txt)
    return model_id, parse_and_ground(raw, txt)


def _case_set(path: str, variant: str) -> dict:
    cases = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    out = {"cases": [], "correct": 0, "deadline_checked": 0, "deadline_correct": 0}
    for c in cases:
        _, (parsed, valid, grounded) = _extract(c["text"], variant)
        obs = parsed.obligations if parsed else []
        ok = bool(obs) == c["creates"] and (c.get("count") is None or len(obs) == c["count"])
        dl_ok = None
        if c["creates"] and "deadline" in c:
            got, want = [o.deadline_expression for o in obs], c["deadline"]
            dl_ok = all(g is None for g in got) if want is None else any(g and want.lower() in g.lower() for g in got)
            out["deadline_checked"] += 1
            out["deadline_correct"] += bool(dl_ok)
        out["correct"] += ok
        out["cases"].append({"id": c["id"], "trap": c.get("trap", ""), "expected": c["creates"], "predicted": bool(obs),
                             "n_obligations": len(obs), "correct": ok, "deadline_ok": dl_ok, "grounded": grounded})
    out["accuracy"] = round(out["correct"] / len(cases), 3)
    return out


def eval_extraction(variant: str = "current") -> dict:
    model_id = None
    std = {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "schema_invalid": 0, "grounding_failed": 0, "cases": 0, "errors": []}
    seen = set()
    for t in TOPICS:
        for label, kind, _ in t["pasal"]:
            txt = version_texts(t, len(t["versions"])).get(label)
            if not txt or txt in seen:
                continue
            seen.add(txt)
            model_id, (parsed, valid, grounded) = _extract(txt, variant)
            std["cases"] += 1
            std["schema_invalid"] += not valid
            std["grounding_failed"] += not grounded
            pred = bool(parsed and parsed.obligations)
            gold = kind in ("OBL", "PROHIB")
            key = "tp" if pred and gold else "fp" if pred else "fn" if gold else "tn"
            std[key] += 1
            if key in ("fp", "fn"):
                std["errors"].append({"document": t["number"], "pasal": label, "kind": kind, "error": key.upper()})
    std["precision"], std["recall"], std["f1"] = _prf(std["tp"], std["fp"], std["fn"])

    adv = _case_set("tests/ai/adversarial_extraction.yaml", variant)
    held = _case_set("tests/ai/heldout_extraction.yaml", variant)
    return {"model_id": model_id, "standard": std, "adversarial": adv, "heldout": held}


def eval_grounding_guardrail() -> dict:
    """Injeksi halusinasi: frasa pendukung karangan pada pasal definisi harus ditolak."""
    fabricated = ["Bank wajib menyampaikan laporan harian", "paling lambat 3 (tiga) hari kerja", "Direksi wajib menyetujui"]
    total = caught = 0
    for t in TOPICS:
        for label, kind, _ in t["pasal"]:
            if kind != "DEF":
                continue
            txt = version_texts(t, len(t["versions"]))[label]
            for f in fabricated:
                total += 1
                caught += not verify_grounding([f], txt)
    return {"injected": total, "caught": caught, "catch_rate": round(caught / total, 3) if total else 1.0}


def eval_changes() -> dict:
    pairs = yaml.safe_load((ROOT / "seed/ground_truth/changes.yaml").read_text(encoding="utf-8"))
    by_number = {t["number"]: t for t in TOPICS}
    exp_total = detected_ok = spurious = 0
    mat = {"tp": 0, "fp": 0, "fn": 0}
    rows = []
    for p in pairs:
        t = by_number[p["document"]]
        a, b = version_texts(t, p["base"]), version_texts(t, p["new"])
        det = {}
        for lbl in set(a) | set(b):
            if lbl in a and lbl in b:
                r = compare_texts(a[lbl], b[lbl])
                if r["change_type"]:
                    det[lbl] = ("TEXT_MODIFIED", r["is_material"])
            else:
                det[lbl] = ("PROVISION_ADDED" if lbl in b else "PROVISION_DELETED", True)
        expected = {c["pasal"]: c for c in p["expected_changes"]}
        missed = [x for x in expected if x not in det or det[x][0] != expected[x]["type"]]
        extra = [x for x in det if x not in expected]
        exp_total += len(expected)
        detected_ok += len(expected) - len(missed)
        spurious += len(extra)
        for lbl, c in expected.items():
            flag = det.get(lbl, (None, False))[1]
            if flag and c["material"]:
                mat["tp"] += 1
            elif flag and not c["material"]:
                mat["fp"] += 1
            elif not flag and c["material"]:
                mat["fn"] += 1
        rows.append({"pair": p["pair_id"], "expected": sorted(expected), "missed": missed, "spurious": extra})
    mp, mr, mf = _prf(mat["tp"], mat["fp"], mat["fn"])
    return {"pairs": len(pairs), "expected_changes": exp_total, "detected": detected_ok, "spurious": spurious,
            "recall": round(detected_ok / exp_total, 3), "materiality_flag": {"precision": mp, "recall": mr, "f1": mf, **mat},
            "rows": rows}


def eval_copilot() -> dict:
    from sqlalchemy import select

    from app.copilot.services import answer_query
    from app.corpus.models import DocumentVersion
    from app.shared.database import SessionLocal

    db = SessionLocal()
    try:
        if not db.scalar(select(DocumentVersion.id).where(DocumentVersion.origin_url == "synthetic://generator").limit(1)):
            return {"skipped": "Korpus sintetis tidak ada di DB ini; jalankan python -m seed.generate pada DB kosong."}
        grounded = yaml.safe_load((ROOT / "tests/ai/questions_grounded.yaml").read_text(encoding="utf-8"))
        ooc = yaml.safe_load((ROOT / "tests/ai/questions_out_of_corpus.yaml").read_text(encoding="utf-8"))
        hits = answered = cited = 0
        misses = []
        for item in grounded:
            r = answer_query(db, item["q"])
            got = [c["citation"].replace(" Pasal", "|Pasal") for c in r["citations"]]
            if r["state"] == "PRESENTED":
                answered += 1
                cited += bool(got)
            ok = any(e in got for e in item["expected"])
            hits += ok
            if not ok:
                misses.append({"q": item["q"], "expected": item["expected"], "got": got})
        refused = 0
        leaks = []
        for q in ooc:
            r = answer_query(db, q)
            if r["state"] == "INSUFFICIENT_BASIS":
                refused += 1
            else:
                leaks.append({"q": q, "got": [c["citation"] for c in r["citations"]]})
        return {"grounded_questions": len(grounded), "hit_at_3": round(hits / len(grounded), 3),
                "answered": answered, "citation_rate": round(cited / answered, 3) if answered else 1.0,
                "out_of_corpus": len(ooc), "refusal_rate": round(refused / len(ooc), 3), "misses": misses, "leaks": leaks}
    finally:
        db.close()


def run() -> dict:
    res = {"generated_at": datetime.now(timezone.utc).isoformat(), "extraction": eval_extraction(),
           "extraction_baseline_v1": eval_extraction("v1"),
           "grounding_guardrail": eval_grounding_guardrail(), "changes": eval_changes(), "copilot": eval_copilot()}
    cp = res["copilot"]
    res["targets"] = {
        "change_recall": [res["changes"]["recall"], TARGETS["change_recall"]],
        "grounding_catch_rate": [res["grounding_guardrail"]["catch_rate"], TARGETS["grounding_catch_rate"]],
        **({} if "skipped" in cp else {
            "copilot_citation_rate": [cp["citation_rate"], TARGETS["copilot_citation_rate"]],
            "copilot_refusal_rate": [cp["refusal_rate"], TARGETS["copilot_refusal_rate"]],
            "copilot_hit_at_3": [cp["hit_at_3"], TARGETS["copilot_hit_at_3"]]}),
    }
    res["all_targets_met"] = all(v >= t for v, t in res["targets"].values())
    return res


def pct(x):
    return f"{100 * x:.1f}%"


def render(res: dict) -> str:
    ex, adv, ch, cp, g = (res["extraction"]["standard"], res["extraction"]["adversarial"], res["changes"],
                          res["copilot"], res["grounding_guardrail"])
    L = ["# Laporan Evaluasi AI — RCIP", "",
         f"_Dibangkitkan otomatis oleh `python -m app.ai.evaluate` pada {res['generated_at'][:19]} UTC. "
         f"Model ekstraksi: `{res['extraction']['model_id']}`._", "",
         "## Ringkasan terhadap target", "", "| Ukuran | Hasil | Target | Status |", "|---|---|---|---|"]
    names = {"change_recall": "Recall deteksi perubahan (SM-04)", "grounding_catch_rate": "Halusinasi tertangkap grounding",
             "copilot_citation_rate": "Jawaban copilot bersitasi (SM-09)", "copilot_refusal_rate": "Penolakan di luar korpus (SM-10)",
             "copilot_hit_at_3": "Copilot menemukan pasal benar (hit@3)"}
    for k, (v, t) in res["targets"].items():
        L.append(f"| {names[k]} | {pct(v)} | ≥ {pct(t)} | {'Tercapai' if v >= t else 'Belum'} |")
    L += ["", "Ekstraksi kewajiban tidak diberi target lulus/gagal karena TRD menyatakan akurasi model tidak dijanjikan "
          "sebelum baseline disepakati; angka di bawah adalah baseline.", "",
          "## 1. Ekstraksi kewajiban", "",
          f"Set standar: {ex['cases']} pasal unik korpus sintetis, label jenis ditetapkan manual (OBL/PROHIB = menimbulkan kewajiban; "
          "DEF/PERM = tidak).", "",
          "| Presisi | Recall | F1 | TP | FP | FN | TN | Skema tidak valid | Grounding gagal |", "|---|---|---|---|---|---|---|---|---|",
          f"| {pct(ex['precision'])} | {pct(ex['recall'])} | {pct(ex['f1'])} | {ex['tp']} | {ex['fp']} | {ex['fn']} | {ex['tn']} | "
          f"{ex['schema_invalid']} | {ex['grounding_failed']} |", ""]
    if ex["errors"]:
        L += ["Kesalahan pada set standar:", ""] + [f"- {e['document']} {e['pasal']} ({e['kind']}): {e['error']}" for e in ex["errors"]] + [""]
    L += [f"Set adversarial (16 jebakan, TRD §13.5): akurasi {pct(adv['accuracy'])}; tenggat benar "
          f"{adv['deadline_correct']}/{adv['deadline_checked']}.", "",
          "| Kasus | Jebakan | Diharapkan | Prediksi | Benar | Tenggat |", "|---|---|---|---|---|---|"]
    for c in adv["cases"]:
        L.append(f"| `{c['id']}` | {c['trap']} | {'kewajiban' if c['expected'] else 'bukan'} | "
                 f"{c['n_obligations']} kewajiban | {'ya' if c['correct'] else 'TIDAK'} | "
                 f"{'-' if c['deadline_ok'] is None else ('ya' if c['deadline_ok'] else 'TIDAK')} |")
    held = res["extraction"]["heldout"]
    wrong = [c["id"] for c in held["cases"] if not c["correct"]]
    L += ["", f"Held-out: {held['correct']}/{len(held['cases'])} benar" + (f"; salah: {', '.join(wrong)}." if wrong else "."), "",
          "**Interpretasi.** v1 hanya mengenali kata `wajib`, sehingga gagal pada larangan, sinonim (`harus`, "
          "`diwajibkan`), negasi, definisi yang memuat kata Wajib, dan kewajiban milik regulator. v2 menangani pola "
          "tersebut tetapi tetap pendekatan aturan: tidak memahami konteks, rujukan silang, atau lampiran. Karena itu "
          "setiap draf diberi keyakinan 0,60 (di bawah `ai.confidence_floor` 0,70) dan wajib ditinjau manual (E8.3); "
          "AI_DRAFT tidak pernah masuk angka kepatuhan. Bila LLM dikonfigurasi, keluarannya melewati validasi skema dan "
          "grounding yang sama; jalankan ulang evaluasi untuk membandingkan.", "",
          "## 2. Guardrail grounding", "",
          f"{g['injected']} frasa pendukung karangan disisipkan pada pasal definisi; {g['caught']} ditolak "
          f"({pct(g['catch_rate'])}). Draf yang frasanya tidak muncul verbatim di teks pasal ditolak dengan "
          "`AI_GROUNDING_FAILED` dan tidak pernah disimpan sebagai kewajiban.", "",
          "## 3. Deteksi perubahan (deterministik, tanpa AI)", "",
          f"{ch['pairs']} pasangan versi dari 5 rantai perubahan; {ch['detected']}/{ch['expected_changes']} perubahan "
          f"terdeteksi (recall {pct(ch['recall'])}), {ch['spurious']} perubahan semu.", "",
          f"Presisi flag material otomatis: {pct(ch['materiality_flag']['precision'])} (FP {ch['materiality_flag']['fp']}). "
          "Perubahan redaksional ditandai material oleh ambang kemiripan; karena itu flag diff hanya indikasi dan "
          "materialitas diputuskan analis lalu dikonfirmasi Manajer (titik kendali #1).", ""]
    for r in ch["rows"]:
        L.append(f"- `{r['pair']}`: diharapkan {', '.join('Pasal ' + x for x in r['expected'])}; terlewat {r['missed'] or '-'}; semu {r['spurious'] or '-'}")
    L += ["", "## 4. Copilot advisori", ""]
    if "skipped" in cp:
        L.append(f"Dilewati: {cp['skipped']}")
    else:
        L += [f"- Pertanyaan bersumber: {cp['grounded_questions']}; pasal benar dalam 3 teratas: {pct(cp['hit_at_3'])}.",
              f"- Jawaban yang disajikan: {cp['answered']}; seluruhnya bersitasi pasal tersimpan: {pct(cp['citation_rate'])}.",
              f"- Pertanyaan di luar korpus: {cp['out_of_corpus']}; ditolak INSUFFICIENT_BASIS: {pct(cp['refusal_rate'])}."]
        for m in cp["misses"]:
            L.append(f"- Meleset: \"{m['q']}\" → {m['got'] or 'tidak ada'} (diharapkan {m['expected']})")
        for m in cp["leaks"]:
            L.append(f"- Bocor (seharusnya ditolak): \"{m['q']}\" → {m['got']}")
        L += ["", "Moda saat ini: retrieval-only (E15.1) — tanpa narasi generatif, setiap pernyataan adalah kutipan pasal, "
              "sehingga pernyataan faktual tanpa sitasi = 0 secara konstruksi."]
    L += ["", "## Keterbatasan evaluasi", "",
          "- Dataset disusun tim yang sama yang membangun sistem; ada risiko optimisme. Mentor dianjurkan menambah kasus.",
          "- Korpus sintetis berbahasa baku dan rapi, ditulis dengan pola 'X wajib ...' sehingga set standar cenderung "
          "optimistis bagi ekstraktor aturan; set adversarial dan held-out adalah sinyal yang lebih bermakna.",
          "- PDF asli (OCR, penomoran tidak konsisten) akan lebih sulit daripada korpus sintetis.",
          "- Evaluasi LLM belum dijalankan di lingkungan ini (tanpa API key); jalankan ulang setelah key tersedia.", ""]
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs"))
    args = ap.parse_args()
    res = run()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "ai_evaluation.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "ai_evaluation_report.md").write_text(render(res), encoding="utf-8")
    for k, (v, t) in res["targets"].items():
        print(f"{k:<24} {v:.3f}  (target {t})")
    ex = res["extraction"]
    print(f"extraction std P/R/F1   {ex['standard']['precision']}/{ex['standard']['recall']}/{ex['standard']['f1']}")
    print(f"extraction adversarial  {ex['adversarial']['accuracy']}  held-out {ex['heldout']['accuracy']}  "
          f"(v1: {res['extraction_baseline_v1']['adversarial']['accuracy']} / {res['extraction_baseline_v1']['heldout']['accuracy']})")
    print("ALL TARGETS MET" if res["all_targets_met"] else "SOME TARGETS NOT MET")


if __name__ == "__main__":
    main()
