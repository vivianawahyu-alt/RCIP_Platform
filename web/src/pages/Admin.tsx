import { useState } from "react";
import { api } from "../api";
import type { User } from "../types";
import type { Ctx } from "../ui";
import { Empty, PageHead, ROLE_LABEL, fmtTime, useAction, useLoad } from "../ui";

export function Admin({ ctx }: { ctx: Ctx }) {
  const [cfg, reload] = useLoad<any[]>(() => api("/config"), [], ctx.notify);
  const [users] = useLoad<User[]>(() => api("/users"), [], ctx.notify);
  const canMetrics = ["SYSTEM_ADMINISTRATOR", "INTERNAL_AUDITOR"].includes(ctx.me.role);
  const [metrics] = useLoad<any>(() => canMetrics ? api("/metrics") : Promise.resolve(null), [], ctx.notify);
  const [edit, setEdit] = useState<Record<string, { value: string; why: string }>>({});
  const { run, busy } = useAction(ctx.notify, reload);
  const admin = ctx.me.role === "SYSTEM_ADMINISTRATOR";
  return <>
    <PageHead crumbs="Laporan & Audit" title="Administrasi" intro="Parameter runtime yang dapat disetel beserta batasnya. Setiap perubahan wajib berjustifikasi dan tercatat di jejak audit. Tidak ada parameter yang dapat mematikan audit, pemisahan tugas, atau label AI." />
    <section className="panel"><h2>Konfigurasi</h2>
      {cfg?.length ? <div className="tablewrap"><table className="data"><thead><tr><th>Parameter</th><th>Nilai</th><th>Batas</th><th>Terakhir diubah</th>{admin && <th>Ubah</th>}</tr></thead>
        <tbody>{cfg.map(c => <tr key={c.key}><td><b>{c.key}</b><div className="small muted">{c.description}</div></td><td>{c.value}{c.value !== c.default && <div className="small muted">bawaan {c.default}</div>}</td>
          <td className="small">{c.min} – {c.max}</td><td className="small">{c.updated_by ? `${c.updated_by} · ${fmtTime(c.updated_at)}` : "—"}</td>
          {admin && <td><div className="row" style={{ flexWrap: "nowrap" }}>
            <input style={{ width: 80 }} type="number" step="any" value={edit[c.key]?.value ?? ""} placeholder={String(c.value)} onChange={e => setEdit({ ...edit, [c.key]: { value: e.target.value, why: edit[c.key]?.why || "" } })} />
            <input style={{ width: 160 }} value={edit[c.key]?.why ?? ""} placeholder="Justifikasi" onChange={e => setEdit({ ...edit, [c.key]: { value: edit[c.key]?.value || "", why: e.target.value } })} />
            <button className="btn sm" disabled={busy || !edit[c.key]?.value || !edit[c.key]?.why} onClick={() => run(async () => { await api(`/config/${c.key}`, { method: "PUT", body: { value: Number(edit[c.key].value), justification: edit[c.key].why } }); setEdit({ ...edit, [c.key]: { value: "", why: "" } }); }, `${c.key} diperbarui.`)}>Simpan</button></div></td>}</tr>)}</tbody></table></div> : <Empty>Belum ada konfigurasi.</Empty>}
      {!admin && <p className="hint">Hanya Administrator Sistem yang dapat mengubah parameter.</p>}
    </section>
    <div className="cols-even">
      <section className="panel"><h2>Pengguna & peran</h2><ul className="list">{(users || []).map(u => <li key={u.id} className="between small"><b>{u.username}</b><span>{ROLE_LABEL[u.role]}</span></li>)}</ul></section>
      {metrics && <section className="panel"><h2>Metrik layanan</h2><p className="small muted">Uptime {Math.round(metrics.uptime_seconds / 60)} menit</p>
        <ul className="list">{Object.entries(metrics.events).map(([k, v]) => <li key={k} className="between small"><span>{k}</span><b>{String(v)}</b></li>)}</ul>
        <h3 style={{ fontSize: 15, marginTop: 10 }}>Endpoint tersibuk</h3>
        <ul className="list">{Object.entries(metrics.routes).sort((a: any, b: any) => b[1].requests - a[1].requests).slice(0, 8).map(([k, v]: any) => <li key={k} className="between small"><span>{k}</span><span>{v.requests} req · {v.avg_ms} ms · {v.errors} error</span></li>)}</ul>
      </section>}
    </div>
  </>;
}
