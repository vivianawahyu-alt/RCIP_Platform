"""AI Gateway: satu-satunya pintu panggilan LLM (ADR-04).

Mencatat prompt_version/model_version, memvalidasi skema Pydantic, dan menjalankan grounding check.
Tanpa OPENAI_API_KEY dipakai ekstraktor berbasis aturan (deterministik) sehingga demo tetap jalan.
"""
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.platform.models import AiCallLog
from app.shared.config import settings

logger = logging.getLogger("rcip.ai_gateway")
TEMPLATE_DIR = Path(__file__).parent / "templates"


class AIUnavailableException(Exception):
    """LLM tidak tersedia -> alur manual tetap berjalan (NFR-13)."""


class ObligationDraft(BaseModel):
    plain_language_summary: str
    regulated_entity: Optional[str] = None
    required_actions: list[str] = []
    prohibited_actions: list[str] = []
    condition: Optional[str] = None
    frequency: Optional[str] = None
    deadline_expression: Optional[str] = None
    required_evidence: Optional[str] = None
    supporting_phrases: list[str] = []
    confidence: float = Field(ge=0, le=1)


class ExtractionResult(BaseModel):
    creates_obligation: bool
    obligations: list[ObligationDraft] = []


@dataclass
class AICallResult:
    template_name: str
    template_version: str
    model_id: str
    parsed: Optional[ExtractionResult]
    schema_valid: bool
    grounding_passed: bool
    log_id: str


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def verify_grounding(phrases: list[str], source_text: str) -> bool:
    """Setiap frasa pendukung harus muncul verbatim (setelah normalisasi spasi) di teks pasal."""
    src = _norm(source_text)
    return bool(phrases) and all(_norm(p) in src for p in phrases)


OBLIGATION_RE = re.compile(r"\b(wajib|diwajibkan|harus)\b", re.I)
PROHIBITION_RE = re.compile(r"\bdilarang\b", re.I)
NEGATED_RE = re.compile(r"\btidak\s+(wajib|diwajibkan|harus|dilarang)\b", re.I)
REGULATOR_SUBJECT_RE = re.compile(r"^\s*(Otoritas Jasa Keuangan|OJK|Bank Indonesia|PPATK|Menteri|Pemerintah|Kementerian)\b", re.I)


def _rule_based_extract(text: str) -> str:
    """rule-based-v2 (setelah evaluasi G4): penanda kewajiban wajib/diwajibkan/harus + larangan 'dilarang';
    mengabaikan negasi ('tidak wajib'), kalimat definisi ('X adalah ...' sebelum penanda), dan kewajiban milik
    regulator. Keyakinan tetap 0,60 (< ai.confidence_floor) sehingga selalu wajib ditinjau manusia."""
    sentences = [s.strip() for s in re.split(r"(?<=[.;])\s+", text) if s.strip()]
    obligations = []
    for s in sentences:
        m_obl, m_pro = OBLIGATION_RE.search(s), PROHIBITION_RE.search(s)
        m = min((x for x in (m_obl, m_pro) if x), key=lambda x: x.start(), default=None)
        if not m or NEGATED_RE.search(s):
            continue
        subject = s[:m.start()]
        if re.search(r"\badalah\b", subject, re.I) or REGULATOR_SUBJECT_RE.search(subject):
            continue
        prohibited = m is m_pro
        action = s[m.end():].strip(" .;")
        deadline = re.search(r"paling (?:lambat|sedikit|lama|singkat)[^.;]*", s, re.I)
        freq = "EVENT_DRIVEN" if re.search(r"insiden|apabila|dalam hal", s, re.I) else (
            "PERIODIC" if re.search(r"setiap|kali dalam", s, re.I) else None)
        obligations.append({
            "plain_language_summary": f"{'Dilarang' if prohibited else 'Wajib'} {action}",
            "regulated_entity": subject.strip() or None,
            "required_actions": [] if prohibited else [action],
            "prohibited_actions": [action] if prohibited else [],
            "condition": None, "frequency": freq,
            "deadline_expression": deadline.group(0).strip() if deadline else None,
            "required_evidence": None, "supporting_phrases": [s.rstrip(".;")], "confidence": 0.6,
        })
    return json.dumps({"creates_obligation": bool(obligations), "obligations": obligations}, ensure_ascii=False)


