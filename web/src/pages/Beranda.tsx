import { api } from "../api";
import type { Doc } from "../types";
import type { Ctx } from "../ui";
import { Empty, ImpactIcon, Sev, Status, fmtDate, fmtTime, useLoad } from "../ui";

export function Beranda({ ctx }: { ctx: Ctx }) {
  const [m] = useLoad<any>(() => api("/compliance/dashboard"), [], ctx.notify);
  const [docs] = useLoad<Doc[]>(() => api("/corpus/documents"), [], ctx.notify);
  if (!m) return <div className="panel">Memuat postur kepatuhan…</div>;
  const total = m.active_obligations || 0;
  const full = m.with_effective_control, part = m.partial_coverage, none = m.gaps;
  const pct = (n: number) => (total ? `${(100 * n) / total}%` : "0%");
  const sev = m.findings_by_severity || {};
  const headline = total === 0
    ? "Belum ada kewajiban aktif. Mulai dengan mengekstrak kewajiban dari pasal yang sudah terbit."
    : `${full} dari ${total} kewajiban aktif sudah didukung kontrol yang terbukti efektif.`;

  return <>
    <section className="lead">
      <div className="asat">Posisi per {fmtTime(m.as_at)} · draf AI ({m.excluded_ai_draft}) tidak dihitung</div>
      <h1>{headline}</h1>
      <p>Skor kepatuhan {m.compliance_score_percent}% ({m.compliance_score.numerator}/{m.compliance_score.denominator}) — {m.compliance_score.basis}.</p>
      {total > 0 && <>
        <div className="ratio" role="img" aria-label={`Efektif ${full}, sebagian ${part}, tanpa kontrol ${none}`}>
          <i className="r-full" style={{ width: pct(full) }} /><i className="r-part" style={{ width: pct(part) }} /><i className="r-none" style={{ width: pct(none) }} />
        </div>
        <div className="ratio-legend">
          <span style={{ ["--c" as any]: "var(--green)" }}>Kontrol efektif {full}</span>
          <span style={{ ["--c" as any]: "var(--seal)" }}>Ada kontrol, belum terbukti {part}</span>
          <span style={{ ["--c" as any]: "var(--red)" }}>Tanpa kontrol {none}</span>
        </div>
      </>}
      <div className="facts">
        <button onClick={() => ctx.go("temuan")}><b>{m.open_findings}</b><span>temuan terbuka</span></button>
        <button onClick={() => ctx.go("temuan")}><b>{m.overdue_actions}</b><span>tindakan lewat tenggat</span></button>
        <button onClick={() => ctx.go("asesmen")}><b>{m.assessments_pending_signoff}</b><span>asesmen menunggu sign-off</span></button>
        <button onClick={() => ctx.go("kewajiban")}><b>{m.review_required}</b><span>kewajiban perlu ditinjau</span></button>
      </div>
    </section>

    <div className="cols">
      <div>
        <section className="panel">
          <header><div><h2>Kesenjangan material</h2><p>Kewajiban aktif tanpa kontrol, lengkap dengan sitasi, pemilik, dan usianya.</p></div>
            <button className="btn sm" onClick={() => ctx.go("kontrol")}>Petakan kontrol</button></header>
          {m.material_gaps.length ? <ul className="list">{m.material_gaps.map((g: any) => <li key={g.obligation_id} className="impact">
            <ImpactIcon level={g.age_days > 30 ? "high" : g.age_days > 7 ? "medium" : "low"} />
            <div><div className="title">{g.summary}</div>
              <div className="sub">{g.canonical_number} {g.number_label} · pemilik {g.owner || "belum ditetapkan"} · {g.age_days} hari</div></div>
          </li>)}</ul> : <Empty>Tidak ada kesenjangan: setiap kewajiban aktif sudah memiliki kontrol.</Empty>}
        </section>

        <section className="panel">
          <header><div><h2>Pusat data regulasi</h2><p>Korpus terkurasi: {Object.entries(m.corpus_by_source || {}).map(([k, v]) => `${k.replace("_", " ")} ${v}`).join(" · ")}.</p></div>
            <button className="btn sm" onClick={() => ctx.go("regulasi")}>Buka korpus</button></header>
          {docs?.length ? <ul className="list">{docs.slice(0, 8).map(d => { const v = d.versions[d.versions.length - 1]; return <li key={d.id}>
            <button className="rowlink" onClick={() => ctx.go("regulasi")}>
              <div className="between"><div><div className="title">{d.canonical_number}</div><div className="sub">{d.title_id}</div></div>
                <div className="row"><Status s={d.status} /><span className="small muted">v{v?.version_number} · {fmtDate(v?.effective_date)}</span></div></div>
            </button></li>; })}</ul> : <Empty>Korpus masih kosong.</Empty>}
        </section>
      </div>

      <aside>
        <section className="panel">
          <h2>Tenggat 30 hari</h2>
          <p className="muted small" style={{ marginTop: 0 }}>Tindakan remediasi, yang lewat tenggat di atas.</p>
          {m.upcoming_deadlines.length ? <ul className="list">{m.upcoming_deadlines.map((u: any) => <li key={u.action_id}>
            <button className="rowlink" onClick={() => ctx.go(`temuan/${u.finding_id}`)}>
              <div className="title">{u.description}</div>
              <div className="sub" style={u.overdue ? { color: "var(--red)", fontWeight: 600 } : undefined}>{u.overdue ? "Lewat tenggat · " : ""}{fmtDate(u.due_date)} · {u.owner}</div>
            </button></li>)}</ul> : <Empty>Tidak ada tenggat dalam 30 hari.</Empty>}
        </section>
        <section className="panel">
          <h2>Temuan terbuka per tingkat</h2>
          <ul className="list">{["CRITICAL", "HIGH", "MEDIUM", "LOW"].map(s => <li key={s} className="between"><Sev s={s} /><b>{sev[s] ?? 0}</b></li>)}
            <li className="between"><span className="small">Risiko diterima (bukan terselesaikan)</span><b>{m.risk_accepted}</b></li></ul>
        </section>
        <section className="panel">
          <h2>Antrean tata kelola</h2>
          <ul className="list">
            <li className="between"><button className="rowlink small" onClick={() => ctx.go("perubahan")}>Perubahan regulasi menunggu reviu analis</button><b>{m.changes_pending_review}</b></li>
            <li className="between"><button className="rowlink small" onClick={() => ctx.go("perubahan")}>Perubahan menunggu konfirmasi materialitas</button><b>{m.changes_pending_confirmation}</b></li>
            <li className="between"><span className="small" style={m.changes_over_sla ? { color: "var(--red)" } : undefined}>Perubahan melewati SLA reviu {m.change_review_sla_days} hari</span><b>{m.changes_over_sla}</b></li>
            <li className="between"><button className="rowlink small" onClick={() => ctx.go("keberlakuan")}>Keputusan keberlakuan menunggu persetujuan/hukum</button><b>{m.applicability_pending}</b></li>
            <li className="between"><span className="small">Bukti menunggu tinjauan</span><b>{m.evidence_pending_review}</b></li>
            <li className="between"><span className="small">Kontrol tanpa pemilik</span><b>{m.controls_without_owner}</b></li>
            <li className="between"><span className="small">Temuan lewat target penutupan</span><b>{m.overdue_findings}</b></li>
          </ul>
        </section>
      </aside>
    </div>
  </>;
}
