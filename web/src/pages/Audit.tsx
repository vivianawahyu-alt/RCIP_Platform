import { useState } from "react";
import { api, download } from "../api";
import type { Ctx } from "../ui";
import { Empty, PageHead, can, fmtTime, useLoad } from "../ui";

const TYPES = ["", "obligation", "finding", "remediation_action", "evidence", "assessment", "compliance_report", "control", "document_version"];

export function Audit({ ctx }: { ctx: Ctx }) {
  const [f, setF] = useState({ object_type: "", action: "", actor: "" });
  const [applied, setApplied] = useState(f);
  const qs = new URLSearchParams(Object.entries(applied).filter(([, v]) => v)).toString();
  const [rows] = useLoad<any[]>(() => can(ctx.me.role, "audit_read") ? api(`/audit?limit=300&${qs}`) : Promise.resolve([]), [qs], ctx.notify);
  const [open, setOpen] = useState<number | null>(null);
  if (!can(ctx.me.role, "audit_read")) return <><PageHead title="Jejak audit" /><Empty>Peran Anda tidak memiliki akses ke jejak audit.</Empty></>;
  const scoped = ["REGULATORY_ANALYST", "COMPLIANCE_OFFICER"].includes(ctx.me.role);
  return <>
    <PageHead crumbs="Laporan & Audit" title="Jejak audit" intro="Catatan append-only: setiap transisi menyimpan aktor, waktu, status sebelum dan sesudah. Tidak dapat diubah atau dihapus, bahkan oleh administrator.">
      <button className="btn" onClick={() => download(`/audit/export?${qs}`, "rcip_audit_trail.csv").catch(e => ctx.notify("error", e.message))}>Ekspor CSV</button>
    </PageHead>
    {scoped && <div className="notice ok"><span>Lingkup dibatasi: Anda hanya melihat event yang Anda lakukan sendiri.</span></div>}
    <section className="panel"><div className="row">
      <select value={f.object_type} onChange={e => setF({ ...f, object_type: e.target.value })} aria-label="Jenis objek">{TYPES.map(t => <option key={t} value={t}>{t || "Semua objek"}</option>)}</select>
      <input value={f.action} onChange={e => setF({ ...f, action: e.target.value })} placeholder="Aksi, mis. CLOSED" />
      <input value={f.actor} onChange={e => setF({ ...f, actor: e.target.value })} placeholder="Username aktor" />
      <button className="btn primary" onClick={() => setApplied(f)}>Terapkan</button>
    </div></section>
    <section className="panel">{rows?.length ? <div className="tablewrap"><table className="data"><thead><tr><th>Waktu</th><th>Aktor</th><th>Aksi</th><th>Objek</th><th>Perubahan</th></tr></thead>
      <tbody>{rows.map(r => <tr key={r.id} className="clickable" onClick={() => setOpen(open === r.id ? null : r.id)}><td className="small">{fmtTime(r.occurred_at)}</td><td>{r.actor}</td><td><b>{r.action}</b></td>
        <td className="small">{r.object_type}<div className="muted">{r.object_id?.slice(0, 8)}</div></td>
        <td className="small">{open === r.id ? <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{JSON.stringify({ sebelum: r.before, sesudah: r.after }, null, 1)}</pre> : r.after ? Object.entries(r.after).slice(0, 2).map(([k, v]) => `${k}: ${String(v).slice(0, 40)}`).join(" · ") : "—"}</td></tr>)}</tbody></table></div> : <Empty>Tidak ada event untuk saringan ini.</Empty>}</section>
  </>;
}
