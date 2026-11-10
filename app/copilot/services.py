"""W15 copilot advisori — hanya-baca terhadap rantai kepatuhan.

Retrieval: full-text bahasa Indonesia atas versi PUBLISHED; kandidat diambil dengan OR atas lexeme konten,
lalu diberi skor cakupan (proporsi lexeme pertanyaan yang muncul pada pasal). Di bawah ambang → INSUFFICIENT_BASIS.
Tanpa LLM (moda E15.1 yang terdokumentasi) jawaban berupa kutipan pasal terperingkat. Setiap interaksi dicatat
di ai_call_log (templat copilot_retrieval/v1)."""
import json
import math
import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.compliance.services import corpus_basis, disclaimer
from app.platform.config_service import get_value
from app.platform.governance import audit
from app.platform.models import AiCallLog

MIN_COVERAGE = 0.5
# kata tanya & kata fungsi yang tidak membawa makna regulasi
STOP = {"apa", "apakah", "berapa", "bagaimana", "kapan", "siapa", "mana", "dimana", "mengapa", "kenapa", "yang", "untuk",
        "dengan", "dan", "atau", "di", "ke", "dari", "pada", "dalam", "kami", "kita", "saya", "harus", "perlu", "ada",
        "itu", "ini", "tentang", "terkait", "mengenai", "aturan", "ketentuan", "kewajiban", "wajib", "regulasi", "berlaku",
        "bank", "lama", "batas", "waktu", "hari", "berapakah", "adakah", "sebutkan", "jelaskan", "boleh", "bisa", "oleh"}
LEGAL_ADVICE = re.compile(r"\b(apakah kami (melanggar|patuh|aman)|nasihat hukum|pendapat hukum|apakah (boleh|sah|legal)|sanksi apa yang akan)\b", re.I)


def _terms(question: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9]+", question.lower())
    return [w for w in words if w not in STOP and len(w) > 1]


def retrieve(db: Session, question: str, limit: int = 3) -> tuple[list[dict], list[str]]:
    terms = _terms(question)
    if not terms:
        return [], []
    lexemes = [r[0] for r in db.execute(text("SELECT unnest(tsvector_to_array(to_tsvector('indonesian', :q)))"),
                                        {"q": " ".join(terms)}).all()]
    if not lexemes:
        return [], terms
    rows = db.execute(text("""
        SELECT pv.id, pv.text, p.number_label, d.canonical_number, dv.version_number,
               tsvector_to_array(pv.text_search) AS lex,
               ts_rank_cd(pv.text_search, to_tsquery('indonesian', :tq)) AS rank
        FROM corpus.provision_version pv
        JOIN corpus.provision p ON p.id = pv.provision_id
        JOIN corpus.document_version dv ON dv.id = pv.document_version_id
        JOIN corpus.document d ON d.id = dv.document_id
        WHERE dv.state = 'PUBLISHED' AND d.status NOT IN ('REVOKED')
          AND dv.version_number = (SELECT max(version_number) FROM corpus.document_version
                                   WHERE document_id = d.id AND state = 'PUBLISHED')
          AND pv.text_search @@ to_tsquery('indonesian', :tq)
        ORDER BY rank DESC LIMIT 40"""), {"tq": " | ".join(lexemes)}).all()
    # bobot IDF: istilah yang muncul di hampir semua pasal (mis. "indonesia") berbobot kecil
    stats = db.execute(text("""SELECT count(*) AS n, """ + ", ".join(
        f"count(*) FILTER (WHERE pv.text_search @@ to_tsquery('indonesian', :l{i})) AS d{i}" for i in range(len(lexemes))) + """
        FROM corpus.provision_version pv JOIN corpus.document_version dv ON dv.id = pv.document_version_id
        WHERE dv.state = 'PUBLISHED'"""), {f"l{i}": lx for i, lx in enumerate(lexemes)}).one()
    n = max(stats[0], 1)
    weight = {lx: math.log((n + 1) / (stats[i + 1] + 0.5)) for i, lx in enumerate(lexemes)}
    total = sum(weight.values()) or 1.0
    scored = []
    for r in rows:
        coverage = sum(w for lx, w in weight.items() if lx in set(r.lex)) / total
        scored.append({"provision_version_id": str(r.id), "text": r.text, "number_label": r.number_label,
                       "canonical_number": r.canonical_number, "version_number": r.version_number,
                       "rank": float(r.rank), "coverage": round(coverage, 3)})
    scored.sort(key=lambda h: (h["coverage"], h["rank"]), reverse=True)
    return [h for h in scored if h["coverage"] >= MIN_COVERAGE][:limit], lexemes


