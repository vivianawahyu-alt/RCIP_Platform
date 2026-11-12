import { useState } from "react";
import { api } from "../api";
import type { Ctx } from "../ui";
import { Empty, PageHead, Sev, Status, fmtDate, inDays, useAction, useLoad } from "../ui";

type OwnedControl = {
  id: string; title: string; source_changed: boolean; status: "NEEDS_EVIDENCE" | "PENDING_REVIEW" | "ACCEPTED" | "EFFECTIVE";
  signed_off_at: string | null; evidence: { total: number; accepted: number; pending: number; rejected: number };
  obligations: { obligation_id: string; summary: string; provision_version_id: string; number_label: string; canonical_number: string; version_number: number }[];
};
type OwnedFinding = {
  id: string; title: string; severity: string; state: string; source_type: string; created_at: string; target_closure_date: string | null;
  raised_by: string | null; needs_plan: boolean; actions: { id: string; description: string; state: string; due_date: string; overdue: boolean }[];
};
type Workspace = { controls: OwnedControl[]; findings: OwnedFinding[] };

const WINDOW: Record<string, number> = { CRITICAL: 30, HIGH: 60, MEDIUM: 90, LOW: 180 };
const SOURCE: Record<string, string> = { COVERAGE_GAP: "Dari pindaian kesenjangan", ASSESSMENT: "Dari hasil asesmen", EVIDENCE_GAP: "Bukti tidak tersedia", MANUAL: "Dicatat manual" };
const BADGE: Record<OwnedControl["status"], [string, string]> = {
  NEEDS_EVIDENCE: ["Bukti diminta", "amber"], PENDING_REVIEW: ["Menunggu tinjauan", "blue"],
  ACCEPTED: ["Bukti diterima · menunggu asesmen", "teal"], EFFECTIVE: ["Efektif · bukti diterima", "green"],
};

export function KontrolSaya({ ctx }: { ctx: Ctx }) {
  const [w, reload] = useLoad<Workspace>(() => api("/compliance/owner/workspace"), [], ctx.notify);
  if (!w) return <div className="panel">Memuat kontrol Anda…</div>;
  const needAttention = w.controls.filter(c => c.status === "NEEDS_EVIDENCE" || c.source_changed).length;

  return <>
    <PageHead crumbs="Kepatuhan · Risiko & kontrol" title="Kontrol saya"
      intro="Kontrol yang Anda miliki, beserta bukti yang perlu diunggah dan temuan yang perlu diperbaiki." />
    <div className="cols">
      <div>
        {w.controls.length ? w.controls.map(c => <ControlCard key={c.id} c={c} ctx={ctx} onDone={reload} />)
          : <section className="panel"><Empty>Belum ada kontrol yang ditetapkan kepada Anda. Hubungi Pejabat Kepatuhan.</Empty></section>}
        {needAttention === 0 && w.controls.length > 0 && <p className="small muted">Tidak ada kontrol yang menunggu bukti dari Anda.</p>}
      </div>
      <aside>
        <section className="panel">
          <div className="between"><h2 style={{ margin: 0 }}>Temuan untuk Anda</h2>
            <span className={`badge ${w.findings.length ? "red" : "green"}`}>{w.findings.length ? `${w.findings.length} terbuka` : "Tidak ada"}</span></div>
          {w.findings.length ? w.findings.map(f => <FindingCard key={f.id} f={f} ctx={ctx} onDone={reload} />)
            : <Empty>Tidak ada temuan terbuka atas nama Anda.</Empty>}
        </section>
      </aside>
    </div>
  </>;
}

