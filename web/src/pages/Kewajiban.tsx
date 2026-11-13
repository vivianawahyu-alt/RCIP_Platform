import { useState } from "react";
import { api } from "../api";
import type { Obligation, User } from "../types";
import type { Ctx } from "../ui";
import { AiBadge, Cite, Empty, Flow, PageHead, Status, can, useAction, useLoad } from "../ui";
import { CitationPicker } from "../CitationPicker";
import type { Cite as Cited } from "../CitationPicker";

const STEPS: [string, string][] = [["AI_DRAFT", "Draf AI"], ["IN_VALIDATION", "Validasi"], ["PENDING_APPROVAL", "Persetujuan"], ["ACTIVE", "Aktif"]];
const FILTERS = ["Semua", "AI_DRAFT", "PENDING_LEGAL", "PENDING_APPROVAL", "ACTIVE", "REVIEW_REQUIRED"];

export function Kewajiban({ ctx }: { ctx: Ctx }) {
  const [obs, reload] = useLoad<Obligation[]>(() => api("/compliance/obligations"), [], ctx.notify);
  const [users] = useLoad<User[]>(() => api("/users"), [], ctx.notify);
  const [owner, setOwner] = useState<Record<string, string>>({});
  const [summary, setSummary] = useState<Record<string, string>>({});
  const [reason, setReason] = useState<Record<string, string>>({});
  const [ack, setAck] = useState<Record<string, boolean>>({});
  const [why, setWhy] = useState<Record<string, boolean>>({});
  const [filter, setFilter] = useState("Semua");
  const [q, setQ] = useState<Record<string, string>>({});
  const [lw, setLw] = useState<Record<string, string>>({});
  const [cites, setCites] = useState<Record<string, Cited[]>>({});
  const [trace, setTrace] = useState<any>(null);
  const { run, busy } = useAction(ctx.notify, reload);
  const officer = can(ctx.me.role, "obligation_validate"), manager = can(ctx.me.role, "obligation_approve");
  const legal = ctx.me.role === "LEGAL_REVIEWER";
  const owners = (users || []).filter(u => !["SYSTEM_ADMINISTRATOR", "INTERNAL_AUDITOR", "EXECUTIVE"].includes(u.role));
  const defOwner = owners.find(u => u.username === "owner")?.id || "";
  const shown = (obs || []).filter(o => filter === "Semua" || o.state === filter);

  return <>
    <PageHead crumbs="Kepatuhan" title="Kewajiban" intro="AI hanya menyusun draf. Pejabat Kepatuhan memvalidasi dan menetapkan pemilik; Manajer Kepatuhan menyetujui. Draf AI tidak pernah dihitung atau dipetakan." />
    <div className="tabs">{FILTERS.map(f => <button key={f} className={f === filter ? "on" : ""} onClick={() => setFilter(f)}>
      {f === "Semua" ? "Semua" : <Status s={f} />} <span className="muted small">{(obs || []).filter(o => f === "Semua" || o.state === f).length}</span></button>)}</div>
    {shown.length ? shown.map(o => <section className="panel" key={o.id}>
      <div className="between">
        <div className="row"><Cite c={o.citation} onOpen={ctx.openCite} />{o.derived_from_ai && o.state === "AI_DRAFT" && <AiBadge />}<Status s={o.state} /></div>
        <span className="small muted">{o.confidence != null ? `keyakinan ekstraksi ${Math.round(o.confidence * 100)}%` : ""}</span>
      </div>
      {STEPS.some(s => s[0] === o.state) && <div style={{ marginTop: 12 }}><Flow steps={STEPS} now={o.state} /></div>}
      <h3 style={{ fontSize: 19, margin: "6px 0" }}>{o.summary || "Belum ada ringkasan."}</h3>
      {o.low_confidence && ["AI_DRAFT", "IN_VALIDATION"].includes(o.state) && <span className="badge amber">Keyakinan rendah · wajib ditinjau manual</span>}
      {o.state === "REVIEW_REQUIRED" && <div className="notice error" style={{ marginTop: 8 }}><span>Pasal sumber berubah secara material. Kewajiban tetap tercatat sampai ditinjau ulang; buka kembali untuk memvalidasi terhadap versi terbaru.</span></div>}
      {o.reopen_reason && o.state !== "ACTIVE" && <p className="small">Dibuka kembali: {o.reopen_reason}</p>}
      {o.legal_question && <p className="small" style={{ whiteSpace: "pre-line" }}>Pertanyaan hukum: {o.legal_question}{o.legal_answer && <><br />Posisi hukum{o.legal_reviewer ? ` (${o.legal_reviewer})` : ""}: {o.legal_answer}</>}</p>}
      <div className="row small muted">{o.deadline && <span>Tenggat: {o.deadline}</span>}{o.frequency && <span>Frekuensi: {o.frequency}</span>}
        <span>Pemilik: {o.owner || "belum ditetapkan"}</span>{o.validator && <span>Validator: {o.validator}</span>}{o.approver && <span>Penyetuju: {o.approver}</span>}</div>

      {officer && ["AI_DRAFT", "IN_VALIDATION"].includes(o.state) && <div className="decision">
        <h4>Validasi draf</h4>
        <div className="form">
          <label className="field">Ringkasan dalam bahasa operasional<textarea defaultValue={o.summary} onChange={e => setSummary({ ...summary, [o.id]: e.target.value })} /></label>
          {o.low_confidence && <label className="row small" style={{ gap: 6 }}><input type="checkbox" checked={!!ack[o.id]} onChange={e => setAck({ ...ack, [o.id]: e.target.checked })} />Saya telah membandingkan draf ini dengan teks pasal secara manual (keyakinan AI di bawah ambang)</label>}
          <label className="field">Pemilik kewajiban<select value={owner[o.id] ?? defOwner} onChange={e => setOwner({ ...owner, [o.id]: e.target.value })}>{owners.map(u => <option key={u.id} value={u.id}>{u.username}</option>)}</select></label>
          <div><button className="btn primary" onClick={() => run(() => api(`/compliance/obligations/${o.id}/validate`, { body: { owner_id: owner[o.id] ?? defOwner, plain_language_summary: summary[o.id] || undefined, low_confidence_reviewed: !!ack[o.id] } }), "Kewajiban divalidasi dan diajukan ke Manajer Kepatuhan.")} disabled={busy || (o.low_confidence && !ack[o.id])}>Validasi & ajukan persetujuan</button></div>
        </div>
      </div>}
      {officer && ["AI_DRAFT", "IN_VALIDATION"].includes(o.state) && <div className="decision">
        <h4>Penafsiran diperdebatkan?</h4>
        <div className="row"><input className="grow" value={q[o.id] || ""} onChange={e => setQ({ ...q, [o.id]: e.target.value })} placeholder="Tulis pertanyaan hukum untuk Peninjau Hukum" />
          <button className="btn" disabled={busy || !(q[o.id] || "").trim()} onClick={() => run(() => api(`/compliance/obligations/${o.id}/escalate`, { body: { question: q[o.id] } }), "Diteruskan ke Peninjau Hukum.")}>Eskalasi</button></div>
      </div>}
      {legal && o.state === "PENDING_LEGAL" && <div className="decision"><h4>Posisi hukum</h4>
        <div className="row"><input className="grow" value={lw[o.id] || ""} onChange={e => setLw({ ...lw, [o.id]: e.target.value })} placeholder="Posisi hukum" /></div>
        <CitationPicker value={cites[o.id] || []} onChange={v => setCites({ ...cites, [o.id]: v })} />
        <div className="row" style={{ marginTop: 8 }}>
          <button className="btn primary" disabled={busy || !(lw[o.id] || "").trim() || !(cites[o.id] || []).length} onClick={() => run(() => api(`/compliance/obligations/${o.id}/legal-answer`, { body: { answer: lw[o.id], citation_provision_version_ids: (cites[o.id] || []).map(x => x.id) } }), "Posisi hukum tercatat; kewajiban kembali ke Pejabat Kepatuhan untuk divalidasi.")}>Kirim</button></div></div>}
      {manager && o.state === "PENDING_APPROVAL" && <div className="decision">
        <h4>Keputusan persetujuan (titik kendali 3)</h4>
        <p className="small muted" style={{ marginTop: 0 }}>Anda tidak dapat menyetujui kewajiban yang Anda validasi sendiri.</p>
        <label className="field">Alasan (wajib bila dikembalikan)<input value={reason[o.id] || ""} onChange={e => setReason({ ...reason, [o.id]: e.target.value })} /></label>
        <div className="row" style={{ marginTop: 10 }}>
          <button className="btn primary" disabled={busy} onClick={() => run(() => api(`/compliance/obligations/${o.id}/decision`, { body: { outcome: "APPROVED", reason: reason[o.id] } }), "Kewajiban disetujui dan kini aktif.")}>Setujui</button>
          <button className="btn danger" disabled={busy || !reason[o.id]} onClick={() => run(() => api(`/compliance/obligations/${o.id}/decision`, { body: { outcome: "REJECTED", reason: reason[o.id] } }), "Kewajiban dikembalikan ke validator.")}>Kembalikan</button>
        </div>
      </div>}
      {officer && o.state === "REVIEW_REQUIRED" && <ReopenBox o={o} ctx={ctx} onDone={reload} />}
      <div className="row" style={{ marginTop: 10 }}>
        {o.derived_from_ai && <button className="btn ghost" onClick={() => setWhy({ ...why, [o.id]: !why[o.id] })}>{why[o.id] ? "Sembunyikan penjelasan AI" : "Mengapa AI mengusulkan ini?"}</button>}
        <button className="btn ghost" onClick={() => trace?.obligation?.id === o.id ? setTrace(null) : api(`/compliance/trace/obligations/${o.id}`).then(setTrace).catch(e => ctx.notify("error", e.message))}>
          {trace?.obligation?.id === o.id ? "Sembunyikan rantai" : "Telusuri rantai kepatuhan"}</button>
      </div>
      {why[o.id] && <Explain o={o} />}
      {trace?.obligation?.id === o.id && <TraceChain t={trace} />}
    </section>) : <Empty>{filter === "Semua" ? "Belum ada kewajiban. Ekstrak dari pasal yang sudah terbit di Korpus & pasal." : "Tidak ada kewajiban dengan status ini."}</Empty>}
  </>;
}