def _rule_based_extract_v1(text: str) -> str:
    """Baseline rule-based-v1 (dipertahankan untuk perbandingan evaluasi): kalimat yang memuat 'wajib'."""
    sentences = [s.strip() for s in re.split(r"(?<=[.;])\s+", text) if s.strip()]
    obligations = []
    for s in sentences:
        if not re.search(r"\bwajib\b", s, re.I):
            continue
        deadline = re.search(r"paling (?:lambat|sedikit|lama)[^.;]*", s, re.I)
        freq = "EVENT_DRIVEN" if re.search(r"insiden|apabila|dalam hal", s, re.I) else (
            "PERIODIC" if re.search(r"setiap|kali dalam", s, re.I) else None)
        action = re.split(r"\bwajib\b", s, maxsplit=1, flags=re.I)[1].strip(" .;")
        obligations.append({
            "plain_language_summary": f"Wajib {action}",
            "regulated_entity": s.split(" wajib")[0].strip() or None,
            "required_actions": [action],
            "prohibited_actions": [],
            "condition": None,
            "frequency": freq,
            "deadline_expression": deadline.group(0).strip() if deadline else None,
            "required_evidence": None,
            "supporting_phrases": [s.rstrip(".;")],
            "confidence": 0.6,
        })
    return json.dumps({"creates_obligation": bool(obligations), "obligations": obligations}, ensure_ascii=False)


def _openai_call(prompt: str) -> str:
    try:
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
            json={"model": settings.LLM_MODEL_NAME, "temperature": 0,
                  "response_format": {"type": "json_object"},
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, ValueError) as e:
        raise AIUnavailableException(str(e)) from e


def call_extractor(provision_text: str) -> tuple[str, str, str]:
    """Satu-satunya titik panggilan model ekstraksi. Mengembalikan (model_id, prompt, raw_response)."""
    template = (TEMPLATE_DIR / "obligation_v1.txt").read_text(encoding="utf-8")
    prompt = template.replace("{provision_text}", provision_text)
    if settings.OPENAI_API_KEY:
        return settings.LLM_MODEL_NAME, prompt, _openai_call(prompt)
    return "rule-based-v2", prompt, _rule_based_extract(provision_text)


def parse_and_ground(raw: str, provision_text: str) -> tuple[Optional[ExtractionResult], bool, bool]:
    parsed, schema_valid = None, True
    try:
        parsed = ExtractionResult.model_validate_json(raw)
    except ValidationError:
        schema_valid = False
    grounded = bool(parsed) and all(verify_grounding(o.supporting_phrases, provision_text) for o in parsed.obligations)
    if parsed and not parsed.obligations:
        grounded = True
    return parsed, schema_valid, grounded


def extract_obligations(db: Session, provision_text: str) -> AICallResult:
    model_id, prompt, raw = call_extractor(provision_text)

    parsed, schema_valid = None, True
    try:
        parsed = ExtractionResult.model_validate_json(raw)
    except ValidationError as e:
        schema_valid = False
        logger.error("AI_SCHEMA_VIOLATION: %s", e)

    grounded = bool(parsed) and all(verify_grounding(o.supporting_phrases, provision_text) for o in parsed.obligations)
    if parsed and not parsed.obligations:
        grounded = True

    conf = max((o.confidence for o in parsed.obligations), default=None) if parsed else None
    log = AiCallLog(template_name="obligation_extractor", template_version="v1", model_id=model_id,
                    prompt_rendered=prompt, raw_response=raw, schema_valid=schema_valid,
                    grounding_passed=grounded, confidence=conf)
    db.add(log)
    db.flush()
    return AICallResult("obligation_extractor", "v1", model_id, parsed, schema_valid, grounded, str(log.id))
