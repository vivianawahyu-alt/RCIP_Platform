import { useState } from "react";
import type { ChangeEvent } from "react";
import { api } from "../api";
import type { Action, Finding, Obligation, User } from "../types";
import type { Ctx } from "../ui";
import { Cite, Empty, Flow, PageHead, SEVERITIES, Sev, Status, can, fmtDate, fmtTime, inDays, useAction, useLoad } from "../ui";
import { EvidenceRow } from "./Kontrol";

const STEPS: [string, string][] = [["OPEN", "Terbuka"], ["ACTION_PLANNED", "Tindakan direncanakan"], ["IN_REMEDIATION", "Remediasi"],
  ["PENDING_CLOSURE_VALIDATION", "Validasi penutupan"], ["CLOSED", "Ditutup"]];
const SOURCE: Record<string, string> = { COVERAGE_GAP: "Kesenjangan cakupan", ASSESSMENT: "Hasil asesmen", EVIDENCE_GAP: "Bukti tidak tersedia", MANUAL: "Manual" };
const WINDOW: Record<string, number> = { CRITICAL: 30, HIGH: 60, MEDIUM: 90, LOW: 180 };

export function Temuan({ ctx, selected }: { ctx: Ctx; selected?: string }) {
  const [rows, reload] = useLoad<Finding[]>(() => api("/compliance/findings"), [], ctx.notify);
  const [sev, setSev] = useState<string>("ALL");
  const [state, setState] = useState<string>("TERBUKA");
  const [showNew, setShowNew] = useState(false);
  const { run, busy } = useAction(ctx.notify, reload);
  const all = rows || [];
  const openish = (f: Finding) => !["CLOSED", "RISK_ACCEPTED"].includes(f.state);
  const late = (f: Finding) => f.overdue || f.overdue_actions > 0;
  const shown = all.filter(f => (sev === "ALL" || (sev === "LATE" ? late(f) : f.severity === sev))
    && (state === "SEMUA" || (state === "TERBUKA" ? openish(f) : f.state === state)));
  const sel = selected || shown[0]?.id;
  const count = (fn: (f: Finding) => boolean) => all.filter(f => openish(f) && fn(f)).length;

  return <>
    <PageHead crumbs="Temuan & Remediasi" title="Register temuan" intro="Setiap temuan tertaut ke kewajiban, memiliki pemilik dan jendela remediasi sesuai tingkat keparahan. Penutupan divalidasi Manajer Kepatuhan yang bukan pemilik tindakan (titik kendali 5).">
      {can(ctx.me.role, "gap_scan") && <button className="btn" disabled={busy} onClick={() => run(async () => { const r = await api("/compliance/gaps/scan", { body: {} }); ctx.notify("ok", `${r.findings_created.length} temuan kesenjangan baru dibuat.`); })}>Pindai kesenjangan</button>}
      {can(ctx.me.role, "finding_create") && <button className="btn primary" onClick={() => setShowNew(!showNew)}>{showNew ? "Batal" : "Catat temuan"}</button>}
    </PageHead>
    {showNew && <NewFinding ctx={ctx} onDone={id => { setShowNew(false); reload(); ctx.go(`temuan/${id}`); }} />}
    <div className="sevbar" role="group" aria-label="Saring menurut tingkat keparahan">
      <button className={sev === "ALL" ? "on" : ""} onClick={() => setSev("ALL")}><b>{count(() => true)}</b><span>Semua terbuka</span></button>
      {SEVERITIES.map(s => <button key={s} className={sev === s ? "on" : ""} onClick={() => setSev(s)}><b>{count(f => f.severity === s)}</b><Sev s={s} /></button>)}
      <button className={sev === "LATE" ? "on" : ""} onClick={() => setSev("LATE")}><b>{count(late)}</b><span>Lewat tenggat</span></button>
    </div>
    <div className="tabs">{[["TERBUKA", "Terbuka"], ["PENDING_CLOSURE_VALIDATION", "Menunggu validasi"], ["CLOSED", "Ditutup"], ["RISK_ACCEPTED", "Risiko diterima"], ["SEMUA", "Semua"]].map(([k, l]) =>
      <button key={k} className={state === k ? "on" : ""} onClick={() => setState(k)}>{l}</button>)}</div>
    <div className="cols">
      <section className="panel">
        {shown.length ? <div className="tablewrap"><table className="data"><thead><tr><th>Temuan</th><th>Tingkat</th><th>Pemilik</th><th>Target</th><th>Status</th></tr></thead>
          <tbody>{shown.map(f => <tr key={f.id} className={`clickable ${f.id === sel ? "selected" : ""}`} onClick={() => ctx.go(`temuan/${f.id}`)}>
            <td><b>{f.title}</b><div className="small muted">{SOURCE[f.source_type] || f.source_type} · {f.action_count ?? f.actions.length} tindakan · {f.age_days} hari</div></td>
            <td><Sev s={f.severity} /></td><td>{f.owner || "—"}</td>
            <td style={f.overdue ? { color: "var(--red)", fontWeight: 600 } : undefined}>{fmtDate(f.target_closure_date)}{f.overdue_actions > 0 && <div className="small" style={{ color: "var(--red)" }}>{f.overdue_actions} tindakan terlambat</div>}</td>
            <td><Status s={f.state} /></td></tr>)}</tbody></table></div>
          : <Empty>{all.length ? "Tidak ada temuan untuk saringan ini." : "Belum ada temuan. Jalankan Pindai kesenjangan setelah ada kewajiban aktif."}</Empty>}
      </section>
      <aside className="detail">{sel ? <FindingDetail key={sel} id={sel} ctx={ctx} onChange={reload} /> : <Empty>Pilih temuan untuk melihat rencana remediasinya.</Empty>}</aside>
    </div>
  </>;
}