export function TraceChain({ t }: { t: any }) {
  return <ol className="timeline" style={{ marginTop: 10 }}>
    <li><b>Pasal</b> {t.citation.document.canonical_number} {t.citation.number_label}, versi {t.citation.document_version.version_number} ({t.citation.document_version.state})</li>
    <li><b>Kewajiban</b> {t.obligation.state} · pemilik {t.obligation.owner || "—"} · validator {t.obligation.validator || "—"} · penyetuju {t.obligation.approver || "—"}</li>
    <li><b>Persetujuan</b> {t.approvals.length ? t.approvals.map((a: any) => `${a.outcome} oleh ${a.checker}`).join("; ") : "belum ada"}</li>
    <li><b>Kontrol</b> {t.controls.length ? t.controls.map((c: any) => `${c.title} (bukti diterima ${c.evidence.accepted}/${c.evidence.total}; asesmen ${c.latest_assessment ? `${c.latest_assessment.operating_result}, ${c.latest_assessment.state}` : "belum"})`).join("; ") : "belum dipetakan"}</li>
    <li><b>Temuan</b> {t.findings.length ? t.findings.map((f: any) => `${f.title} — ${f.state} (${f.actions.length} tindakan)`).join("; ") : "tidak ada"}</li>
  </ol>;
}

