import { api } from "../api";
import type { Ctx } from "../ui";
import { Empty, PageHead, useLoad } from "../ui";
import { RelasiItem } from "./Regulasi";

// Antrian Peninjau Hukum: semua permintaan yang menunggu posisi hukum dikumpulkan di satu halaman,
// ditambah usulan relasi yang menunggu persetujuan Manajer (legal boleh memberi catatan / minta revisi).
export function AntrianLegal({ ctx }: { ctx: Ctx }) {
  const [q] = useLoad<any>(() => api("/compliance/legal-queue"), [], ctx.notify);
  const [rels, reloadRels] = useLoad<any[]>(() => api("/corpus/relationships"), [], ctx.notify);
  const pendingRels = (rels || []).filter(r => r.state === "PROPOSED");
  const total = (q?.changes.length || 0) + (q?.applicability.length || 0) + (q?.obligations.length || 0);
  return <>
    <PageHead crumbs="Peninjau Hukum" title="Antrian hukum"
      intro="Semua eskalasi yang menunggu posisi hukum Anda, dari tinjauan perubahan, keberlakuan, dan kewajiban. Relasi yang menunggu persetujuan Manajer juga dapat diberi catatan atau diminta revisi di sini." />

    <section className="panel" style={{ marginBottom: 20 }}><h2>Menunggu posisi hukum ({total})</h2>
      {q && total === 0 && <Empty>Tidak ada eskalasi yang menunggu posisi hukum.</Empty>}
      <ul className="list">
        {q?.changes.map((c: any) => <li key={c.id} className="between">
          <span className="small"><b>Perubahan</b> · {c.document} {c.versions} · {c.provision}<br /><span className="muted">{c.question}</span></span>
          <button className="btn sm" onClick={() => ctx.go(`perubahan/${c.change_set_id}`)}>Buka</button></li>)}
        {q?.applicability.map((d: any) => <li key={d.id} className="between">
          <span className="small"><b>Keberlakuan</b> · {d.document} v{d.version_number}<br /><span className="muted">{d.question}</span></span>
          <button className="btn sm" onClick={() => ctx.go("keberlakuan")}>Buka</button></li>)}
        {q?.obligations.map((o: any) => <li key={o.id} className="between">
          <span className="small"><b>Kewajiban</b> · {o.citation} · {o.summary}<br /><span className="muted">{o.question}</span></span>
          <button className="btn sm" onClick={() => ctx.go("kewajiban")}>Buka</button></li>)}
      </ul>
    </section>

    <section className="panel"><h2>Relasi menunggu persetujuan ({pendingRels.length})</h2>
      {rels && pendingRels.length === 0 && <Empty>Tidak ada relasi yang menunggu persetujuan.</Empty>}
      <ul className="list">{pendingRels.map(r => <RelasiItem key={r.id} r={r} provs={[]} ctx={ctx} onDone={reloadRels} />)}</ul>
    </section>
  </>;
}