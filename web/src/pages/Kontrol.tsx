import { useState } from "react";
import type { ChangeEvent } from "react";
import { api, download } from "../api";
import type { Assessment, Control, Evidence, Obligation, Risk, User } from "../types";
import type { Ctx, Notify } from "../ui";
import { Empty, PageHead, Sev, Status, can, fmtDate, fmtTime, useAction, useLoad } from "../ui";

export function Kontrol({ ctx, selected }: { ctx: Ctx; selected?: string }) {
  const [obs] = useLoad<Obligation[]>(() => api("/compliance/obligations"), [], ctx.notify);
  const [risks, reloadR] = useLoad<Risk[]>(() => api("/compliance/risks"), [], ctx.notify);
  const [controls, reloadC] = useLoad<Control[]>(() => api("/compliance/controls"), [], ctx.notify);
  const [users] = useLoad<User[]>(() => api("/users"), [], ctx.notify);
  const [rf, setRf] = useState({ obligation_id: "", title: "", severity: "MEDIUM" });
  const [cf, setCf] = useState({ risk_id: "", title: "", owner_id: "" });
  const reload = () => { reloadR(); reloadC(); };
  const { run, busy } = useAction(ctx.notify, reload);
  const officer = can(ctx.me.role, "risk_control_write");
  const active = (obs || []).filter(o => ["ACTIVE", "REVIEW_REQUIRED"].includes(o.state));
  const owners = (users || []).filter(u => ["BUSINESS_CONTROL_OWNER", "COMPLIANCE_OFFICER"].includes(u.role));
  const sel = selected || controls?.[0]?.id;

  return <>
    <PageHead crumbs="Kepatuhan" title="Risiko & kontrol" intro="Petakan kewajiban aktif ke risiko dan kontrol yang bertuan. Kontrol membutuhkan bukti yang diterima sebelum dapat diasesmen." />
    {officer && <div className="cols-even">
      <section className="panel"><h2>Tambah risiko</h2><div className="form">
        <label className="field">Kewajiban<select value={rf.obligation_id} onChange={e => setRf({ ...rf, obligation_id: e.target.value })}><option value="">Pilih kewajiban aktif</option>{active.map(o => <option key={o.id} value={o.id}>{o.citation.number_label} · {o.summary?.slice(0, 80)}</option>)}</select></label>
        <div className="form-2"><label className="field">Judul risiko<input value={rf.title} onChange={e => setRf({ ...rf, title: e.target.value })} placeholder="Laporan insiden terlambat" /></label>
          <label className="field">Tingkat<select value={rf.severity} onChange={e => setRf({ ...rf, severity: e.target.value })}>{["CRITICAL", "HIGH", "MEDIUM", "LOW"].map(s => <option key={s}>{s}</option>)}</select></label></div>
        <div><button className="btn primary" disabled={busy || !rf.obligation_id || !rf.title} onClick={() => run(async () => { await api("/compliance/risks", { body: rf }); setRf({ obligation_id: "", title: "", severity: "MEDIUM" }); }, "Risiko ditambahkan.")}>Tambah risiko</button></div>
      </div></section>
      <section className="panel"><h2>Tambah kontrol</h2><div className="form">
        <label className="field">Risiko yang dimitigasi<select value={cf.risk_id} onChange={e => setCf({ ...cf, risk_id: e.target.value })}><option value="">Tanpa risiko</option>{(risks || []).map(r => <option key={r.id} value={r.id}>{r.title}</option>)}</select></label>
        <div className="form-2"><label className="field">Nama kontrol<input value={cf.title} onChange={e => setCf({ ...cf, title: e.target.value })} placeholder="Eskalasi insiden otomatis ≤ 12 jam" /></label>
          <label className="field">Pemilik kontrol<select value={cf.owner_id} onChange={e => setCf({ ...cf, owner_id: e.target.value })}><option value="">Belum ditetapkan</option>{owners.map(u => <option key={u.id} value={u.id}>{u.username}</option>)}</select></label></div>
        <div><button className="btn primary" disabled={busy || !cf.title} onClick={() => run(async () => { const r = await api("/compliance/controls", { body: { ...cf, risk_id: cf.risk_id || null, owner_id: cf.owner_id || null } }); setCf({ risk_id: "", title: "", owner_id: "" }); ctx.go(`kontrol/${r.id}`); }, "Kontrol ditambahkan.")}>Tambah kontrol</button></div>
      </div></section>
    </div>}
    <div className="cols">
      <div>
        <section className="panel"><h2>Pustaka kontrol</h2>
          {controls?.length ? <div className="tablewrap"><table className="data"><thead><tr><th>Kontrol</th><th>Pemilik</th><th>Kewajiban</th><th>Bukti diterima</th><th>Asesmen terakhir</th></tr></thead>
            <tbody>{controls.map(c => <tr key={c.id} className={`clickable ${c.id === sel ? "selected" : ""}`} onClick={() => ctx.go(`kontrol/${c.id}`)}>
              <td><b>{c.title}</b>{c.source_changed && <> <span className="badge red" title="Pasal sumber berubah material; asesmen ulang diperlukan">Sumber berubah</span></>}{c.risk_title && <div className="small muted">Risiko: {c.risk_title}</div>}</td>
              <td>{c.owner || <span className="badge red">Kosong</span>}</td><td>{c.obligation_ids.length}</td>
              <td>{c.evidence_accepted}/{c.evidence_count}{c.evidence_pending > 0 && <div className="small muted">{c.evidence_pending} menunggu</div>}</td>
              <td>{c.latest_assessment ? <><Status s={c.latest_assessment} /><div className="small muted"><Status s={c.latest_assessment_state} /></div></> : "—"}</td>
            </tr>)}</tbody></table></div> : <Empty>Belum ada kontrol.</Empty>}
        </section>
        <section className="panel"><h2>Register risiko</h2>
          {risks?.length ? <ul className="list">{risks.map(r => <li key={r.id} className="between"><div><div className="title">{r.title}</div><div className="sub">{r.obligation_summary}</div></div><Sev s={r.severity} /></li>)}</ul> : <Empty>Belum ada risiko.</Empty>}
        </section>
      </div>
      <aside className="detail">{sel ? <ControlDetail key={sel} id={sel} ctx={ctx} active={active} owners={owners} onChange={reload} /> : <Empty>Pilih kontrol untuk melihat bukti dan asesmennya.</Empty>}</aside>
    </div>
  </>;
}