function highlight(text: string, phrases: string[]) {
  const norm = (x: string) => x.replace(/\s+/g, " ").trim();
  let parts: (string | JSX.Element)[] = [norm(text)];
  phrases.forEach((ph, k) => {
    const p = norm(ph);
    parts = parts.flatMap(seg => typeof seg !== "string" || !p ? [seg] : seg.split(p).flatMap((piece, i, arr) => i < arr.length - 1 ? [piece, <mark key={`${k}-${i}`}>{p}</mark>] : [piece]));
  });
  return parts;
}

function Explain({ o }: { o: Obligation }) {
  return <div className="action-card" style={{ marginTop: 10 }}>
    <b>Dasar draf AI</b>
    <p className="small muted" style={{ margin: "4px 0" }}>Frasa yang disorot adalah kutipan verbatim yang dipakai model; draf ditolak otomatis bila frasa tidak ditemukan di teks pasal (grounding).</p>
    <div className="verbatim" style={{ fontSize: 15 }}>{highlight(o.original_text || "", o.supporting_phrases || [])}</div>
    <div className="row small">
      <span>Model: <b>{o.ai?.model_id || o.model_id || "—"}</b></span><span>Templat: {o.ai?.template || "—"}</span>
      <span>Skema: {o.ai ? (o.ai.schema_valid ? "valid" : "tidak valid") : "—"}</span><span>Grounding: {o.ai ? (o.ai.grounding_passed ? "lolos" : "gagal") : "—"}</span>
      <span>Keyakinan: {o.confidence != null ? `${Math.round(o.confidence * 100)}%` : "—"}</span>
    </div>
    {!!o.required_actions?.length && <p className="small" style={{ marginBottom: 0 }}>Tindakan yang diekstrak: {o.required_actions.join("; ")}</p>}
  </div>;
}

function ReopenBox({ o, ctx, onDone }: { o: Obligation; ctx: Ctx; onDone: () => void }) {
  const [reason, setReason] = useState(""), [target, setTarget] = useState<{ id: string; label: string } | null>(null);
  const { run, busy } = useAction(ctx.notify, onDone);
  const find = async () => {
    const docs = await api<any[]>("/corpus/documents");
    const d = docs.find(x => x.canonical_number === o.citation.canonical_number);
    const v = d?.versions.filter((x: any) => x.state === "PUBLISHED").slice(-1)[0];
    if (!v) return;
    const provs = await api<any[]>(`/corpus/versions/${v.id}/provisions`);
    const p = provs.find(x => x.number_label === o.citation.number_label);
    if (p && p.provision_version_id !== o.citation.provision_version_id) setTarget({ id: p.provision_version_id, label: `${o.citation.number_label} versi ${v.version_number}` });
  };
  return <div className="decision"><h4>Tinjau ulang kewajiban</h4>
    <div className="form">
      <label className="field">Alasan<input value={reason} onChange={e => setReason(e.target.value)} placeholder="mis. tenggat berubah 24 → 12 jam" /></label>
      <div className="row">{target ? <span className="small">Sitasi akan diarahkan ke <b>{target.label}</b></span> : <button className="btn sm" onClick={() => find().catch(e => ctx.notify("error", e.message))}>Cari pasal yang sama di versi terbaru</button>}</div>
      <div><button className="btn primary" disabled={busy || !reason} onClick={() => run(() => api(`/compliance/obligations/${o.id}/reopen`, { body: { reason, new_provision_version_id: target?.id } }), "Kewajiban dibuka kembali untuk validasi ulang.")}>Buka kembali untuk validasi</button></div>
    </div></div>;
}