function NewFinding({ ctx, onDone }: { ctx: Ctx; onDone: (id: string) => void }) {
  const [obs] = useLoad<Obligation[]>(() => api("/compliance/obligations"), [], ctx.notify);
  const [users] = useLoad<User[]>(() => api("/users"), [], ctx.notify);
  const [f, setF] = useState({ obligation_id: "", title: "", description: "", severity: "MEDIUM", owner_id: "", target_closure_date: inDays(30) });
  const { run, busy } = useAction(ctx.notify);
  return <section className="panel"><h2>Catat temuan manual</h2><div className="form">
    <label className="field">Kewajiban terkait<select value={f.obligation_id} onChange={e => setF({ ...f, obligation_id: e.target.value })}><option value="">Pilih kewajiban</option>{(obs || []).filter(o => !["AI_DRAFT", "IN_VALIDATION"].includes(o.state)).map(o => <option key={o.id} value={o.id}>{o.citation.number_label} · {o.summary?.slice(0, 80)}</option>)}</select></label>
    <label className="field">Judul<input value={f.title} onChange={e => setF({ ...f, title: e.target.value })} /></label>
    <label className="field">Uraian<textarea value={f.description} onChange={e => setF({ ...f, description: e.target.value })} /></label>
    <div className="form-2">
      <label className="field">Tingkat keparahan<select value={f.severity} onChange={e => setF({ ...f, severity: e.target.value, target_closure_date: inDays(Math.min(30, WINDOW[e.target.value])) })}>{SEVERITIES.map(s => <option key={s}>{s}</option>)}</select><span className="hint">Jendela maksimum {WINDOW[f.severity]} hari</span></label>
      <label className="field">Target penutupan<input type="date" value={f.target_closure_date} max={inDays(WINDOW[f.severity])} onChange={e => setF({ ...f, target_closure_date: e.target.value })} /></label>
    </div>
    <label className="field">Pemilik<select value={f.owner_id} onChange={e => setF({ ...f, owner_id: e.target.value })}><option value="">Pilih pemilik</option>{(users || []).filter(u => ["BUSINESS_CONTROL_OWNER", "COMPLIANCE_OFFICER"].includes(u.role)).map(u => <option key={u.id} value={u.id}>{u.username}</option>)}</select></label>
    <div><button className="btn primary" disabled={busy || !f.obligation_id || !f.title || !f.description || !f.owner_id} onClick={() => run(async () => { const r = await api("/compliance/findings", { body: f }); onDone(r.id); }, "Temuan dicatat.")}>Catat temuan</button></div>
  </div></section>;
}

