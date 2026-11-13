import { useEffect, useState } from "react";
import { api } from "../api";
import { CitationPicker } from "../CitationPicker";
import type { Cite } from "../CitationPicker";
import type { Doc, User } from "../types";
import type { Ctx } from "../ui";
import { Empty, Flow, PageHead, Status, can, fmtDate, fmtTime, inDays, useAction, useLoad } from "../ui";

const VALUES: [string, string][] = [["APPLICABLE", "Berlaku"], ["PARTIALLY_APPLICABLE", "Berlaku sebagian"], ["NOT_APPLICABLE", "Tidak berlaku"], ["REQUIRES_FURTHER_REVIEW", "Perlu kajian lanjut"]];
const VL = Object.fromEntries(VALUES);
const STEPS: [string, string][] = [["IN_ASSESSMENT", "Disusun"], ["PENDING_APPROVAL", "Menunggu persetujuan"], ["APPROVED", "Disetujui"]];
const STATE_TXT: Record<string, string> = { IN_ASSESSMENT: "Disusun", PENDING_LEGAL: "Menunggu Peninjau Hukum", PENDING_APPROVAL: "Menunggu persetujuan",
  APPROVED: "Disetujui", REJECTED_TO_MAKER: "Dikembalikan", REVIEW_REQUIRED: "Perlu ditinjau ulang", SUPERSEDED: "Digantikan" };
type Prov = { provision_version_id: string; number_label: string; text: string };

export function Keberlakuan({ ctx }: { ctx: Ctx }) {
  const [rows, reload] = useLoad<any[]>(() => api("/compliance/applicability"), [], ctx.notify);
  const [filter, setFilter] = useState("AKTIF");
  const [showNew, setShowNew] = useState(false);
  const officer = can(ctx.me.role, "applicability_create");
  const shown = (rows || []).filter(d => filter === "SEMUA" || (filter === "AKTIF" ? d.state !== "SUPERSEDED" : d.state === filter));
  return <>
    <PageHead crumbs="Kepatuhan" title="Keberlakuan" intro="Apakah sebuah peraturan mengikat organisasi? Saran aturan hanya titik awal; Pejabat Kepatuhan menyusun keputusan bersitasi, Manajer Kepatuhan menyetujui (titik kendali 2). Ekstraksi kewajiban hanya untuk versi dengan keputusan berlaku yang disetujui.">
      {officer && <button className="btn primary" onClick={() => setShowNew(!showNew)}>{showNew ? "Batal" : "Susun keputusan"}</button>}
    </PageHead>
    <Profile ctx={ctx} onChange={reload} />
    {showNew && <NewDecision ctx={ctx} onDone={() => { setShowNew(false); reload(); }} />}
    <div className="tabs">{[["AKTIF", "Aktif"], ["PENDING_APPROVAL", "Menunggu persetujuan"], ["PENDING_LEGAL", "Menunggu hukum"], ["REVIEW_REQUIRED", "Perlu ditinjau"], ["SEMUA", "Semua termasuk digantikan"]].map(([k, l]) =>
      <button key={k} className={filter === k ? "on" : ""} onClick={() => setFilter(k)}>{l}</button>)}</div>
    {shown.length ? shown.map(d => <DecisionCard key={d.id} d={d} ctx={ctx} onDone={reload} />) : <Empty>Tidak ada keputusan untuk saringan ini.</Empty>}
  </>;
}