function ControlDetail({ id, ctx, active, owners, onChange }: { id: string; ctx: Ctx; active: Obligation[]; owners: User[]; onChange: () => void }) {
  const [c, reload] = useLoad<any>(() => api(`/compliance/controls/${id}`), [id], ctx.notify);
  const [desc, setDesc] = useState("");
  const [af, setAf] = useState({ design_result: "EFFECTIVE", operating_result: "EFFECTIVE", design_rationale: "", operating_rationale: "" });
  const { run, busy } = useAction(ctx.notify, () => { reload(); onChange(); });
  if (!c) return <div className="panel">Memuat…</div>;
  const role = ctx.me.role, officer = can(role, "assess");
  const isOwner = role === "BUSINESS_CONTROL_OWNER" && c.owner_id === ctx.me.user_id;
  const upload = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return; const form = new FormData(); form.append("file", f); form.append("description", desc);
    run(async () => { await api(`/compliance/controls/${id}/evidence`, { form }); setDesc(""); }, "Bukti diunggah dan menunggu tinjauan Pejabat Kepatuhan."); e.target.value = "";
  };
  const unmapped = active.filter(o => !c.obligation_ids.includes(o.id));
  return <section className="panel">
    <h2>{c.title}</h2>
    <p className="muted small" style={{ marginTop: 2 }}>Pemilik: {c.owner || "belum ditetapkan"} · {c.obligation_ids.length} kewajiban terpetakan</p>
    {officer && <div className="form-2" style={{ marginTop: 10 }}>
      <label className="field">Tetapkan pemilik<select value={c.owner_id || ""} onChange={e => e.target.value && run(() => api(`/compliance/controls/${id}/owner`, { body: { owner_id: e.target.value } }), "Pemilik kontrol ditetapkan.")}><option value="">Pilih…</option>{owners.map(u => <option key={u.id} value={u.id}>{u.username}</option>)}</select></label>
      <label className="field">Petakan ke kewajiban<select value="" onChange={e => e.target.value && run(() => api(`/compliance/obligations/${e.target.value}/controls/${id}`, { body: {} }), "Kontrol dipetakan ke kewajiban.")}><option value="">Pilih kewajiban aktif…</option>{unmapped.map(o => <option key={o.id} value={o.id}>{o.citation.number_label} · {o.summary?.slice(0, 60)}</option>)}</select></label>
    </div>}

    <h3 style={{ fontSize: 17, marginTop: 18 }}>Bukti</h3>
    {c.evidence.length ? c.evidence.map((e: Evidence) => <EvidenceRow key={e.id} e={e} ctx={ctx} onDone={() => { reload(); onChange(); }} />) : <p className="muted small">Belum ada bukti.</p>}
    {(officer || isOwner) && <div className="form" style={{ marginTop: 10 }}>
      <label className="field">Keterangan bukti<input value={desc} onChange={e => setDesc(e.target.value)} placeholder="Log eskalasi insiden Oktober 2026 (sintetis)" /></label>
      <label className="field">Unggah berkas<input type="file" onChange={upload} disabled={busy} /></label>
    </div>}

    <h3 style={{ fontSize: 17, marginTop: 18 }}>Asesmen</h3>
    {c.assessments.length ? <ul className="list">{c.assessments.map((a: Assessment) => <li key={a.id}>
      <div className="between"><span className="small">{fmtTime(a.assessed_at)} oleh {a.assessed_by}</span><Status s={a.state} /></div>
      <div className="row small" style={{ marginTop: 4 }}>Desain <Status s={a.design_result} /> Operasional <Status s={a.operating_result} /></div>
      {a.return_reason && a.state === "CONCLUDED" && <p className="small" style={{ color: "var(--red)" }}>Dikembalikan: {a.return_reason}</p>}
      {officer && a.state === "CONCLUDED" && <button className="btn sm" style={{ marginTop: 6 }} disabled={busy} onClick={() => run(() => api(`/compliance/assessments/${a.id}/submit`, { method: "POST" }), "Asesmen diajukan untuk sign-off Manajer Kepatuhan.")}>Ajukan sign-off</button>}
    </li>)}</ul> : <p className="muted small">Belum diasesmen.</p>}
    {officer && <div className="decision">
      <h4>Catat kesimpulan asesmen</h4>
      {c.evidence_accepted === 0 && <p className="small" style={{ color: "var(--amber)", marginTop: 0 }}>Butuh minimal satu bukti berstatus Diterima.</p>}
      <div className="form">
        <div className="form-2">
          <label className="field">Efektivitas desain<select value={af.design_result} onChange={e => setAf({ ...af, design_result: e.target.value })}>{["EFFECTIVE", "PARTIALLY_EFFECTIVE", "INEFFECTIVE", "NOT_ASSESSED"].map(x => <option key={x} value={x}>{x}</option>)}</select></label>
          <label className="field">Efektivitas operasional<select value={af.operating_result} onChange={e => setAf({ ...af, operating_result: e.target.value })}>{["EFFECTIVE", "PARTIALLY_EFFECTIVE", "INEFFECTIVE", "NOT_TESTED", "NOT_APPLICABLE"].map(x => <option key={x} value={x}>{x}</option>)}</select></label>
        </div>
        <label className="field">Rasional desain<textarea value={af.design_rationale} onChange={e => setAf({ ...af, design_rationale: e.target.value })} /></label>
        <label className="field">Rasional operasional<textarea value={af.operating_rationale} onChange={e => setAf({ ...af, operating_rationale: e.target.value })} placeholder="mis. 18 dari 20 sampel sesuai" /></label>
        <span className="hint">Hasil sebagian efektif atau tidak efektif otomatis memunculkan temuan yang tertaut ke asesmen ini.</span>
        <div><button className="btn primary" disabled={busy || !af.design_rationale || !af.operating_rationale || c.evidence_accepted === 0}
          onClick={() => run(async () => { const r = await api(`/compliance/controls/${id}/assessments`, { body: af }); setAf({ ...af, design_rationale: "", operating_rationale: "" }); if (r.finding_id) ctx.notify("ok", "Asesmen dicatat dan temuan otomatis dibuat. Lihat Register temuan."); }, "Asesmen dicatat.")}>Simpan kesimpulan</button></div>
      </div>
    </div>}
  </section>;
}