def answer_query(db: Session, question: str, user_id=None) -> dict:
    note = disclaimer(corpus_basis(db))  # §13.6: penafian tetap juga tampil di antarmuka copilot
    hits, lexemes = retrieve(db, question)
    legal = bool(LEGAL_ADVICE.search(question))
    if not hits:
        state = "INSUFFICIENT_BASIS"
        answer = ("INSUFFICIENT_BASIS: dasar tidak memadai dalam korpus yang disetujui. "
                  f"Istilah yang ditelusuri: {', '.join(lexemes) or '-'}.")
        out = {"answer": answer, "citations": [], "hits": [], "state": state}
    else:
        state = "PRESENTED"
        body = "\n".join(f"[{h['canonical_number']} {h['number_label']}] {h['text']}" for h in hits)
        out = {"answer": f"Ketentuan yang relevan:\n{body}", "state": state,
               "citations": [{"provision_version_id": h["provision_version_id"],
                              "citation": f"{h['canonical_number']} {h['number_label']}"} for h in hits],
               "hits": hits}
    if legal:  # E15.2: tidak memberi nasihat hukum / keputusan kepatuhan
        out["legal_notice"] = ("Copilot tidak memberikan nasihat hukum atau keputusan kepatuhan. Konsultasikan dengan "
                               "Peninjau Hukum atau Pejabat Kepatuhan; ketentuan terkait disertakan sebagai rujukan.")
    out.update({"ai_label": "DRAFT_GENERATED_BY_AI", "disclaimer": note, "mode": "retrieval_only",
                "confidence": round(max((h["coverage"] for h in hits), default=0.0), 3)})
    # FR-COP-005: jawaban yang disajikan tetapi keyakinannya di bawah ambang → ditandai, dapat dikirim untuk ditinjau
    threshold = get_value(db, "copilot.review_threshold")
    out["review_threshold"] = threshold
    out["low_confidence"] = state == "PRESENTED" and out["confidence"] < threshold
    # FR-COP-004: log interaksi lengkap per pengguna (tabelnya append-only, tidak dapat disunting)
    log = AiCallLog(template_name="copilot_retrieval", template_version="v1", model_id="fts-indonesian-coverage",
                    prompt_rendered=question, user_id=user_id, presented_state=state,
                    raw_response=json.dumps({"state": state, "citations": out["citations"],
                                             "low_confidence": out["low_confidence"],
                                             "retrieved": [{"provision_version_id": h["provision_version_id"],
                                                            "citation": f"{h['canonical_number']} {h['number_label']}",
                                                            "coverage": h["coverage"]} for h in hits]}),
                    schema_valid=True, grounding_passed=bool(hits), confidence=out["confidence"])
    db.add(log)
    db.flush()
    audit(db, user_id, "COPILOT_INTERACTION_LOGGED", "ai_call_log", log.id,
          after={"state": state, "confidence": out["confidence"], "low_confidence": out["low_confidence"]})
    if out["low_confidence"]:
        audit(db, user_id, "LOW_CONFIDENCE_FLAGGED", "ai_call_log", log.id,
              after={"confidence": out["confidence"], "threshold": threshold})
    db.commit()
    out["interaction_id"] = str(log.id)
    return out
