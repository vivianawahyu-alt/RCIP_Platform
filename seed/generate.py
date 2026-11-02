"""Generator data sintetis RCIP yang dapat direproduksi (proposal V-TEKI hal. 20, TRD §10.4).

    python -m seed.generate --seed 42 --anchor 2026-10-27

- Seed yang sama + anchor yang sama → ID, teks, status, dan tanggal yang identik (UUID diturunkan dari RNG).
- Memuat pola normal, anomali (tenggat lewat, kontrol tanpa pemilik, risiko diterima lewat tanggal tinjau,
  temuan dibuka kembali), edge case (dokumen dicabut, status UNKNOWN, NOT_APPLICABLE, PARTIAL/REVIEW),
  data kosong (frekuensi/tenggat kosong), dan riwayat waktu ±2 tahun.
- Integritas referensial dijaga oleh FK + trigger DB; jalankan `python -m seed.validate` sesudahnya.
- Idempoten: berhenti bila korpus sintetis sudah ada (gunakan DB baru untuk generate ulang).
Tidak ada data pribadi; semua nama orang/organisasi fiktif.
"""
import argparse
import hashlib
import logging
import random
import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select, text

from app.ai import gateway
from app.compliance.models import (ApplicabilityDecision, Assessment, ComplianceReport, Control, Evidence, Finding,
                                   Obligation, ObligationControlMap, OrganisationProfile, RemediationAction, Risk)
from app.corpus.diff_engine import compare_texts
from app.corpus.models import (Change, ChangeSet, Document, DocumentVersion, Provision, ProvisionVersion, Relationship,
                               TaxonomyLabel)
from app.corpus.review import POPULATION_RULES, THEME_RULES
from app.corpus.services import get_or_create_source
from app.platform.auth import hash_password
from app.platform.models import AppUser, Approval, AuditEvent
from app.shared.database import SessionLocal
from app.shared.storage import put_object
from seed import run as base_seed
from seed.corpus_synthetic import TOPICS, version_texts

log = logging.getLogger("rcip.generate")
MARKER = "synthetic://generator"
EXTRA_USERS = [("owner_it", "BUSINESS_CONTROL_OWNER"), ("owner_ops", "BUSINESS_CONTROL_OWNER"),
               ("owner_fin", "BUSINESS_CONTROL_OWNER"), ("officer2", "COMPLIANCE_OFFICER"),
               ("manager2", "COMPLIANCE_MANAGER")]
SOURCES = {"OJK": ("Otoritas Jasa Keuangan", "https://www.ojk.go.id"),
           "BANK_INDONESIA": ("Bank Indonesia", "https://www.bi.go.id"),
           "PERATURAN_JDIH": ("JDIH Nasional", "https://peraturan.go.id")}