function ControlCard({ c, ctx, onDone }: { c: OwnedControl; ctx: Ctx; onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [desc, setDesc] = useState("");
  const { run, busy } = useAction(ctx.notify, () => { setFile(null); setDesc(""); onDone(); });
  const [label, tone] = BADGE[c.status];
  const ob = c.obligations[0];
  const askEvidence = c.status === "NEEDS_EVIDENCE" || c.source_changed;

  const send = () => file && run(async () => {
    const form = new FormData(); form.append("file", file); form.append("description", desc);
    await api(`/compliance/controls/${c.id}/evidence`, { form });
  }, "Bukti terkirim dan menunggu tinjauan Pejabat Kepatuhan.");

  return <section className="panel">
    <div className="between"><h2 style={{ margin: 0 }}>{c.title}</h2><span className={`badge ${tone}`}>{label}</span></div>
    <p className="small muted" style={{ margin: "4px 0 0" }}>
      {ob ? <>Kewajiban{c.obligations.length > 1 ? ` (${c.obligations.length})` : ""}: <button type="button" className="cite" onClick={() => ctx.openCite(ob.provision_version_id)}>{ob.canonical_number} v{ob.version_number} {ob.number_label}</button></>
        : "Belum dipetakan ke kewajiban."}
      {c.status === "EFFECTIVE" && c.signed_off_at && <> · asesmen terakhir disetujui manajer {fmtDate(c.signed_off_at)}</>}
      {c.evidence.pending > 0 && <> · {c.evidence.pending} bukti menunggu tinjauan</>}
      {c.evidence.rejected > 0 && c.status === "NEEDS_EVIDENCE" && <> · {c.evidence.rejected} bukti ditolak, unggah ulang</>}
    </p>
    {c.source_changed && <div className="notice warn" style={{ marginTop: 10, marginBottom: 0 }}><span>Pasal sumber berubah material. Unggah bukti terbaru agar kontrol dapat diasesmen ulang.</span></div>}

    {askEvidence && <div className="form" style={{ marginTop: 14 }}>
      <div className="dropzone">
        <div><b>Unggah bukti</b><div className="small muted">{file ? `${file.name} · ${(file.size / 1024).toFixed(0)} KB` : "PDF, gambar, atau CSV"}</div></div>
        <label className="btn" style={{ cursor: "pointer" }}>Pilih file<input type="file" hidden accept=".pdf,.png,.jpg,.jpeg,.csv" onChange={e => setFile(e.target.files?.[0] || null)} /></label>
      </div>
      <label className="field">Keterangan bukti<input value={desc} onChange={e => setDesc(e.target.value)} placeholder="mis. Berita acara serah terima, 15 Des 2026" /></label>
      <div><button className="btn primary" disabled={busy || !file} onClick={send}>Kirim bukti untuk ditinjau</button></div>
    </div>}
  </section>;
}

function FindingCard({ f, ctx, onDone }: { f: OwnedFinding; ctx: Ctx; onDone: () => void }) {
  const win = WINDOW[f.severity] ?? 30;
  const [plan, setPlan] = useState("");
  const [due, setDue] = useState(inDays(Math.min(14, win)));
  const { run, busy } = useAction(ctx.notify, onDone);
  const live = f.actions.filter(a => a.state !== "CANCELLED");

  return <div className="owner-finding">
    <div className="between"><b>{f.title}</b><Sev s={f.severity} /></div>
    <div className="small muted">{SOURCE[f.source_type] || f.source_type}{f.raised_by ? ` ${f.raised_by}` : ""} · {fmtDate(f.created_at)} · target {fmtDate(f.target_closure_date)}</div>

    {f.needs_plan && <div className="form" style={{ marginTop: 10 }}>
      <label className="field">Rencana remediasi<textarea value={plan} onChange={e => setPlan(e.target.value)} placeholder="Langkah perbaikan" /></label>
      <label className="field">Tenggat<input type="date" value={due} min={inDays(0)} max={inDays(win)} onChange={e => setDue(e.target.value)} /></label>
      <span className="hint">Maksimal {win} hari untuk tingkat {f.severity}.</span>
      <div><button className="btn primary" disabled={busy || !plan.trim() || !due}
        onClick={() => run(() => api(`/compliance/owner/findings/${f.id}/plan`, { body: { description: plan.trim(), due_date: due } }), "Rencana remediasi tersimpan.")}>Simpan rencana</button></div>
    </div>}

    {live.length > 0 && <ul className="list" style={{ marginTop: 8 }}>{live.map(a => <li key={a.id}>
      <div className="between"><span className="small">{a.description}</span><Status s={a.state} /></div>
      <div className="small muted" style={a.overdue ? { color: "var(--red)", fontWeight: 600 } : undefined}>Tenggat {fmtDate(a.due_date)}{a.overdue ? " (terlambat)" : ""}</div>
    </li>)}</ul>}
    {live.length > 0 && <button className="btn ghost sm" onClick={() => ctx.go(`temuan/${f.id}`)}>Kerjakan tindakan & unggah bukti penutupan →</button>}
  </div>;
}