export function EvidenceRow({ e, ctx, onDone }: { e: Evidence; ctx: Ctx; onDone: () => void }) {
  const [why, setWhy] = useState("");
  const { run, busy } = useAction(ctx.notify, onDone);
  const review = (outcome: string) => run(() => api(`/compliance/evidence/${e.id}/review`, { body: { outcome, rationale: why } }), outcome === "ACCEPTED" ? "Bukti diterima dan kini tidak dapat diubah." : "Bukti ditolak.");
  return <div className="evidence">
    <div className="grow"><b>{e.filename}</b> <Status s={e.state} />
      <div className="small muted">{e.description ? `${e.description} · ` : ""}{e.uploaded_by} · {fmtDate(e.uploaded_at)} · sha256 {e.sha256.slice(0, 10)}…</div>
      {e.review_rationale && <div className="small">Tinjauan {e.reviewed_by}: {e.review_rationale}</div>}
      {can(ctx.me.role, "evidence_review") && e.state === "SUBMITTED" && <div className="row" style={{ marginTop: 6 }}>
        <input className="grow" value={why} onChange={x => setWhy(x.target.value)} placeholder="Rasional tinjauan (wajib)" />
        <button className="btn sm primary" disabled={busy || !why.trim()} onClick={() => review("ACCEPTED")}>Terima</button>
        <button className="btn sm danger" disabled={busy || !why.trim()} onClick={() => review("REJECTED")}>Tolak</button></div>}
    </div>
    {can(ctx.me.role, "evidence_download") && <button className="btn sm ghost" onClick={() => download(`/compliance/evidence/${e.id}/download`, e.filename).catch(x => ctx.notify("error", x.message))}>Unduh</button>}
  </div>;
}

