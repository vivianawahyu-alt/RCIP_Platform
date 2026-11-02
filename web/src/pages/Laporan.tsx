import { useState } from "react";
import { api } from "../api";
import type { Ctx } from "../ui";
import { Empty, Flow, PageHead, Sev, Status, can, fmtDate, fmtTime, useAction, useLoad } from "../ui";

const STEPS: [string, string][] = [["DRAFT", "Draf"], ["PENDING_APPROVAL", "Menunggu persetujuan"], ["ISSUED", "Terbit"]];

export function Laporan({ ctx, selected }: { ctx: Ctx; selected?: string }) {
  const [rows, reload] = useLoad<any[]>(() => api("/compliance/reports"), [], ctx.notify);
  const [title, setTitle] = useState("Laporan Postur Kepatuhan");
  const { run, busy } = useAction(ctx.notify, reload);
  if (selected) return <ReportView id={selected} ctx={ctx} onChange={reload} />;
  return <>
    <PageHead crumbs="Laporan & Audit" title="Laporan kepatuhan" intro="Pejabat Kepatuhan membangkitkan draf; Manajer Kepatuhan menerbitkan (titik kendali 6). Laporan gagal dibuat bila ada angka atau sitasi yang tidak dapat ditelusuri, dan menjadi imutabel setelah terbit." />
    {can(ctx.me.role, "report_generate") && <section className="panel"><h2>Bangkitkan draf</h2><div className="row" style={{ marginTop: 10 }}>
      <input className="grow" value={title} onChange={e => setTitle(e.target.value)} aria-label="Judul laporan" />
      <button className="btn primary" disabled={busy || !title} onClick={() => run(async () => { const r = await api("/compliance/reports", { body: { title } }); ctx.go(`laporan/${r.id}`); }, "Draf laporan dibangkitkan.")}>Bangkitkan draf</button></div></section>}
    <section className="panel"><h2>Arsip laporan</h2>
      {rows?.length ? <div className="tablewrap"><table className="data"><thead><tr><th>Judul</th><th>Dibangkitkan</th><th>Diterbitkan</th><th>Skor</th><th>Status</th></tr></thead>
        <tbody>{rows.map(r => <tr key={r.id} className="clickable" onClick={() => ctx.go(`laporan/${r.id}`)}><td><b>{r.title}</b></td>
          <td>{r.generated_by}<div className="small muted">{fmtTime(r.created_at)}</div></td><td>{r.issued_by ? <>{r.issued_by}<div className="small muted">{fmtTime(r.issued_at)}</div></> : "—"}</td>
          <td>{r.payload?.metrics?.compliance_score_percent ?? 0}%</td><td><Status s={r.state} /></td></tr>)}</tbody></table></div> : <Empty>Belum ada laporan.</Empty>}
    </section>
  </>;
}