function FindingDetail({ id, ctx, onChange }: { id: string; ctx: Ctx; onChange: () => void }) {
  const [f, reload] = useLoad<Finding>(() => api(`/compliance/findings/${id}`), [id], ctx.notify);
  const [users] = useLoad<User[]>(() => api("/users"), [], ctx.notify);
  const [na, setNa] = useState({ description: "", due_date: inDays(14), owner_id: "", expected_outcome: "" });
  const [dec, setDec] = useState({ rationale: "", new_due_date: inDays(14), late_justification: "" });
  const [risk, setRisk] = useState({ rationale: "", review_date: inDays(90) });
  const [reopenWhy, setReopenWhy] = useState("");
  const refresh = () => { reload(); onChange(); };
  const { run, busy } = useAction(ctx.notify, refresh);
  if (!f) return <div className="panel">Memuat…</div>;
  const role = ctx.me.role, me = ctx.me.user_id;
  const officer = role === "COMPLIANCE_OFFICER", manager = role === "COMPLIANCE_MANAGER";
  const canPlan = can(role, "action_create") && !["CLOSED", "RISK_ACCEPTED", "PENDING_CLOSURE_VALIDATION"].includes(f.state);
  const live = f.actions.filter(a => a.state !== "CANCELLED");
  const allDone = live.length > 0 && live.every(a => a.state === "DONE");
  const canSubmit = can(role, "closure_propose") && ["IN_REMEDIATION", "ACTION_PLANNED"].includes(f.state) && allDone;
  const ownsAction = f.actions.some(a => a.owner_id === me);
  const late = f.target_closure_date && f.target_closure_date < new Date().toISOString().slice(0, 10);
  const people = (users || []).filter(u => ["BUSINESS_CONTROL_OWNER", "COMPLIANCE_OFFICER", "COMPLIANCE_MANAGER"].includes(u.role));
  const flowNow = f.state === "RISK_ACCEPTED" ? "OPEN" : f.state;

  return <section className="panel">
    <div className="between"><Sev s={f.severity} /><Status s={f.state} /></div>
    <h2 style={{ marginTop: 6 }}>{f.title}</h2>
    <p className="small muted" style={{ marginTop: 4 }}>{SOURCE[f.source_type]} · dicatat {f.raised_by || "sistem"} {fmtDate(f.created_at)} · pemilik {f.owner || "—"} · target {fmtDate(f.target_closure_date)}{f.reopened_count ? ` · dibuka kembali ${f.reopened_count}×` : ""}</p>
    {f.state !== "RISK_ACCEPTED" && <Flow steps={STEPS} now={flowNow} />}
    <p>{f.description}</p>
    {f.obligation && <div className="row small"><span className="muted">Kewajiban:</span><Cite c={f.obligation.citation} onOpen={ctx.openCite} /><span>{f.obligation.summary}</span></div>}
    {f.control && <p className="small"><span className="muted">Kontrol:</span> <button className="btn ghost sm" onClick={() => ctx.go(`kontrol/${f.control!.id}`)}>{f.control.title}</button></p>}
    {f.risk_acceptance && <div className="notice ok"><span>Risiko diterima oleh {f.risk_acceptance.accepted_by}: {f.risk_acceptance.rationale}. Tinjau ulang {fmtDate(f.risk_acceptance.review_date)}. Dihitung sebagai kesenjangan yang diterima, bukan terselesaikan.</span></div>}

    <h3 style={{ fontSize: 17, marginTop: 16 }}>Rencana remediasi</h3>
    {f.actions.length ? f.actions.map(a => <ActionCard key={a.id} a={a} ctx={ctx} onDone={refresh} />) : <p className="muted small">Belum ada tindakan.</p>}

    {canPlan && <div className="form" style={{ marginTop: 12 }}>
      <label className="field">Tindakan baru<input value={na.description} onChange={e => setNa({ ...na, description: e.target.value })} placeholder="mis. Pasang pengingat otomatis H-2 pelaporan" /></label>
      <div className="form-2">
        <label className="field">Pemilik tindakan<select value={na.owner_id} onChange={e => setNa({ ...na, owner_id: e.target.value })}><option value="">{f.owner ? `Pemilik temuan (${f.owner})` : "Saya"}</option>{people.map(u => <option key={u.id} value={u.id}>{u.username}</option>)}</select></label>
        <label className="field">Jatuh tempo<input type="date" value={na.due_date} max={inDays(WINDOW[f.severity])} onChange={e => setNa({ ...na, due_date: e.target.value })} /></label>
      </div>
      <label className="field">Hasil yang diharapkan<input value={na.expected_outcome} onChange={e => setNa({ ...na, expected_outcome: e.target.value })} /></label>
      <div><button className="btn primary" disabled={busy || !na.description} onClick={() => run(async () => { await api(`/compliance/findings/${f.id}/remediation`, { body: { ...na, owner_id: na.owner_id || undefined } }); setNa({ description: "", due_date: inDays(14), owner_id: "", expected_outcome: "" }); }, "Tindakan remediasi ditambahkan.")}>Tambah tindakan</button></div>
    </div>}

    {canSubmit && <div className="decision"><h4>Semua tindakan selesai</h4><p className="small" style={{ marginTop: 0 }}>Ajukan penutupan agar divalidasi Manajer Kepatuhan.</p>
      <button className="btn primary" disabled={busy} onClick={() => run(() => api(`/compliance/findings/${f.id}/submit-closure`, { method: "POST" }), "Penutupan diajukan.")}>Ajukan penutupan</button></div>}

    {manager && f.state === "PENDING_CLOSURE_VALIDATION" && <div className="decision">
      <h4>Validasi penutupan (titik kendali 5)</h4>
      <p className="small" style={{ marginTop: 0 }}>Diajukan oleh {f.closure.submitted_by} {fmtTime(f.closure.submitted_at)}.</p>
      {(ownsAction || f.raised_by_id === me) && <p className="small" style={{ color: "var(--red)" }}>Anda pemilik tindakan atau pencatat temuan ini, sehingga tidak dapat memvalidasinya. Minta Manajer lain.</p>}
      <div className="form">
        <label className="field">Rasional validasi<textarea value={dec.rationale} onChange={e => setDec({ ...dec, rationale: e.target.value })} /></label>
        {late && <label className="field">Justifikasi keterlambatan<input value={dec.late_justification} onChange={e => setDec({ ...dec, late_justification: e.target.value })} /></label>}
        <label className="field">Jatuh tempo baru (bila ditolak)<input type="date" value={dec.new_due_date} onChange={e => setDec({ ...dec, new_due_date: e.target.value })} /></label>
        <div className="row">
          <button className="btn primary" disabled={busy || !dec.rationale} onClick={() => run(() => api(`/compliance/findings/${f.id}/close`, { body: { outcome: "APPROVED", rationale: dec.rationale, late_justification: dec.late_justification || undefined } }), "Temuan ditutup.")}>Tutup temuan</button>
          <button className="btn danger" disabled={busy || !dec.rationale} onClick={() => run(() => api(`/compliance/findings/${f.id}/close`, { body: { outcome: "REJECTED", rationale: dec.rationale, new_due_date: dec.new_due_date } }), "Penutupan ditolak; temuan kembali ke remediasi.")}>Tolak penutupan</button>
        </div>
      </div>
    </div>}

    {manager && ["OPEN", "ACTION_PLANNED"].includes(f.state) && <details style={{ marginTop: 14 }}><summary className="small" style={{ cursor: "pointer", fontWeight: 600 }}>Terima risiko alih-alih remediasi</summary>
      <div className="form" style={{ marginTop: 8 }}>
        <label className="field">Rasional penerimaan<textarea value={risk.rationale} onChange={e => setRisk({ ...risk, rationale: e.target.value })} /></label>
        <label className="field">Tanggal tinjau ulang<input type="date" value={risk.review_date} onChange={e => setRisk({ ...risk, review_date: e.target.value })} /></label>
        <div><button className="btn" disabled={busy || !risk.rationale} onClick={() => run(() => api(`/compliance/findings/${f.id}/accept-risk`, { body: risk }), "Risiko diterima dan tercatat.")}>Terima risiko</button></div>
      </div></details>}

    {manager && f.state === "CLOSED" && <div className="row" style={{ marginTop: 14 }}>
      <input className="grow" value={reopenWhy} onChange={e => setReopenWhy(e.target.value)} placeholder="Alasan membuka kembali" />
      <button className="btn" disabled={busy || !reopenWhy} onClick={() => run(() => api(`/compliance/findings/${f.id}/reopen`, { body: { reason: reopenWhy } }), "Temuan dibuka kembali; catatan penutupan lama tetap tersimpan.")}>Buka kembali</button></div>}

    {f.closure.closed_by && <p className="small" style={{ marginTop: 12 }}>Ditutup oleh <b>{f.closure.closed_by}</b> {fmtTime(f.closure.closed_at)}: {f.closure.rationale}</p>}
    {!!f.approvals?.length && <><h3 style={{ fontSize: 17, marginTop: 16 }}>Keputusan maker-checker</h3><ul className="list">{f.approvals.map((a, i) => <li key={i} className="small"><b>{a.outcome}</b> oleh {a.checker} (maker {a.maker}) · {fmtTime(a.decided_at)}{a.reason && <div className="muted">{a.reason}</div>}</li>)}</ul></>}
    <h3 style={{ fontSize: 17, marginTop: 16 }}>Jejak audit</h3>
    <ol className="timeline">{(f.timeline || []).map((t, i) => <li key={i}><b>{t.action}</b> — {t.actor}<time>{fmtTime(t.occurred_at)}</time></li>)}</ol>
  </section>;
}

