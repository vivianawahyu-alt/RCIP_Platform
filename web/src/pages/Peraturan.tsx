import { useEffect, useState } from "react";
import { api, openFile } from "../api";
import { canDo } from "../permissions";
import type { AsOf, DocDetail } from "../types";
import type { Ctx } from "../ui";
import { Empty, PageHead, Status, fmtDate, useLoad } from "../ui";

type Prov = { provision_version_id: string; number_label: string; path: string; text: string };
type View = { title: string; note?: string; provs: Prov[] };

// Halaman detail satu peraturan (hanya baca). Mengubah data/tanggal berlaku dilakukan di "Korpus & pasal" (Analis).
export function Peraturan({ ctx, id }: { ctx: Ctx; id?: string }) {
  const [d] = useLoad<DocDetail | null>(() => id ? api(`/corpus/documents/${id}`) : Promise.resolve(null), [id], ctx.notify);
  const [view, setView] = useState<View | null>(null);
  const [asOf, setAsOf] = useState("");

  const openVersion = (vid: string, title: string) =>
    api<Prov[]>(`/corpus/versions/${vid}/provisions`).then(p => setView({ title, provs: p })).catch(e => ctx.notify("error", e.message));

  // buka otomatis versi terbit terbaru (atau versi terakhir bila belum ada yang terbit)
  useEffect(() => {
    setView(null); setAsOf("");
    if (!d || !d.versions.length) return;
    const v = [...d.versions].reverse().find(x => x.state === "PUBLISHED") || d.versions[d.versions.length - 1];
    openVersion(v.id, `Versi ${v.version_number} · berlaku ${fmtDate(v.effective_date)}`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d?.id]);

  const showAsOf = () => api<AsOf>(`/corpus/documents/${id}/as-of?as_of=${asOf}`).then(r => {
    if (!r.version) setView({ title: `Per ${fmtDate(asOf)}`, provs: [], note: r.earliest_effective_date
      ? `Belum ada versi terbit yang berlaku pada tanggal ini. Versi pertama berlaku sejak ${fmtDate(r.earliest_effective_date)}.`
      : "Peraturan ini belum memiliki versi terbit." });
    else setView({ title: `Per ${fmtDate(asOf)} · versi ${r.version.version_number} (berlaku ${fmtDate(r.version.effective_date)})`, provs: r.provisions,
      note: r.later_version ? `Catatan: ada versi lebih baru yang berlaku sejak ${fmtDate(r.later_version)}.` : undefined });
  }).catch(e => ctx.notify("error", e.message));

  if (!id) return <Empty>Pilih peraturan dari Katalog.</Empty>;
  if (!d) return <Empty>Memuat…</Empty>;
  const groups = d.relations.reduce<Record<string, typeof d.relations>>((acc, r) => { (acc[r.label] ||= []).push(r); return acc; }, {});

  return <>
    <PageHead crumbs="Pusat Regulasi · Katalog peraturan" title={d.number_display} intro={d.title_id}>
      <button className="btn" onClick={() => ctx.go("katalog")}>← Kembali ke katalog</button>
    </PageHead>
    <div className="cols">
      <div>
        <section className="panel">
          <header><div><h2>Isi peraturan</h2><p>{view?.title || "Belum ada versi"}</p></div></header>
          <div className="row" style={{ marginBottom: 12 }}>
            <label className="field" style={{ margin: 0 }}>Berlaku per tanggal<input type="date" value={asOf} onChange={e => setAsOf(e.target.value)} /></label>
            <button className="btn" disabled={!asOf} onClick={showAsOf} style={{ alignSelf: "flex-end" }}>Tampilkan</button>
          </div>
          {view?.note && <div className="notice warn"><span>{view.note}</span></div>}
          {view?.provs.length ? <ul className="list">{view.provs.map(p => <li key={p.provision_version_id}>
            <div className="between"><div className="title">{p.number_label}</div>
              <button className="btn sm ghost" onClick={() => ctx.openCite(p.provision_version_id)}>Sitasi</button></div>
            <div className="small muted">{p.path}</div>
            <div className="verbatim" style={{ fontSize: 15 }}>{p.text}</div>
          </li>)}</ul> : !view?.note && <Empty>Versi ini belum memiliki pasal.</Empty>}
        </section>
      </div>
      <aside>
        <section className="panel">
          <header><div><h2>Informasi</h2></div><Status s={d.status} /></header>
          <dl className="doc-meta">
            <dt>Jenis</dt><dd>{d.instrument_type}</dd>
            <dt>Penerbit</dt><dd>{d.issuer}</dd>
            <dt>Sumber</dt><dd>{d.source?.name || "—"}</dd>
            <dt>Tahun</dt><dd>{d.year ?? "—"}</dd>
            <dt>Ditetapkan</dt><dd>{fmtDate(d.enacted_date)}</dd>
            <dt>Diundangkan</dt><dd>{fmtDate(d.promulgated_date)}</dd>
            <dt>Lembaran</dt><dd>{d.gazette_ref || "—"}</dd>
          </dl>
          {!!d.labels.length && <div className="row" style={{ marginTop: 10, gap: 4 }}>{d.labels.map((l, i) => <span key={i} className={`badge ${l.state === "CONFIRMED" ? "teal" : ""}`} title={l.dimension}>{l.value}</span>)}</div>}
          {canDo(ctx.me.role, "doc_status", "U") && <button className="btn sm" style={{ marginTop: 12 }} onClick={() => ctx.go("regulasi")}>Ubah data di Korpus & pasal</button>}
        </section>

        <section className="panel">
          <h2>Versi</h2>
          {d.versions.length ? <ul className="list">{d.versions.map(v => <li key={v.id}>
            <div className="between"><div className="title">Versi {v.version_number}</div><Status s={v.state} /></div>
            <div className="sub">Berlaku {fmtDate(v.effective_date)} · {v.provision_count} pasal{v.extraction_method === "OCR" ? " · teks via OCR" : ""}</div>
            {v.origin_url && <div className="small muted">URL asal: <a href={v.origin_url} target="_blank" rel="noreferrer">{v.origin_url}</a></div>}
            <div className="row" style={{ marginTop: 6 }}>
              <button className="btn sm" onClick={() => openVersion(v.id, `Versi ${v.version_number} · berlaku ${fmtDate(v.effective_date)}`)}>Lihat pasal</button>
              {v.has_file && <button className="btn sm" onClick={() => openFile(`/corpus/versions/${v.id}/file`).catch(e => ctx.notify("error", e.message))}>Lihat berkas asli</button>}
            </div>
          </li>)}</ul> : <Empty>Belum ada versi.</Empty>}
        </section>

        <section className="panel">
          <h2>Relasi dengan peraturan lain</h2>
          {Object.keys(groups).length ? Object.entries(groups).map(([label, rs]) => <div key={label} style={{ marginBottom: 10 }}>
            <div className="small muted" style={{ textTransform: "capitalize" }}>{label}</div>
            <ul className="list">{rs.map(r => <li key={r.id}>
              <button className="rowlink" onClick={() => ctx.go(`peraturan/${r.other.id}`)}><div className="title">{r.other.canonical_number}</div></button>
              <div className="sub">{r.other.title_id}</div>
              {r.state !== "CONFIRMED" && <span className="badge amber" title="Relasi belum dikonfirmasi">usulan</span>}
              {r.note && <div className="small muted">{r.note}</div>}
            </li>)}</ul>
          </div>) : <Empty>Belum ada relasi tercatat. Analis dapat mengusulkannya di halaman Korpus & pasal.</Empty>}
          {!!d.cited_by.length && <p className="small muted">Dikutip oleh {d.cited_by.length} peraturan lain.</p>}
        </section>
      </aside>
    </div>
  </>;
}