function Profile({ ctx, onChange }: { ctx: Ctx; onChange: () => void }) {
  const [profiles, reload] = useLoad<any[]>(() => api("/compliance/profiles"), [], ctx.notify);
  const [edit, setEdit] = useState(false), [lic, setLic] = useState(""), [why, setWhy] = useState("");
  const { run, busy } = useAction(ctx.notify, () => { reload(); onChange(); setEdit(false); });
  const p = profiles?.[0];
  if (!p) return null;
  return <section className="panel"><div className="between"><div><h2>{p.organisation_name}</h2>
    <p className="muted small" style={{ margin: "2px 0 0" }}>Profil v{p.version} · entitas {p.entity_type} · izin: {p.licenses.join(", ")} · lini: {p.business_lines.join(", ")}</p></div>
    {can(ctx.me.role, "profile_update") && <button className="btn sm" onClick={() => { setEdit(!edit); setLic(p.licenses.join(", ")); }}>{edit ? "Batal" : "Ubah profil"}</button>}</div>
    {edit && <div className="form" style={{ marginTop: 10 }}>
      <label className="field">Izin (pisahkan dengan koma)<input value={lic} onChange={e => setLic(e.target.value)} /></label>
      <label className="field">Justifikasi<input value={why} onChange={e => setWhy(e.target.value)} /></label>
      <span className="hint">Keputusan yang disetujui dan bersandar pada atribut yang berubah akan ditandai Perlu ditinjau ulang (E7.1).</span>
      <div><button className="btn primary" disabled={busy || !why} onClick={() => run(async () => { const r = await api(`/compliance/profiles/${p.id}`, { method: "PUT", body: { licenses: lic.split(",").map(x => x.trim()).filter(Boolean), justification: why } }); ctx.notify("ok", `Profil v${r.version}; ${r.flagged_decisions.length} keputusan ditandai untuk ditinjau.`); })}>Simpan profil</button></div>
    </div>}
  </section>;
}