export function Asesmen({ ctx }: { ctx: Ctx }) {
  const [rows, reload] = useLoad<Assessment[]>(() => api("/compliance/assessments"), [], ctx.notify);
  const [reason, setReason] = useState<Record<string, string>>({});
  const { run, busy } = useAction(ctx.notify, reload);
  const manager = can(ctx.me.role, "signoff");
  const pending = (rows || []).filter(a => a.state === "PENDING_SIGNOFF");
  return <>
    <PageHead crumbs="Kepatuhan" title="Asesmen & sign-off" intro="Pejabat Kepatuhan menyimpulkan efektivitas desain dan operasional; Manajer Kepatuhan memberi sign-off (titik kendali 4). Hanya asesmen bersign-off yang masuk skor kepatuhan." />
    <section className="panel"><header><div><h2>Menunggu sign-off</h2><p>{pending.length} asesmen</p></div></header>
      {pending.length ? <ul className="list">{pending.map(a => <li key={a.id}>
        <div className="between"><div><div className="title">{a.control}</div><div className="sub">Asesor {a.assessed_by} · diajukan {a.submitted_by}</div></div>
          <div className="row">Desain <Status s={a.design_result} /> Operasional <Status s={a.operating_result} /></div></div>
        <p className="small"><b>Rasional desain:</b> {a.design_rationale}<br /><b>Rasional operasional:</b> {a.operating_rationale}</p>
        {manager && <div className="row">
          <input className="grow" value={reason[a.id] || ""} onChange={e => setReason({ ...reason, [a.id]: e.target.value })} placeholder="Alasan (wajib bila dikembalikan)" />
          <button className="btn primary" disabled={busy} onClick={() => run(() => api(`/compliance/assessments/${a.id}/signoff`, { body: { outcome: "APPROVED", reason: reason[a.id] } }), "Sign-off tercatat.")}>Beri sign-off</button>
          <button className="btn danger" disabled={busy || !reason[a.id]} onClick={() => run(() => api(`/compliance/assessments/${a.id}/signoff`, { body: { outcome: "REJECTED", reason: reason[a.id] } }), "Asesmen dikembalikan ke asesor.")}>Kembalikan</button>
        </div>}
      </li>)}</ul> : <Empty>Tidak ada asesmen yang menunggu sign-off.</Empty>}
    </section>
    <section className="panel"><h2>Riwayat asesmen</h2>
      {rows?.length ? <div className="tablewrap"><table className="data"><thead><tr><th>Kontrol</th><th>Desain</th><th>Operasional</th><th>Asesor</th><th>Sign-off</th><th>Status</th></tr></thead>
        <tbody>{rows.map(a => <tr key={a.id} className="clickable" onClick={() => ctx.go(`kontrol/${a.control_id}`)}><td>{a.control}</td><td><Status s={a.design_result} /></td><td><Status s={a.operating_result} /></td>
          <td>{a.assessed_by}<div className="small muted">{fmtDate(a.assessed_at)}</div></td><td>{a.signed_off_by || "—"}</td><td><Status s={a.state} /></td></tr>)}</tbody></table></div> : <Empty>Belum ada asesmen.</Empty>}
    </section>
  </>;
}
export type { Notify };
