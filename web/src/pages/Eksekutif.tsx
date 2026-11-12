import { api } from "../api";
import type { Ctx } from "../ui";
import { Empty, PageHead, fmtDate, fmtTime, useLoad } from "../ui";

type Posture = {
  as_at: string; basis: string;
  kpis: { active_obligations: number; regulations_in_force: number; effective_percent: number; effective_count: number;
    open_findings: number; overdue_findings: number; reports_issued: number; last_report: { id: string; title: string; issued_at: string } | null };
  by_area: { area: string; obligations: number; effective: number; effective_percent: number; open_findings: number }[];
  new_regulations: { document_id: string; canonical_number: string; title_id: string; issuer: string; version_number: number; effective_date: string }[];
};

const tone = (p: number) => (p >= 80 ? "ok" : p >= 50 ? "mid" : "low");

function Kpi({ label, value, unit, note, tone: t, onClick }: { label: string; value: number | string; unit?: string; note: string; tone?: string; onClick?: () => void }) {
  const body = <>
    <span className="kpi-label">{label}</span>
    <b className={`kpi-value ${t || ""}`}>{value}{unit}</b>
    <span className="kpi-note">{note}</span>
  </>;
  return onClick ? <button type="button" className="kpi" onClick={onClick}>{body}</button> : <div className="kpi">{body}</div>;
}

export function Postur({ ctx }: { ctx: Ctx }) {
  const [p] = useLoad<Posture>(() => api("/compliance/executive/posture"), [], ctx.notify);
  if (!p) return <div className="panel">Memuat postur kepatuhan…</div>;
  const k = p.kpis, last = k.last_report;
  const goReport = () => ctx.go(last ? `laporan/${last.id}` : "laporan");

  return <>
    <PageHead crumbs={`Beranda · per ${fmtDate(p.as_at)}`} title="Postur kepatuhan"
      intro="Ringkasan untuk direksi. Setiap angka dapat ditelusuri sampai pasal regulasi sumbernya lewat laporan terbit." />

    <div className="kpi-grid">
      <Kpi label="Kewajiban aktif" value={k.active_obligations} note={`dari ${k.regulations_in_force} regulasi terbit`} onClick={goReport} />
      <Kpi label="Kontrol efektif" value={k.effective_percent} unit="%" tone={tone(k.effective_percent)}
        note={`${k.effective_count} kewajiban · asesmen sign-off`} onClick={goReport} />
      <Kpi label="Temuan terbuka" value={k.open_findings} tone={k.open_findings ? "low" : "ok"}
        note={`${k.overdue_findings} lewat tenggat`} onClick={goReport} />
      <Kpi label="Laporan terbit" value={k.reports_issued}
        note={last ? `terakhir: ${last.title}` : "belum ada laporan terbit"} onClick={goReport} />
    </div>

    <div className="cols">
      <section className="panel">
        <header><div><h2>Kepatuhan per area</h2><p>Dasar hitung: {p.basis}.</p></div></header>
        {p.by_area.length ? <div className="tablewrap"><table className="data">
          <thead><tr><th>Area</th><th>Kewajiban</th><th>Kontrol efektif</th><th>Temuan terbuka</th></tr></thead>
          <tbody>{p.by_area.map(a => <tr key={a.area}>
            <td>{a.area}</td>
            <td>{a.obligations}</td>
            <td><div className="bar-cell">
              <div className="bar" role="img" aria-label={`${a.effective_percent}% efektif`}><i className={tone(a.effective_percent)} style={{ width: `${a.effective_percent}%` }} /></div>
              <span>{a.effective_percent}%</span></div></td>
            <td>{a.open_findings}</td>
          </tr>)}</tbody></table></div>
          : <Empty>Belum ada kewajiban aktif yang berlabel area (taksonomi THEME).</Empty>}
      </section>

      <aside>
        <section className="panel">
          <h2>Regulasi baru terbit</h2>
          {p.new_regulations.length ? <ul className="list">{p.new_regulations.map(r => <li key={`${r.document_id}-${r.version_number}`}>
            <div className="title">{r.canonical_number}</div>
            <div className="sub">{r.title_id} · v{r.version_number} · berlaku {fmtDate(r.effective_date)}</div>
          </li>)}</ul> : <Empty>Belum ada regulasi terbit.</Empty>}
          <p style={{ marginBottom: 0 }}><button className="btn ghost" onClick={goReport}>{last ? `Buka ${last.title} →` : "Buka laporan →"}</button></p>
          {last && <p className="small muted" style={{ margin: "4px 0 0" }}>Diterbitkan {fmtTime(last.issued_at)}</p>}
        </section>
      </aside>
    </div>
  </>;
}