function ReportView({ id, ctx, onChange }: { id: string; ctx: Ctx; onChange: () => void }) {
  const [r, reload] = useLoad<any>(() => api(`/compliance/reports/${id}`), [id], ctx.notify);
  const [reason, setReason] = useState("");
  const { run, busy } = useAction(ctx.notify, () => { reload(); onChange(); });
  if (!r) return <div className="panel">Memuat laporan…</div>;
  const p = r.payload || {}, m = p.metrics || {};
  const officer = can(ctx.me.role, "report_generate"), manager = can(ctx.me.role, "report_issue");
  const legacy = !p.obligation_inventory;
  return <>
    <div className="no-print"><button className="btn ghost" onClick={() => ctx.go("laporan")}>← Arsip laporan</button></div>
    <div className="cols">
      <article className="report-doc">
        <div className="crumbs">{p.scope?.organisation} · posisi per {fmtTime(p.scope?.as_at)}{p.scope?.synthetic_data ? " · data sintetis" : ""}</div>
        <h1>{r.title}</h1>
        <div className="row" style={{ margin: "10px 0" }}><Status s={r.state} /><span className="small muted">Dibangkitkan {r.generated_by} · {r.issued_by ? `diterbitkan ${r.issued_by} ${fmtTime(r.issued_at)}` : "belum terbit"}</span></div>
        {r.state === "WITHDRAWN" && <div className="notice error"><span>Laporan ditarik: {r.withdrawn_reason}</span></div>}
        {r.state === "SUPERSEDED" && <div className="notice error"><span>Digantikan oleh laporan yang lebih baru. <button onClick={() => ctx.go(`laporan/${r.superseded_by}`)}>Buka pengganti</button></span></div>}
        {legacy ? <p className="muted">Laporan versi lama (sebelum tahap ini) hanya menyimpan metrik ringkas: skor {m.compliance_score_percent}%, {m.active_obligations} kewajiban aktif.</p> : <>
          <h2>1. Ruang lingkup dan dasar</h2>
          <p>Entitas {p.scope.organisation} ({p.scope.entity_type}). Periode {p.scope.period_start ? `${fmtDate(p.scope.period_start)} – ${fmtDate(p.scope.period_end)}` : "tidak dibatasi"}.</p>
          <h2>2. Dasar korpus</h2>
          <p>{p.corpus_basis.completeness_statement} Sumber: {p.corpus_basis.by_source.map((s: any) => `${s.source} (${s.documents})`).join(", ")}.</p>
          {p.corpus_basis.quality_warnings.map((w: string) => <p key={w} className="small" style={{ color: "var(--amber)" }}>Peringatan: {w}</p>)}
          <h2>3. Peraturan yang berlaku</h2>
          {p.applicable_regulations.length ? <table className="data"><thead><tr><th>Peraturan</th><th>Keberlakuan</th><th>Alasan</th></tr></thead><tbody>{p.applicable_regulations.map((g: any, i: number) => <tr key={i}><td><b>{g.canonical_number}</b> v{g.version_number}<div className="small muted">{g.title_id}</div></td><td>{g.decision_value}</td><td className="small">{g.reason_text}<div className="muted">oleh {g.decided_by}</div></td></tr>)}</tbody></table> : <p className="muted">Belum ada keputusan keberlakuan.</p>}
          <h2>4. Inventaris kewajiban ({p.obligation_inventory.length})</h2>
          {p.obligation_inventory.map((o: any) => <div key={o.obligation_id} style={{ marginBottom: 14 }}>
            <div className="between"><b>{o.summary}</b><span className={`badge ${o.coverage === "FULL" ? "green" : o.coverage === "PARTIAL" ? "amber" : "red"}`}>{o.coverage === "FULL" ? "Tercakup efektif" : o.coverage === "PARTIAL" ? "Tercakup sebagian" : "Tanpa kontrol"}</span></div>
            <div className="small muted">Pemilik {o.owner || "—"} · {o.frequency || "frekuensi —"} · {o.deadline || "tenggat —"}</div>
            <div className="verbatim" style={{ fontSize: 15 }}><button className="cite" onClick={() => ctx.openCite(o.citation.provision_version_id)}>{o.citation.canonical_number} {o.citation.number_label}</button> {o.citation.verbatim}</div>
          </div>)}
          <h2>5. Cakupan kontrol</h2>
          <p>Penuh {p.control_coverage.full} · sebagian {p.control_coverage.partial} · tanpa kontrol {p.control_coverage.none}.</p>
          {p.control_coverage.gaps.map((g: any) => <p key={g.obligation_id} className="small">Kesenjangan: {g.summary} — {g.canonical_number} {g.number_label}</p>)}
          <h2>6. Hasil asesmen</h2>
          {p.assessment_results.length ? <table className="data"><thead><tr><th>Kontrol</th><th>Desain</th><th>Operasional</th><th>Bukti</th><th>Status</th></tr></thead><tbody>{p.assessment_results.map((a: any) => <tr key={a.assessment_id}><td>{a.control}<div className="small muted">{a.operating_rationale}</div></td><td><Status s={a.design_result} /></td><td><Status s={a.operating_result} /></td><td>{a.accepted_evidence}</td><td><Status s={a.state} /></td></tr>)}</tbody></table> : <p className="muted">Belum ada asesmen.</p>}
          <h2>7. Temuan dan remediasi</h2>
          {p.findings.length ? <table className="data"><thead><tr><th>Temuan</th><th>Tingkat</th><th>Tindakan</th><th>Status</th></tr></thead><tbody>{p.findings.map((f: any) => <tr key={f.finding_id}><td>{f.title}<div className="small muted">pemilik {f.owner || "—"} · target {fmtDate(f.target_closure_date)}</div></td><td><Sev s={f.severity} /></td><td className="small">{f.actions.map((a: any) => <div key={a.action_id}>{a.description} — {a.state}{a.overdue ? " (terlambat)" : ""}</div>)}</td><td><Status s={f.state} />{f.accepted_gap && <div className="small muted">kesenjangan diterima</div>}</td></tr>)}</tbody></table> : <p className="muted">Tidak ada temuan.</p>}
          <h2>8. Perubahan regulasi</h2>
          {p.regulatory_changes.length ? p.regulatory_changes.map((c: any) => <p key={c.change_set_id} className="small">{c.canonical_number}: v{c.base_version} → v{c.new_version}, {c.material_changes} dari {c.total_changes} perubahan material ({fmtDate(c.computed_on)})</p>) : <p className="muted">Tidak ada perbandingan versi dalam periode.</p>}
          <h2>9. Tertunda dan belum disimpulkan</h2>
          <p className="small">{p.pending.obligations.length} kewajiban belum aktif · {p.pending.assessments.length} asesmen belum bersign-off · {p.pending.findings_pending_closure.length} temuan menunggu validasi penutupan.</p>
          <h2>10. Penafian</h2>
          <p className="disclaimer">{p.disclaimer} <span className="muted">(versi {p.disclaimer_version})</span></p>
        </>}
      </article>
      <aside className="detail no-print">
        <section className="panel"><h2>Alur penerbitan</h2>
          {["DRAFT", "PENDING_APPROVAL", "ISSUED"].includes(r.state) && <Flow steps={STEPS} now={r.state} />}
          {r.return_reason && r.state === "DRAFT" && <p className="small" style={{ color: "var(--red)" }}>Dikembalikan: {r.return_reason}</p>}
          {officer && r.state === "DRAFT" && <div className="row">
            <button className="btn" disabled={busy} onClick={() => run(() => api(`/compliance/reports/${id}/regenerate`, { method: "POST" }), "Draf dibangkitkan ulang dengan data terkini.")}>Bangkitkan ulang</button>
            <button className="btn primary" disabled={busy} onClick={() => run(() => api(`/compliance/reports/${id}/submit`, { method: "POST" }), "Draf diajukan ke Manajer Kepatuhan.")}>Ajukan penerbitan</button></div>}
          {manager && r.state === "PENDING_APPROVAL" && <div className="form">
            {r.generated_by_id === ctx.me.user_id && <p className="small" style={{ color: "var(--red)" }}>Anda membangkitkan laporan ini sehingga tidak dapat menerbitkannya.</p>}
            <label className="field">Alasan (wajib bila dikembalikan)<input value={reason} onChange={e => setReason(e.target.value)} /></label>
            <div className="row"><button className="btn primary" disabled={busy} onClick={() => run(() => api(`/compliance/reports/${id}/decision`, { body: { outcome: "APPROVED", reason } }), "Laporan diterbitkan dan dibekukan.")}>Terbitkan</button>
              <button className="btn danger" disabled={busy || !reason} onClick={() => run(() => api(`/compliance/reports/${id}/decision`, { body: { outcome: "REJECTED", reason } }), "Laporan dikembalikan ke draf.")}>Kembalikan</button></div></div>}
          {manager && r.state === "ISSUED" && <div className="form">
            <label className="field">Alasan penarikan<input value={reason} onChange={e => setReason(e.target.value)} /></label>
            <div><button className="btn danger" disabled={busy || !reason} onClick={() => run(() => api(`/compliance/reports/${id}/withdraw`, { body: { reason } }), "Laporan ditarik; tetap terlihat dengan tanda ditarik.")}>Tarik laporan</button></div></div>}
          <button className="btn" style={{ marginTop: 12 }} onClick={() => window.print()}>Cetak / simpan PDF</button>
        </section>
        {!!r.approvals?.length && <section className="panel"><h2>Keputusan</h2><ul className="list">{r.approvals.map((a: any, i: number) => <li key={i} className="small"><b>{a.outcome}</b> oleh {a.checker} · {fmtTime(a.decided_at)}{a.reason && <div className="muted">{a.reason}</div>}</li>)}</ul></section>}
      </aside>
    </div>
  </>;
}