class Gen:
    def __init__(self, db, seed: int, anchor: date):
        self.db, self.rng, self.anchor = db, random.Random(seed), anchor
        self.u: dict[str, AppUser] = {}
        self.stats: dict[str, int] = {}

    # ---------- utilitas deterministik ----------
    def uid(self) -> uuid.UUID:
        return uuid.UUID(int=self.rng.getrandbits(128), version=4)

    def at(self, day_offset: int, hour: int | None = None) -> datetime:
        h = hour if hour is not None else self.rng.randint(8, 17)
        return datetime.combine(self.anchor + timedelta(days=day_offset), time(h, self.rng.randint(0, 59)), tzinfo=timezone.utc)

    def d(self, day_offset: int) -> date:
        return self.anchor + timedelta(days=day_offset)

    def bump(self, k: str, n: int = 1):
        self.stats[k] = self.stats.get(k, 0) + n

    def audit(self, actor: str | None, action: str, otype: str, oid, at: datetime, before=None, after=None):
        self.db.add(AuditEvent(actor_type="USER" if actor else "SYSTEM", actor_id=self.u[actor].id if actor else None,
                               action=action, object_type=otype, object_id=oid, before_state=before, after_state=after,
                               correlation_id=self.uid(), occurred_at=at))

    def approval(self, otype, oid, cp, maker, checker, outcome, at, reason=None, snapshot=None):
        assert maker != checker, "SoD"
        self.db.add(Approval(id=self.uid(), object_type=otype, object_id=oid, control_point=cp, maker_id=self.u[maker].id,
                             last_editor_id=self.u[maker].id, checker_id=self.u[checker].id, outcome=outcome, reason=reason,
                             object_state_snapshot=snapshot or {}, decided_at=at))

    def flush(self):
        self.db.flush()

    # ---------- langkah ----------
    def users(self):
        """Persona inti + tambahan dengan UUID deterministik; profil organisasi sintetis."""
        import yaml
        for name, role in [(n, r.value) for n, r in base_seed.USERS] + EXTRA_USERS:
            if not self.db.scalar(select(AppUser).where(AppUser.username == name)):
                self.db.add(AppUser(id=self.uid(), username=name, email=f"{name}@bank-sinar.example", role=role,
                                    hashed_password=hash_password("demo1234")))
        self.db.flush()
        self.u = {x.username: x for x in self.db.scalars(select(AppUser))}
        self.profile = self.db.scalar(select(OrganisationProfile).limit(1))
        if self.profile is None:
            org = yaml.safe_load((base_seed.HERE / "organisation.yaml").read_text(encoding="utf-8"))
            self.profile = OrganisationProfile(id=self.uid(), **org)
            self.db.add(self.profile)
            self.db.flush()

    def corpus(self):
        self.docs: dict[str, dict] = {}
        for t in TOPICS:
            issuer, url = SOURCES[t["source"]]
            src = get_or_create_source(self.db, t["source"], t["source"], issuer, url)
            doc = Document(id=self.uid(), source_id=src.id, canonical_number=t["number"], instrument_type=t["instrument"],
                           issuer=issuer, title_id=t["title"], status=t.get("status", "IN_FORCE"))
            self.db.add(doc)
            self.flush()
            self.bump("documents")
            versions = []
            provs: dict[str, Provision] = {}
            for vi, v in enumerate(t["versions"], start=1):
                texts = version_texts(t, vi)
                full = "\n".join(f"Pasal {k}\n{x}" for k, x in texts.items())
                eff = self.d(v["date"])
                dv = DocumentVersion(id=self.uid(), document_id=doc.id, version_number=vi,
                                     sha256=hashlib.sha256(full.encode()).hexdigest(), origin_url=MARKER,
                                     canonical_text_ref=f"synthetic/{t['key']}/v{vi}", effective_date=eff, state="PUBLISHED")
                self.db.add(dv)
                self.flush()
                pvs = {}
                for seq, (label, body) in enumerate(texts.items(), start=1):
                    if label not in provs:
                        provs[label] = Provision(id=self.uid(), document_id=doc.id, provision_key=f"PASAL-{label}",
                                                 provision_type="PASAL", number_label=f"Pasal {label}",
                                                 hierarchical_path=f"BAB I/Pasal {label}")
                        self.db.add(provs[label])
                        self.flush()
                    pv = ProvisionVersion(id=self.uid(), provision_id=provs[label].id, document_version_id=dv.id,
                                          sequence=seq, text=body, segmentation_confidence=0.95 if len(body) > 40 else 0.6)
                    self.db.add(pv)
                    pvs[label] = pv
                    self.bump("provision_versions")
                self.flush()
                self.audit("analyst", "VERSION_PUBLISHED", "document_version", dv.id, self.at(v["date"] - 2))
                versions.append({"dv": dv, "pvs": pvs, "offset": v["date"]})
            # label taksonomi: saran aturan, sebagian dikonfirmasi analis
            title = t["title"].lower()
            for dim, rules in (("THEME", THEME_RULES), ("POPULATION", POPULATION_RULES)):
                for value in sorted({val for kw, val in rules.items() if kw in title}):
                    confirmed = self.rng.random() < 0.7
                    self.db.add(TaxonomyLabel(id=self.uid(), document_id=doc.id, dimension=dim, value=value,
                                              state="CONFIRMED" if confirmed else "SUGGESTED", source="RULE",
                                              reason="Kata kunci judul", decided_by=self.u["analyst"].id if confirmed else None))
                    self.bump("taxonomy_labels")
            self.docs[t["key"]] = {"t": t, "doc": doc, "versions": versions, "provs": provs}
        self.flush()
        # relasi: pencabutan terkonfirmasi (W4)
        for key, info in self.docs.items():
            target = info["t"].get("revokes")
            if target:
                last = info["versions"][-1]
                cite = last["pvs"][info["t"]["pasal"][-1][0]]
                self.db.add(Relationship(id=self.uid(), source_document_id=info["doc"].id,
                                         target_document_id=self.docs[target]["doc"].id, relation_type="REVOKES",
                                         citing_provision_version_id=cite.id, state="CONFIRMED",
                                         note="Ketentuan penutup mencabut peraturan lama",
                                         proposed_by=self.u["analyst"].id, confirmed_by=self.u["manager"].id))
                self.bump("relationships")

    def changes(self):
        """W5: semua dokumen multi-versi dibandingkan; status reviu bervariasi (termasuk lewat SLA)."""
        plan = {"ti": "MATERIAL_CONFIRMED", "apu": "MATERIAL_CONFIRMED", "konsumen": "VALIDATED", "siber": "DETECTED",
                "tatakelola": "MIXED"}
        self.material_base_pvs: set = set()
        for key, info in self.docs.items():
            vs = info["versions"]
            for i in range(1, len(vs)):
                base, new = vs[i - 1], vs[i]
                cs = ChangeSet(id=self.uid(), base_version_id=base["dv"].id, new_version_id=new["dv"].id,
                               created_by=self.u["analyst"].id, created_at=self.at(new["offset"] + 1))
                self.db.add(cs)
                self.flush()
                labels = set(base["pvs"]) | set(new["pvs"])
                last_pair = i == len(vs) - 1
                for label in sorted(labels):
                    b, n = base["pvs"].get(label), new["pvs"].get(label)
                    if b and n:
                        r = compare_texts(b.text, n.text)
                        if r["change_type"] is None:
                            continue
                        ch = Change(id=self.uid(), change_set_id=cs.id, provision_id=info["provs"][label].id, base_pv_id=b.id,
                                    new_pv_id=n.id, change_type="TEXT_MODIFIED", similarity=r["similarity"],
                                    is_material=r["is_material"], diff_html=r["diff_html"])
                    elif n:
                        ch = Change(id=self.uid(), change_set_id=cs.id, provision_id=info["provs"][label].id, new_pv_id=n.id,
                                    change_type="PROVISION_ADDED", similarity=0, is_material=True)
                    else:
                        ch = Change(id=self.uid(), change_set_id=cs.id, provision_id=info["provs"][label].id, base_pv_id=b.id,
                                    change_type="PROVISION_DELETED", similarity=0, is_material=True)
                    state = plan.get(key, "DETECTED") if last_pair else "MATERIAL_CONFIRMED"
                    if state == "MIXED":  # perubahan editorial: analis menolak flag material deterministik
                        state = "REJECTED"
                    ch.review_state = state
                    t0 = new["offset"] + 2
                    if state in ("VALIDATED", "MATERIAL_CONFIRMED", "REJECTED"):
                        ch.analyst_material = state != "REJECTED"
                        ch.semantic_type = ("EDITORIAL_ONLY" if state == "REJECTED" else
                                            "OBLIGATION_ADDED" if ch.change_type == "PROVISION_ADDED" else "DEADLINE_CHANGED")
                        ch.review_reason = ("Perubahan redaksional tanpa dampak hukum" if state == "REJECTED"
                                            else "Parameter kewajiban berubah")
                        ch.validated_by, ch.validated_at = self.u["analyst"].id, self.at(t0)
                        self.audit("analyst", "CHANGE_VALIDATED" if state != "REJECTED" else "CHANGE_REJECTED_NOT_MATERIAL",
                                   "change", ch.id, self.at(t0))
                    if state == "MATERIAL_CONFIRMED":
                        ch.confirmed_by, ch.confirmed_at = self.u["manager"].id, self.at(t0 + 1)
                        self.approval("change", ch.id, 1, "analyst", "manager", "APPROVED", self.at(t0 + 1))
                        if b and last_pair:
                            self.material_base_pvs.add(b.id)
                    self.db.add(ch)
                    self.bump(f"changes_{state}")
                self.flush()

    def applicability(self):
        self.decisions: dict[str, ApplicabilityDecision] = {}
        for key, info in self.docs.items():
            t = info["t"]
            value = t.get("decision")
            if not value:
                continue
            # keputusan atas versi terbit terakhir; untuk 'apu' keputusan atas v1 yang lalu ditandai ulang
            prev_superseded = None
            for vi, ver in enumerate(info["versions"]):
                is_last = vi == len(info["versions"]) - 1
                if not is_last and key != "apu":
                    continue
                cited = [str(ver["pvs"][p[0]].id) for p in t["pasal"] if p[1] == "OBL"][:3]
                state = "APPROVED"
                if value == "REQUIRES_FURTHER_REVIEW":
                    state = "PENDING_APPROVAL"
                if not is_last:
                    state = "SUPERSEDED"
                maker, checker = ("officer", "manager") if self.rng.random() < 0.6 else ("officer2", "manager2")
                d = ApplicabilityDecision(
                    id=self.uid(), target_version_id=ver["dv"].id, profile_id=self.profile.id, decision_value=value,
                    reason_text=t.get("decision_reason") or f"Entitas {self.profile.entity_type} termasuk subjek regulasi",
                    relied_upon_attributes={"entity_type": self.profile.entity_type, "licenses": self.profile.licenses,
                                            "business_lines": self.profile.business_lines, "profile_version": 1},
                    maker_id=self.u[maker].id, state=state, cited_provision_version_ids=cited,
                    suggested_value="NOT_APPLICABLE" if key == "pjp" else value,
                    created_at=self.at(ver["offset"] + 3), submitted_at=self.at(ver["offset"] + 4))
                if value == "REQUIRES_FURTHER_REVIEW":
                    d.review_owner_id, d.review_target_date = self.u["legal"].id, self.d(14)
                    d.legal_question = "Apakah bank termasuk pemrosesan skala besar yang wajib menunjuk pejabat PDP?"
                if not is_last:
                    prev_superseded = d
                if is_last and key == "apu":
                    self._apu_prev = prev_superseded
                if state in ("APPROVED", "SUPERSEDED"):
                    d.approver_id, d.decided_at = self.u[checker].id, self.at(ver["offset"] + 5)
                    self.approval("applicability_decision", d.id, 2, maker, checker, "APPROVED", d.decided_at)
                self.db.add(d)
                self.flush()
                self.bump(f"applicability_{state}")
                if is_last:
                    self.decisions[key] = d
                    if key == "apu":
                        self._apu_prev.superseded_by = d.id

    def obligations(self):
        """Ekstraksi memakai AI Gateway sungguhan (aturan deterministik bila tanpa LLM), lalu status dimajukan."""
        self.obs: list[Obligation] = []
        for key, info in self.docs.items():
            dec = self.decisions.get(key)
            # kewajiban pada versi lama 'apu' yang kemudian berubah material → REVIEW_REQUIRED
            targets = []
            if key == "apu":
                targets.append(("old", info["versions"][0]))
            if dec is not None and dec.state == "APPROVED" and dec.decision_value == "APPLICABLE":
                targets.append(("cur", info["versions"][-1]))
            for which, ver in targets:
                d_for = dec if which == "cur" else self.db.scalar(select(ApplicabilityDecision).where(
                    ApplicabilityDecision.target_version_id == ver["dv"].id))
                for label, kind, _ in info["t"]["pasal"]:
                    pv = ver["pvs"][label]
                    if which == "old" and pv.id not in self.material_base_pvs:
                        continue
                    if which == "cur" and key == "apu" and label == "12":
                        continue  # kewajiban Pasal 12 lama sedang ditinjau; versi baru belum diekstrak (pending)
                    res = gateway.extract_obligations(self.db, pv.text)
                    if not res.parsed or not res.parsed.obligations:
                        self.bump("provisions_without_obligation")
                        continue
                    for o in res.parsed.obligations:
                        created = self.at(ver["offset"] + 7)
                        ob = Obligation(id=self.uid(), applicability_decision_id=d_for.id, primary_citation_id=pv.id,
                                        original_text=pv.text, plain_language_summary=o.plain_language_summary,
                                        required_actions=o.required_actions, frequency=o.frequency,
                                        deadline_expression=o.deadline_expression, required_evidence=o.required_evidence,
                                        confidence=o.confidence, derived_from_ai=True, supporting_phrases=o.supporting_phrases,
                                        ai_call_id=uuid.UUID(res.log_id), model_id=res.model_id,
                                        low_confidence=o.confidence < 0.70, created_at=created)
                        roll = self.rng.random()
                        if which == "old":
                            state = "REVIEW_REQUIRED"
                        elif roll < 0.08:
                            state = "AI_DRAFT"
                        elif roll < 0.14:
                            state = "PENDING_APPROVAL"
                        else:
                            state = "ACTIVE"
                        validator, approver = ("officer", "manager") if self.rng.random() < 0.65 else ("officer2", "manager2")
                        if state != "AI_DRAFT":
                            owner = self.rng.choice(["owner", "owner_it", "owner_ops", "owner_fin"])
                            ob.owner_id, ob.validator_id = self.u[owner].id, self.u[validator].id
                            ob.low_confidence_reviewed_by = self.u[validator].id if ob.low_confidence else None
                            if self.rng.random() < 0.15:
                                ob.frequency = None  # data kosong yang disengaja (edge case)
                        if state in ("ACTIVE", "REVIEW_REQUIRED"):
                            ob.approver_id = self.u[approver].id
                            self.approval("obligation", ob.id, 3, validator, approver, "APPROVED", created + timedelta(days=2))
                        ob.state = state
                        self.db.add(ob)
                        self.flush()
                        self.audit(None, "OBLIGATION_AI_DRAFTED", "obligation", ob.id, created, after={"ai_call": res.log_id})
                        self.obs.append(ob)
                        self.bump(f"obligations_{state}")

    def controls(self):
        active = [o for o in self.obs if o.state in ("ACTIVE", "REVIEW_REQUIRED")]
        self.ctrls: list[tuple[Control, Obligation]] = []
        names = ["Prosedur", "Rekonsiliasi", "Pemantauan otomatis", "Checklist", "Eskalasi", "Reviu berkala", "Dasbor"]
        for i, ob in enumerate(active):
            if self.rng.random() < 0.2:  # ~20% sengaja tanpa kontrol → kesenjangan
                continue
            risk = Risk(id=self.uid(), obligation_id=ob.id, severity=self.rng.choice(["CRITICAL", "HIGH", "HIGH", "MEDIUM", "MEDIUM", "LOW"]),
                        title=f"Risiko ketidakpatuhan: {(ob.plain_language_summary or '')[5:60]}")
            self.db.add(risk)
            self.flush()
            no_owner = i % 11 == 5  # anomali: kontrol tanpa pemilik
            ctl = Control(id=self.uid(), risk_id=risk.id, title=f"{self.rng.choice(names)} {(ob.plain_language_summary or '')[6:50]}".strip(),
                          owner_id=None if no_owner else ob.owner_id, source_changed=ob.state == "REVIEW_REQUIRED")
            self.db.add(ctl)
            self.flush()
            self.db.add(ObligationControlMap(obligation_id=ob.id, control_id=ctl.id))
            self.ctrls.append((ctl, ob))
            self.bump("risks")
            self.bump("controls")
            self.bump("controls_without_owner", int(no_owner))
        self.flush()

    def evidence_and_assessments(self):
        self.weak: list[tuple[Control, Obligation, Assessment]] = []
        for ctl, ob in self.ctrls:
            n = self.rng.randint(0, 3)
            accepted = 0
            for k in range(n):
                state = self.rng.choices(["ACCEPTED", "SUBMITTED", "REJECTED"], [0.65, 0.2, 0.15])[0]
                content = f"BUKTI SINTETIS {ctl.title} #{k + 1}\nperiode: Q{self.rng.randint(1, 4)}\n".encode()
                key = f"evidence/{ctl.id}/synthetic_{k + 1}.txt"
                put_object(key, content, "text/plain")
                uploader = "owner" if ctl.owner_id is None else next(u for u, x in self.u.items() if x.id == ctl.owner_id)
                ev = Evidence(id=self.uid(), control_id=ctl.id, filename=f"bukti_{k + 1}.txt", object_key=key,
                              sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content),
                              description="Bukti pelaksanaan kontrol (sintetis)", state=state,
                              uploaded_by=self.u[uploader].id, uploaded_at=self.at(-self.rng.randint(20, 120)))
                if state != "SUBMITTED":
                    ev.reviewed_by, ev.reviewed_at = self.u["officer"].id, ev.uploaded_at + timedelta(days=2)
                    ev.review_rationale = "Sesuai periode dan cakupan" if state == "ACCEPTED" else "Periode tidak sesuai (PERIOD_MISMATCH)"
                self.db.add(ev)
                accepted += state == "ACCEPTED"
                self.bump(f"evidence_{state}")
            self.flush()
            if not accepted:
                continue
            design = self.rng.choices(["EFFECTIVE", "PARTIALLY_EFFECTIVE", "INEFFECTIVE"], [0.75, 0.18, 0.07])[0]
            operating = "INEFFECTIVE" if design == "INEFFECTIVE" else self.rng.choices(
                ["EFFECTIVE", "PARTIALLY_EFFECTIVE", "INEFFECTIVE"], [0.7, 0.2, 0.1])[0]
            state = self.rng.choices(["SIGNED_OFF", "PENDING_SIGNOFF", "CONCLUDED"], [0.7, 0.2, 0.1])[0]
            assessor, signer = ("officer", "manager") if self.rng.random() < 0.6 else ("officer2", "manager2")
            at = self.at(-self.rng.randint(10, 60))
            a = Assessment(id=self.uid(), control_id=ctl.id, result=operating, design_result=design, operating_result=operating,
                           design_rationale="Desain kontrol dibandingkan dengan ketentuan pasal",
                           operating_rationale=f"{self.rng.randint(15, 25)} sampel diuji",
                           state=state, assessed_by=self.u[assessor].id, assessed_at=at)
            if state != "CONCLUDED":
                a.submitted_by, a.submitted_at = self.u[assessor].id, at + timedelta(days=1)
            if state == "SIGNED_OFF":
                a.signed_off_by, a.signed_off_at = self.u[signer].id, at + timedelta(days=3)
                self.approval("assessment", a.id, 4, assessor, signer, "APPROVED", a.signed_off_at)
            self.db.add(a)
            self.flush()
            self.bump(f"assessments_{state}")
            if "INEFFECTIVE" in (design, operating) or "PARTIALLY_EFFECTIVE" in (design, operating):
                self.weak.append((ctl, ob, a))

    def findings(self):
        """≥12 temuan di seluruh status W12, termasuk anomali keterlambatan & risiko diterima lewat tinjau."""
        mapped = {ob.id for _, ob in self.ctrls}
        gaps = [o for o in self.obs if o.state == "ACTIVE" and o.id not in mapped]
        specs = []
        for ctl, ob, a in self.weak:
            sev = "HIGH" if "INEFFECTIVE" in (a.design_result, a.operating_result) else "MEDIUM"
            specs.append(dict(ob=ob, ctl=ctl, a=a, kind="CONTROL_DEFICIENCY", src="ASSESSMENT", sev=sev,
                              title=f"Kontrol '{ctl.title[:50]}' {a.operating_result}"))
        for ob in gaps:
            specs.append(dict(ob=ob, ctl=None, a=None, kind="COMPLIANCE_GAP", src="COVERAGE_GAP", sev="HIGH",
                              title=f"Kewajiban tanpa kontrol: {(ob.plain_language_summary or '')[:80]}"))
        actives = [o for o in self.obs if o.state == "ACTIVE"]
        for i in range(max(0, 12 - len(specs))):
            ob = actives[i % len(actives)]
            specs.append(dict(ob=ob, ctl=None, a=None, kind="MANUAL", src=self.rng.choice(["MANUAL", "EVIDENCE_GAP"]),
                              sev=self.rng.choice(["CRITICAL", "HIGH", "MEDIUM", "LOW"]),
                              title=self.rng.choice(["Bukti pelaporan tidak tersedia untuk periode Q2",
                                                     "Laporan disampaikan melewati tenggat",
                                                     "Prosedur belum diperbarui sesuai ketentuan terbaru",
                                                     "Pelatihan wajib belum diikuti seluruh petugas"])))
        lifecycle = ["CLOSED", "CLOSED", "CLOSED", "IN_REMEDIATION_OVERDUE", "PENDING_CLOSURE_VALIDATION", "ACTION_PLANNED",
                     "OPEN", "RISK_ACCEPTED_STALE", "REOPENED", "IN_REMEDIATION", "OPEN", "ACTION_PLANNED"]
        win = {"CRITICAL": 30, "HIGH": 60, "MEDIUM": 90, "LOW": 180}
        for i, s in enumerate(specs):
            path = lifecycle[i % len(lifecycle)]
            age = self.rng.randint(15, 140)
            created = self.at(-age)
            ob = s["ob"]
            owner_id = (s["ctl"].owner_id if s["ctl"] and s["ctl"].owner_id else ob.owner_id) or self.u["owner"].id
            owner_name = next(u for u, x in self.u.items() if x.id == owner_id)
            raiser = "officer2" if owner_name == "officer" else "officer"
            f = Finding(id=self.uid(), obligation_id=ob.id, control_id=s["ctl"].id if s["ctl"] else None,
                        assessment_id=s["a"].id if s["a"] else None, kind=s["kind"], source_type=s["src"], severity=s["sev"],
                        title=s["title"], description=f"{s['title']}. (data sintetis)", owner_id=owner_id,
                        raised_by=self.u[raiser].id, created_at=created, updated_at=created,
                        target_closure_date=(created + timedelta(days=win[s["sev"]])).date())
            self.db.add(f)
            self.flush()
            self.audit(raiser, "FINDING_AUTO_RAISED" if s["src"] != "MANUAL" else "FINDING_RAISED", "finding", f.id, created)
            self.bump("findings")
            if path in ("OPEN",):
                f.state = "OPEN"
            elif path == "RISK_ACCEPTED_STALE":
                f.state, f.risk_acceptance_rationale = "RISK_ACCEPTED", "Dalam selera risiko; biaya mitigasi tidak sebanding"
                f.risk_accepted_by, f.risk_review_date = self.u["manager"].id, self.d(-5)  # anomali: lewat tanggal tinjau
                self.approval("finding", f.id, 5, raiser, "manager", "RISK_ACCEPTED", created + timedelta(days=3))
            else:
                due_offset = -6 if path == "IN_REMEDIATION_OVERDUE" else self.rng.randint(5, 25)
                due = self.d(due_offset) if path == "IN_REMEDIATION_OVERDUE" else (created + timedelta(days=min(win[s["sev"]] - 1, 20 + age))).date()
                if path in ("ACTION_PLANNED", "IN_REMEDIATION", "IN_REMEDIATION_OVERDUE") and due < self.anchor and path != "IN_REMEDIATION_OVERDUE":
                    due = self.d(self.rng.randint(5, 20))
                act = RemediationAction(id=self.uid(), finding_id=f.id, owner_id=owner_id, created_by=self.u[raiser].id,
                                        description=self.rng.choice(["Perbarui SOP dan sosialisasikan", "Otomasi pengingat tenggat",
                                                                     "Lengkapi bukti periode berjalan", "Tambah reviu berjenjang"]),
                                        expected_outcome="Kepatuhan terhadap pasal terkait terbukti", due_date=due,
                                        original_due_date=due, created_at=created + timedelta(days=1))
                self.db.add(act)
                self.flush()
                self.bump("actions")
                if path == "ACTION_PLANNED":
                    f.state = "ACTION_PLANNED"
                    continue
                act.state, act.started_at = "IN_PROGRESS", created + timedelta(days=2)
                if path in ("IN_REMEDIATION", "IN_REMEDIATION_OVERDUE"):
                    f.state = "IN_REMEDIATION"
                    self.bump("actions_overdue", int(path == "IN_REMEDIATION_OVERDUE"))
                    continue
                content = f"BUKTI PENUTUPAN SINTETIS {f.id}".encode()
                key = f"evidence/{act.id}/penutupan.txt"
                put_object(key, content, "text/plain")
                done_at = created + timedelta(days=self.rng.randint(5, 12))
                self.db.add(Evidence(id=self.uid(), remediation_action_id=act.id, filename="penutupan.txt", object_key=key,
                                     sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content), state="ACCEPTED",
                                     description="Bukti penyelesaian tindakan", uploaded_by=owner_id, uploaded_at=done_at,
                                     reviewed_by=self.u["officer"].id if owner_name != "officer" else self.u["officer2"].id,
                                     reviewed_at=done_at + timedelta(hours=4), review_rationale="Tindakan terbukti selesai"))
                act.state, act.completed_at, act.completion_note = "DONE", done_at, "Selesai sesuai rencana"
                f.closure_submitted_by, f.closure_submitted_at = owner_id, done_at + timedelta(days=1)
                if path == "PENDING_CLOSURE_VALIDATION":
                    f.state = "PENDING_CLOSURE_VALIDATION"
                    continue
                checker = "manager" if owner_name != "manager" else "manager2"
                f.state, f.closed_by, f.closed_at = "CLOSED", self.u[checker].id, done_at + timedelta(days=3)
                f.closure_rationale = "Bukti penutupan memadai; risiko residual rendah"
                self.approval("finding", f.id, 5, owner_name, checker, "APPROVED", f.closed_at)
                self.audit(checker, "FINDING_CLOSED", "finding", f.id, f.closed_at)
                if path == "REOPENED":
                    f.state, f.reopened_count = "IN_REMEDIATION", 1
                    self.audit(checker, "FINDING_REOPENED", "finding", f.id, f.closed_at + timedelta(days=10),
                               after={"reason": "Insiden serupa terulang"})
        self.flush()
        for st, n in self.db.execute(text("SELECT state, count(*) FROM compliance.finding GROUP BY state")).all():
            self.bump(f"findings_{st}", n)

    def reports(self):
        from app.compliance.common import user_names
        from app.compliance.reporting import build_report_payload
        names = user_names(self.db)
        payload = build_report_payload(self.db, "Laporan Postur Kepatuhan Triwulan III", self.d(-120), self.d(-30), names)
        old = ComplianceReport(id=self.uid(), title="Laporan Postur Kepatuhan Triwulan III", payload=payload, state="SUPERSEDED",
                               created_by=self.u["officer"].id, generated_by=self.u["officer"].id,
                               created_at=self.at(-28), submitted_at=self.at(-27), issued_by=self.u["manager"].id,
                               issued_at=self.at(-26), disclaimer_version=payload["disclaimer_version"])
        self.db.add(old)
        self.flush()
        self.approval("compliance_report", old.id, 6, "officer", "manager", "APPROVED", old.issued_at)
        draft = ComplianceReport(id=self.uid(), title="Laporan Postur Kepatuhan Oktober (draf)", payload=payload,
                                 state="DRAFT", created_by=self.u["officer2"].id, generated_by=self.u["officer2"].id,
                                 created_at=self.at(-1), disclaimer_version=payload["disclaimer_version"])
        self.db.add(draft)
        self.bump("reports", 2)

    def run(self):
        self.db.execute(text("SET LOCAL rcip.seeding = 'on'"))
        self.users()
        self.corpus()
        self.changes()
        self.applicability()
        self.obligations()
        self.controls()
        self.evidence_and_assessments()
        self.findings()
        self.reports()
        self.flush()
        return self.stats


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("rcip.storage").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--anchor", type=date.fromisoformat, default=date.today(), help="Tanggal acuan 'hari ini' (YYYY-MM-DD)")
    args = ap.parse_args()
    db = SessionLocal()
    try:
        if db.scalar(select(DocumentVersion.id).where(DocumentVersion.origin_url == MARKER).limit(1)):
            log.warning("Data sintetis sudah ada; generator tidak dijalankan ulang (gunakan DB baru untuk generate ulang).")
            return
        if db.scalar(select(Document.id).limit(1)):
            raise SystemExit("Korpus tidak kosong (mis. sudah menjalankan seed.run). Generator butuh DB kosong hasil "
                             "'alembic upgrade head'. Lihat docs/synthetic_data.md bagian 'Menjalankan'.")
        stats = Gen(db, args.seed, args.anchor).run()
        db.commit()
        log.info("GENERATE OK (seed=%s, anchor=%s)", args.seed, args.anchor)
        for k in sorted(stats):
            log.info("  %-34s %s", k, stats[k])
        log.info("Jalankan: python -m seed.validate")
    except Exception:
        db.rollback()
        log.exception("GENERATE FAILED")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