function NewDecision({ ctx, onDone }: { ctx: Ctx; onDone: () => void }) {
  const [docs] = useLoad<Doc[]>(() => api("/corpus/documents"), [], ctx.notify);
  const [users] = useLoad<User[]>(() => api("/users"), [], ctx.notify);
  const [docId, setDocId] = useState(""), [provs, setProvs] = useState<Prov[]>([]), [sug, setSug] = useState<any>(null);
  const [f, setF] = useState({ decision_value: "APPLICABLE", reason: "", cited: [] as string[], scope: [] as string[], review_owner_id: "", review_target_date: inDays(30) });
  const { run, busy } = useAction(ctx.notify);
  const doc = docs?.find(d => d.id === docId);
  const ver = doc?.versions.filter(v => v.state === "PUBLISHED").slice(-1)[0];
  useEffect(() => {
    if (!ver) return;
    api<Prov[]>(`/corpus/versions/${ver.id}/provisions`).then(setProvs).catch(() => setProvs([]));
    api("/compliance/applicability/suggest", { body: { version_id: ver.id } }).then(r => { setSug(r); setF(x => ({ ...x, decision_value: r.suggested_value, reason: r.reason })); }).catch(() => setSug(null));
  }, [ver?.id]);
  const toggle = (k: "cited" | "scope", id: string) => setF(x => ({ ...x, [k]: x[k].includes(id) ? x[k].filter(y => y !== id) : [...x[k], id] }));
  const submit = () => run(async () => {
    const r = await api("/compliance/applicability", { body: { version_id: ver!.id, decision_value: f.decision_value, reason: f.reason,
      cited_provision_version_ids: f.cited, scope_provision_version_ids: f.decision_value === "PARTIALLY_APPLICABLE" ? f.scope : [],
      review_owner_id: f.decision_value === "REQUIRES_FURTHER_REVIEW" ? f.review_owner_id || null : null,
      review_target_date: f.decision_value === "REQUIRES_FURTHER_REVIEW" ? f.review_target_date : null } });
    await api(`/compliance/applicability/${r.id}/submit`, { method: "POST" }); onDone();
  }, "Keputusan disusun dan diajukan ke Manajer Kepatuhan.");
  return <section className="panel"><h2>Susun keputusan keberlakuan</h2><div className="form">
    <label className="field">Peraturan<select value={docId} onChange={e => { setDocId(e.target.value); setF(x => ({ ...x, cited: [], scope: [] })); }}><option value="">Pilih dokumen</option>{(docs || []).map(d => <option key={d.id} value={d.id}>{d.canonical_number} — {d.title_id}</option>)}</select></label>
    {ver && <p className="small muted" style={{ margin: 0 }}>Versi {ver.version_number}, berlaku {fmtDate(ver.effective_date)}</p>}
    {sug && <div className="notice ok"><span>Saran aturan: <b>{VL[sug.suggested_value]}</b> — {sug.reason}. Kode alasan: {sug.reason_codes.join(", ") || "-"}. {sug.note}</span></div>}
    {ver && <>
      <div className="form-2">
        <label className="field">Keputusan<select value={f.decision_value} onChange={e => setF({ ...f, decision_value: e.target.value })}>{VALUES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <label className="field">Alasan dengan kata-kata Anda<input value={f.reason} onChange={e => setF({ ...f, reason: e.target.value })} /></label>
      </div>
      <fieldset style={{ border: "1px solid var(--line)", borderRadius: 8, padding: 10 }}><legend className="small"><b>Sitasi pasal</b> (minimal satu){f.decision_value === "PARTIALLY_APPLICABLE" && " · centang kolom kanan untuk pasal yang berlaku"}</legend>
        {provs.map(p => <div key={p.provision_version_id} className="between small" style={{ padding: "4px 0" }}>
          <label className="row" style={{ gap: 6 }}><input type="checkbox" checked={f.cited.includes(p.provision_version_id)} onChange={() => toggle("cited", p.provision_version_id)} /><b>{p.number_label}</b> <span className="muted">{p.text.slice(0, 90)}…</span></label>
          {f.decision_value === "PARTIALLY_APPLICABLE" && <label className="row" style={{ gap: 4 }}><input type="checkbox" checked={f.scope.includes(p.provision_version_id)} onChange={() => toggle("scope", p.provision_version_id)} />berlaku</label>}
        </div>)}
      </fieldset>
      {f.decision_value === "REQUIRES_FURTHER_REVIEW" && <div className="form-2">
        <label className="field">Pemilik kajian<select value={f.review_owner_id} onChange={e => setF({ ...f, review_owner_id: e.target.value })}><option value="">Pilih</option>{(users || []).filter(u => ["LEGAL_REVIEWER", "COMPLIANCE_OFFICER"].includes(u.role)).map(u => <option key={u.id} value={u.id}>{u.username}</option>)}</select></label>
        <label className="field">Tanggal target<input type="date" value={f.review_target_date} onChange={e => setF({ ...f, review_target_date: e.target.value })} /></label></div>}
      <div><button className="btn primary" disabled={busy || !f.reason || !f.cited.length} onClick={submit}>Ajukan ke Manajer Kepatuhan</button></div>
    </>}
  </div></section>;
}

function DecisionCard({ d, ctx, onDone }: { d: any; ctx: Ctx; onDone: () => void }) {
  const [txt, setTxt] = useState(""), [cites, setCites] = useState<Cite[]>([]);  const { run, busy } = useAction(ctx.notify, onDone);
  const role = ctx.me.role;
  return <section className="panel">
    <div className="between"><div><div className="title" style={{ fontWeight: 700 }}>{d.document} <span className="muted small">v{d.version_number}</span></div><div className="sub small muted">{d.title}</div></div>
      <div className="row"><span className={`badge ${d.decision_value === "APPLICABLE" ? "green" : d.decision_value === "NOT_APPLICABLE" ? "" : "amber"}`}>{VL[d.decision_value]}</span><span className="badge">{STATE_TXT[d.state] || d.state}</span></div></div>
    {STEPS.some(s => s[0] === d.state) && <div style={{ marginTop: 10 }}><Flow steps={STEPS} now={d.state} /></div>}
    <p style={{ margin: "6px 0" }}>{d.reason}</p>
    <div className="row small muted">{d.citations.map((c: any) => <button key={c.provision_version_id} className="cite" onClick={() => ctx.openCite(c.provision_version_id)}>{c.canonical_number} {c.number_label}</button>)}
      <span>Disusun {d.maker} {fmtTime(d.created_at)}</span>{d.approver && <span>Disetujui {d.approver} {fmtTime(d.decided_at)}</span>}
      {d.suggested_value && d.suggested_value !== d.decision_value && <span className="badge amber">Berbeda dari saran aturan ({VL[d.suggested_value]})</span>}
      {d.review_owner && <span>Kajian: {d.review_owner}, target {fmtDate(d.review_target_date)}</span>}</div>
    {d.legal_question && <p className="small" style={{ whiteSpace: "pre-line" }}>Pertanyaan hukum: {d.legal_question}{d.legal_answer && <><br />Posisi hukum ({d.legal_reviewer}): {d.legal_answer}</>}</p>}
    {d.return_reason && d.state === "REJECTED_TO_MAKER" && <p className="small" style={{ color: "var(--red)" }}>Dikembalikan: {d.return_reason}</p>}
    {role === "COMPLIANCE_OFFICER" && ["IN_ASSESSMENT", "REJECTED_TO_MAKER"].includes(d.state) && <div className="row" style={{ marginTop: 8 }}>
      <button className="btn primary sm" disabled={busy} onClick={() => run(() => api(`/compliance/applicability/${d.id}/submit`, { method: "POST" }), "Diajukan ke Manajer Kepatuhan.")}>Ajukan persetujuan</button>
      <input className="grow" value={txt} onChange={e => setTxt(e.target.value)} placeholder="Pertanyaan untuk Peninjau Hukum" />
      <button className="btn sm" disabled={busy || !txt} onClick={() => run(() => api(`/compliance/applicability/${d.id}/escalate`, { body: { question: txt } }), "Dieskalasi ke Peninjau Hukum.")}>Eskalasi</button></div>}
    {role === "COMPLIANCE_OFFICER" && d.state === "REVIEW_REQUIRED" && <div style={{ marginTop: 8 }}><button className="btn sm" disabled={busy} onClick={() => run(() => api(`/compliance/applicability/${d.id}/reopen`, { method: "POST" }), "Draf baru dibuat; keputusan lama tetap berlaku sampai draf baru disetujui.")}>Buka kajian ulang</button></div>}
    {role === "LEGAL_REVIEWER" && d.state === "PENDING_LEGAL" && <div className="decision"><h4>Posisi hukum</h4>
      <div className="row"><input className="grow" value={txt} onChange={e => setTxt(e.target.value)} placeholder="Posisi hukum" /></div>
      <CitationPicker value={cites} onChange={setCites} />
      <div className="row" style={{ marginTop: 8 }}>
        <button className="btn primary" disabled={busy || !txt.trim() || !cites.length} onClick={() => run(() => api(`/compliance/applicability/${d.id}/legal-answer`, { body: { answer: txt, citation_provision_version_ids: cites.map(x => x.id) } }), "Posisi hukum tercatat.")}>Kirim</button></div></div>}    {role === "COMPLIANCE_MANAGER" && d.state === "PENDING_APPROVAL" && <div className="decision"><h4>Persetujuan keberlakuan (titik kendali 2)</h4>
      {d.maker_id === ctx.me.user_id && <p className="small" style={{ color: "var(--red)" }}>Anda penyusun keputusan ini sehingga tidak dapat menyetujuinya.</p>}
      <div className="row"><input className="grow" value={txt} onChange={e => setTxt(e.target.value)} placeholder="Alasan (wajib bila dikembalikan)" />
        <button className="btn primary" disabled={busy} onClick={() => run(() => api(`/compliance/applicability/${d.id}/decision`, { body: { outcome: "APPROVED", reason: txt } }), "Keputusan disetujui dan menjadi catatan resmi.")}>Setujui</button>
        <button className="btn danger" disabled={busy || !txt} onClick={() => run(() => api(`/compliance/applicability/${d.id}/decision`, { body: { outcome: "REJECTED", reason: txt } }), "Dikembalikan ke penyusun.")}>Kembalikan</button></div></div>}
  </section>;
}