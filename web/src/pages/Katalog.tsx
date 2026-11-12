import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api";
import type { CatalogPage, Facets } from "../types";
import type { Ctx } from "../ui";
import { Empty, PageHead, Status, fmtDate, useLoad } from "../ui";

const PAGE = 20;
const SORTS: [string, string][] = [["newest", "Terbaru"], ["oldest", "Terlama"], ["title", "Judul A–Z"]];
const NO_FILTER = { instrument_type: "", status: "", year: "", issuer: "", label: "" };

export function Katalog({ ctx }: { ctx: Ctx }) {
  const [q, setQ] = useState(""), [applied, setApplied] = useState("");
  const [f, setF] = useState(NO_FILTER);
  const [sort, setSort] = useState("newest"), [offset, setOffset] = useState(0);
  const [facets] = useLoad<Facets>(() => api("/corpus/facets"), [], ctx.notify);
  const [page] = useLoad<CatalogPage>(() => {
    const p = new URLSearchParams({ sort, limit: String(PAGE), offset: String(offset) });
    if (applied) p.set("q", applied);
    (Object.keys(f) as (keyof typeof f)[]).forEach(k => f[k] && p.set(k, f[k]));
    return api(`/corpus/catalog?${p}`);
  }, [applied, f, sort, offset], ctx.notify);

  const submit = (e: FormEvent) => { e.preventDefault(); setOffset(0); setApplied(q.trim()); };
  const setFilter = (k: keyof typeof f, v: string) => { setOffset(0); setF({ ...f, [k]: v }); };
  const active = Object.values(f).some(Boolean) || !!applied;
  const total = page?.total ?? 0;
  const opts = (xs?: { value: string | number; count: number }[]) => (xs || []).map(x => <option key={x.value} value={x.value}>{x.value} ({x.count})</option>);

  return <>
    <PageHead crumbs="Pusat Regulasi" title="Katalog peraturan" intro="Telusuri seluruh peraturan di korpus berdasarkan nomor, judul, jenis, tahun, penerbit, status, dan label. Klik peraturan untuk melihat pasal, versi, dan relasinya." />
    <section className="panel">
      <form className="row" onSubmit={submit} style={{ marginBottom: 14 }}>
        <input style={{ flex: 1, minWidth: 240 }} value={q} onChange={e => setQ(e.target.value)} placeholder="Nomor atau judul — mis. teknologi informasi bank umum" aria-label="Cari nomor atau judul peraturan" />
        <button className="btn primary" type="submit">Cari peraturan</button>
      </form>
      <div className="filters">
        <label className="field">Jenis<select value={f.instrument_type} onChange={e => setFilter("instrument_type", e.target.value)}><option value="">Semua</option>{opts(facets?.instrument_type)}</select></label>
        <label className="field">Status<select value={f.status} onChange={e => setFilter("status", e.target.value)}><option value="">Semua</option>{opts(facets?.status)}</select></label>
        <label className="field">Tahun<select value={f.year} onChange={e => setFilter("year", e.target.value)}><option value="">Semua</option>{opts(facets?.year)}</select></label>
        <label className="field">Penerbit<select value={f.issuer} onChange={e => setFilter("issuer", e.target.value)}><option value="">Semua</option>{opts(facets?.issuer)}</select></label>
        <label className="field">Label<select value={f.label} onChange={e => setFilter("label", e.target.value)}><option value="">Semua</option>
          {(facets?.label || []).map(l => <option key={`${l.dimension}:${l.value}`} value={l.value}>{l.value} ({l.count})</option>)}</select></label>
        <label className="field">Urutkan<select value={sort} onChange={e => { setOffset(0); setSort(e.target.value); }}>{SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
      </div>
      {active && <div className="row small" style={{ marginTop: 10 }}>
        <span className="muted">Filter aktif{applied ? ` · kata kunci “${applied}”` : ""}</span>
        <button className="btn sm ghost" onClick={() => { setF(NO_FILTER); setQ(""); setApplied(""); setOffset(0); }}>Hapus semua filter</button>
      </div>}
    </section>

    <section className="panel">
      <div className="between"><h2>{page ? `${total} peraturan` : "Memuat…"}</h2>
        {total > 0 && <span className="small muted">Menampilkan {offset + 1}–{Math.min(offset + PAGE, total)} dari {total}</span>}</div>
      {page?.items.length ? <ul className="list">{page.items.map(d => <li key={d.id}>
        <div className="between">
          <button className="rowlink" onClick={() => ctx.go(`peraturan/${d.id}`)}><div className="title">{d.number_display}</div></button>
          <Status s={d.status} />
        </div>
        <div className="sub">{d.title_id}</div>
        <div className="row" style={{ marginTop: 6, gap: 6 }}>
          <span className="badge">{d.instrument_type}</span>
          {d.year && <span className="badge">{d.year}</span>}
          <span className="small muted">{d.issuer}</span>
          <span className="small muted">· {d.published_count ? `${d.published_count} versi terbit, berlaku sejak ${fmtDate(d.latest_effective_date)}` : "belum ada versi terbit"}</span>
          {d.labels.map((l, i) => <span key={i} className={`badge ${l.state === "CONFIRMED" ? "teal" : ""}`}>{l.value}</span>)}
        </div>
      </li>)}</ul> : page ? <Empty>Tidak ada peraturan yang cocok. Coba kurangi filter atau ubah kata kunci.</Empty> : null}
      {total > PAGE && <div className="row" style={{ marginTop: 14 }}>
        <button className="btn sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>← Sebelumnya</button>
        <button className="btn sm" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>Berikutnya →</button>
      </div>}
    </section>
  </>;
}