function ActionCard({ a, ctx, onDone }: { a: Action; ctx: Ctx; onDone: () => void }) {
  const [desc, setDesc] = useState(""), [note, setNote] = useState(""), [ext, setExt] = useState({ new_due_date: "", reason: "" });
  const { run, busy } = useAction(ctx.notify, onDone);
  const role = ctx.me.role;
  const actor = role === "COMPLIANCE_OFFICER" || (role === "BUSINESS_CONTROL_OWNER" && a.owner_id === ctx.me.user_id);
  const liveA = ["OPEN", "IN_PROGRESS"].includes(a.state);
  const accepted = a.evidence.some(e => e.state === "ACCEPTED");
  const upload = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return; const form = new FormData(); form.append("file", f); form.append("description", desc);
    run(async () => { await api(`/compliance/actions/${a.id}/evidence`, { form }); setDesc(""); }, "Bukti penutupan diunggah; menunggu tinjauan Pejabat Kepatuhan."); e.target.value = "";
  };
  return <div className="action-card">
    <div className="between"><b>{a.description}</b><Status s={a.state} /></div>
    <div className="small muted">Pemilik {a.owner} · jatuh tempo <span style={a.overdue ? { color: "var(--red)", fontWeight: 700 } : undefined}>{fmtDate(a.due_date)}{a.overdue ? " (terlambat)" : ""}</span>
      {a.original_due_date !== a.due_date && <> · semula {fmtDate(a.original_due_date)}</>}</div>
    {a.expected_outcome && <div className="small">Hasil diharapkan: {a.expected_outcome}</div>}
    {a.extension_history.map((h, i) => <div key={i} className="small muted">Diperpanjang {fmtDate(h.from)} → {fmtDate(h.to)}: {h.reason}</div>)}
    {a.completion_note && <div className="small">Catatan selesai: {a.completion_note}</div>}
    {a.evidence.map(e => <EvidenceRow key={e.id} e={e} ctx={ctx} onDone={onDone} />)}
    {actor && liveA && <div className="stack" style={{ marginTop: 10 }}>
      <div className="row">
        {a.state === "OPEN" && <button className="btn sm" disabled={busy} onClick={() => run(() => api(`/compliance/actions/${a.id}/start`, { method: "POST" }), "Tindakan dimulai.")}>Mulai kerjakan</button>}
        <input className="grow" value={desc} onChange={e => setDesc(e.target.value)} placeholder="Keterangan bukti penutupan" />
        <label className="btn sm" style={{ cursor: "pointer" }}>Unggah bukti<input type="file" hidden onChange={upload} /></label>
      </div>
      <div className="row">
        <input className="grow" value={note} onChange={e => setNote(e.target.value)} placeholder="Catatan penyelesaian" />
        <button className="btn sm primary" disabled={busy || !accepted} title={accepted ? "" : "Butuh bukti yang sudah diterima"} onClick={() => run(() => api(`/compliance/actions/${a.id}/complete`, { body: { note } }), "Tindakan ditandai selesai.")}>Tandai selesai</button>
      </div>
      {!accepted && <span className="hint">Tindakan baru bisa diselesaikan setelah minimal satu bukti diterima Pejabat Kepatuhan.</span>}
      <details><summary className="small" style={{ cursor: "pointer" }}>Perpanjang jatuh tempo</summary><div className="row" style={{ marginTop: 6 }}>
        <input type="date" value={ext.new_due_date} onChange={e => setExt({ ...ext, new_due_date: e.target.value })} />
        <input className="grow" value={ext.reason} onChange={e => setExt({ ...ext, reason: e.target.value })} placeholder="Alasan perpanjangan" />
        <button className="btn sm" disabled={busy || !ext.new_due_date || !ext.reason} onClick={() => run(() => api(`/compliance/actions/${a.id}/extend`, { body: ext }), "Jatuh tempo diperpanjang; tanggal asli tetap tercatat.")}>Simpan</button></div></details>
    </div>}
  </div>;
}