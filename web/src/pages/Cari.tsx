import { useState } from "react";
import { api } from "../api";
import { canDo } from "../permissions";
import type { Facets, Finding, Obligation } from "../types";
import type { Ctx } from "../ui";
import { Cite, Empty, Highlight, PageHead, Sev, Status, fmtDate, useLoad } from "../ui";


export function Cari({ ctx, kind, q }: { ctx: Ctx; kind: string; q: string }) {
  // hanya jenis hasil yang boleh dibaca peran ini (Kewajiban = baca Obligation, Temuan = baca Finding)
  const allowedKind = (k: string) => k === "Kewajiban" ? canDo(ctx.me.role, "obligation", "R") : k === "Temuan" ? canDo(ctx.me.role, "finding", "R") : true;
  const want = (k: string) => (kind === "Semua" || kind === k) && allowedKind(k);
    // filter pencarian pasal: jenis, status, tahun, dan "berlaku per tanggal"
  const [flt, setFlt] = useState({ instrument_type: "", status: "", year: "", as_of: "" });
  const [facets] = useLoad<Facets>(() => api("/corpus/facets"), [], ctx.notify);
  const [hits] = useLoad<any[]>(() => {
    if (!want("Peraturan")) return Promise.resolve([]);
    const p = new URLSearchParams({ q });
    (Object.keys(flt) as (keyof typeof flt)[]).forEach(k => flt[k] && p.set(k, flt[k]));
    return api(`/corpus/search?${p}`);
  }, [q, kind, flt], ctx.notify);
  const [obs] = useLoad<Obligation[]>(() => want("Kewajiban") ? api("/compliance/obligations") : Promise.resolve([]), [q, kind], ctx.notify);
  const [fs] = useLoad<Finding[]>(() => want("Temuan") ? api("/compliance/findings") : Promise.resolve([]), [q, kind], ctx.notify);
  const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
  const match = (s?: string | null) => !!s && terms.every(t => s.toLowerCase().includes(t));
  const ob = (obs || []).filter(o => match(`${o.summary} ${o.original_text} ${o.citation.canonical_number} ${o.citation.number_label}`));
  const fd = (fs || []).filter(f => match(`${f.title} ${f.description}`));
  return <>
    <PageHead crumbs={`Pencarian · ${kind}`} title={`Hasil untuk “${q}”`} />
    {want("Peraturan") && <section className="panel"><h2>Peraturan ({hits?.length ?? 0})</h2>
          <div className="filters" style={{ margin: "8px 0 12px" }}>
        <label className="field">Jenis<select value={flt.instrument_type} onChange={e => setFlt({ ...flt, instrument_type: e.target.value })}><option value="">Semua</option>{(facets?.instrument_type || []).map(x => <option key={x.value} value={x.value}>{x.value}</option>)}</select></label>
        <label className="field">Status<select value={flt.status} onChange={e => setFlt({ ...flt, status: e.target.value })}><option value="">Semua</option>{(facets?.status || []).map(x => <option key={x.value} value={x.value}>{x.value}</option>)}</select></label>
        <label className="field">Tahun<select value={flt.year} onChange={e => setFlt({ ...flt, year: e.target.value })}><option value="">Semua</option>{(facets?.year || []).map(x => <option key={x.value} value={x.value}>{x.value}</option>)}</select></label>
        <label className="field">Berlaku per tanggal<input type="date" value={flt.as_of} onChange={e => setFlt({ ...flt, as_of: e.target.value })} /></label>
      </div>
      {hits?.length ? <ul className="list">{hits.map(h => <li key={h.provision_version_id}><Cite c={h} onOpen={ctx.openCite} /> <span className="small muted">versi {h.version_number} · berlaku {fmtDate(h.effective_date)} · {h.instrument_type}{h.year ? ` ${h.year}` : ""}</span> <button className="btn sm ghost" onClick={() => ctx.go(`peraturan/${h.document_id}`)}>Buka peraturan</button><div className="verbatim" style={{ fontSize: 15 }}>{h.snippet ? <Highlight text={h.snippet} /> : h.text}</div></li>)}</ul> : <Empty>Tidak ada pasal terbit yang cocok. Pencarian memakai kata dasar bahasa Indonesia.</Empty>}</section>}
    {want("Kewajiban") && <section className="panel"><h2>Kewajiban ({ob.length})</h2>
      {ob.length ? <ul className="list">{ob.map(o => <li key={o.id}><button className="rowlink" onClick={() => ctx.go("kewajiban")}><div className="title">{o.summary}</div></button><div className="row small"><Cite c={o.citation} onOpen={ctx.openCite} /><Status s={o.state} /></div></li>)}</ul> : <Empty>Tidak ada kewajiban yang cocok.</Empty>}</section>}
    {want("Temuan") && <section className="panel"><h2>Temuan ({fd.length})</h2>
      {fd.length ? <ul className="list">{fd.map(f => <li key={f.id}><button className="rowlink" onClick={() => ctx.go(`temuan/${f.id}`)}><div className="title">{f.title}</div><div className="row small"><Sev s={f.severity} /><Status s={f.state} /></div></button></li>)}</ul> : <Empty>Tidak ada temuan yang cocok.</Empty>}</section>}
  </>;
}