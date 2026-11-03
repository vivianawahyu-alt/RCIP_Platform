import { useEffect, useState } from "react";
import type { ChangeEvent } from "react";
import { api } from "../api";
import type { Doc } from "../types";
import type { Ctx } from "../ui";
import { Empty, Flow, PageHead, Status, can, fmtDate, useAction, useLoad } from "../ui";

type Prov = { provision_version_id: string; number_label: string; path: string; text: string; confidence: number; corrected_by_human: boolean };
// Satu kelompok BAB berisi daftar pasalnya (dipakai untuk tampilan BAB → Pasal)
type BabGroup = { bab: string; pasal: Prov[] };

/** Kelompokkan pasal per BAB (array of array): [{ bab: "BAB I", pasal: [Pasal 1, Pasal 2] }, ...].
 *  Sumbernya `path` dari segmenter ("BAB I/Pasal 1"); pasal tanpa BAB masuk grup "Tanpa BAB". Urutan pasal dipertahankan. */
function groupByBab(provs: Prov[]): BabGroup[] {
  const groups: BabGroup[] = [];
  for (const p of provs) {
    const bab = p.path.includes("/") ? p.path.split("/")[0] : "Tanpa BAB";
    const last = groups[groups.length - 1];
    if (last && last.bab === bab) last.pasal.push(p);
    else groups.push({ bab, pasal: [p] });
  }
  return groups;
}

// Halaman "Korpus & pasal": daftar dokumen (kanan) dan isi pasal versi terpilih (kiri)
export function Regulasi({ ctx }: { ctx: Ctx }) {
  const [docs, reload] = useLoad<Doc[]>(() => api("/corpus/documents"), [], ctx.notify);
  const [sel, setSel] = useState<string>("");
  const [provs, setProvs] = useState<Prov[]>([]);
  const [nd, setNd] = useState({ canonical_number: "", title_id: "", instrument_type: "POJK" });
  const { run, busy } = useAction(ctx.notify, reload);
  const analyst = can(ctx.me.role, "corpus_write"), officer = can(ctx.me.role, "obligation_extract");
  useEffect(() => { if (!sel && docs?.[0]?.versions.length) setSel(docs[0].versions[docs[0].versions.length - 1].id); }, [docs]);
  useEffect(() => { if (sel) api<Prov[]>(`/corpus/versions/${sel}/provisions`).then(setProvs).catch(e => ctx.notify("error", e.message)); }, [sel]);
  const selDoc = docs?.find(d => d.versions.some(v => v.id === sel));
  const selVer = selDoc?.versions.find(v => v.id === sel);

  const upload = (e: ChangeEvent<HTMLInputElement>, docId: string) => {
    const f = e.target.files?.[0]; if (!f) return;
    const form = new FormData(); form.append("file", f); form.append("effective_date", new Date().toISOString().slice(0, 10));
    run(async () => { const r = await api(`/corpus/documents/${docId}/versions`, { form }); setSel(r.version_id); }, "Versi baru diunggah dan tersegmentasi. Periksa pasal lalu publikasikan.");
    e.target.value = "";
  };
  const extract = (pv: string) => run(() => api("/compliance/obligations/extract", { body: { provision_version_id: pv } }),
    "Draf kewajiban dibuat dan berlabel Draf AI. Validasi di halaman Kewajiban.");

  return <>
    <PageHead crumbs="Pusat Regulasi" title="Korpus & pasal" intro="Dokumen regulasi terkurasi. Versi yang sudah terbit tidak dapat diubah; setiap kewajiban menyitasi pasal pada versi tertentu." />
    <div className="cols">
      <div>
        {selVer ? <section className="panel">
          <header><div><h2>{selDoc?.canonical_number}</h2><p>{selDoc?.title_id} · versi {selVer.version_number}, berlaku {fmtDate(selVer.effective_date)}</p></div><Status s={selVer.state} /></header>
          {/* Pasal dikelompokkan per BAB; setiap BAB bisa dilipat/dibuka */}
          {provs.length ? groupByBab(provs).map(g => <details key={g.bab} className="bab" open>
            <summary><span className="bab-title">{g.bab}</span> <span className="small muted">{g.pasal.length} pasal</span></summary>
            <ul className="list">{g.pasal.map(p => <li key={p.provision_version_id}>
              <div className="between"><div><b style={{ fontFamily: "var(--serif)", fontSize: 17 }}>{p.number_label}</b> <span className="small muted">keyakinan segmentasi {p.confidence}</span></div>
                {officer && selVer.state === "PUBLISHED" && <button className="btn sm" disabled={busy} onClick={() => extract(p.provision_version_id)}>Ekstrak kewajiban</button>}</div>
              {/* Teks pasal rata kanan-kiri; lang="id" agar pemenggalan kata mengikuti bahasa Indonesia */}
              <div className="verbatim justify" lang="id">{p.text}</div>
            </li>)}</ul>
          </details>) : <Empty>Versi ini belum memiliki pasal.</Empty>}
        </section> : <Empty>Pilih versi dokumen di samping untuk membaca pasalnya.</Empty>}
      </div>
      <aside>
        <section className="panel">
          <h2>Dokumen</h2>
          {docs?.length ? <ul className="list">{docs.map(d => <li key={d.id}>
            <div className="between"><div className="title">{d.canonical_number}</div><Status s={d.status} /></div><div className="sub">{d.issuer} · {d.title_id}</div>
            {!!d.labels?.length && <div className="row" style={{ marginTop: 6, gap: 4 }}>{d.labels.map((l, i) => <span key={i} className={`badge ${l.state === "CONFIRMED" ? "teal" : ""}`} title={`${l.dimension} · ${l.state === "CONFIRMED" ? "terkonfirmasi" : "saran aturan"}`}>{l.value}</span>)}</div>}
            <div className="row" style={{ marginTop: 8 }}>{d.versions.map(v => <span key={v.id} className="row" style={{ gap: 4 }}>
              {/* Tombol pilih versi; versi yang ditarik diberi keterangan "(ditarik)" */}
              <button className={`btn sm ${v.id === sel ? "primary" : ""}`} onClick={() => setSel(v.id)}>v{v.version_number}{v.state === "WITHDRAWN" ? " (ditarik)" : ""}</button>
              {analyst && v.state !== "PUBLISHED" && v.state !== "WITHDRAWN" && <button className="btn sm" disabled={busy} onClick={() => run(() => api(`/corpus/versions/${v.id}/publish`, { method: "POST" }), `Versi ${v.version_number} dipublikasikan dan dibekukan.`)}>Publikasikan</button>}
            </span>)}</div>
            {/* Tombol Hapus/Tarik versi & Hapus dokumen (khusus Analis); kosongkan pilihan bila versi yang dibuka ikut terhapus */}
            {analyst && <CorpusActions doc={d} busy={busy} run={run} onRemoved={id => { if (d.versions.some(v => v.id === sel) && (id === d.id || id === sel)) setSel(""); }} />}
            {analyst && <label className="field" style={{ marginTop: 10 }}>Unggah versi baru (.pdf/.txt)<input type="file" accept=".pdf,.txt" onChange={e => upload(e, d.id)} /></label>}
          </li>)}</ul> : <Empty>Belum ada dokumen.</Empty>}
        </section>
        {selDoc && <DocGovernance key={selDoc.id} doc={selDoc} docs={docs || []} ctx={ctx} onChange={reload} />}
        {analyst && <section className="panel">
          <h2>Daftarkan dokumen</h2>
          <div className="form">
            <label className="field">Nomor regulasi<input value={nd.canonical_number} onChange={e => setNd({ ...nd, canonical_number: e.target.value })} placeholder="POJK 4/POJK.05/2021" /></label>
            <label className="field">Judul<input value={nd.title_id} onChange={e => setNd({ ...nd, title_id: e.target.value })} placeholder="Penerapan Manajemen Risiko bagi Bank Umum" /></label>
            <label className="field">Jenis instrumen<select value={nd.instrument_type} onChange={e => setNd({ ...nd, instrument_type: e.target.value })}>{["UU", "PP", "POJK", "SEOJK", "PBI", "PADG"].map(x => <option key={x}>{x}</option>)}</select></label>
            <button className="btn primary" disabled={busy || !nd.canonical_number || !nd.title_id} onClick={() => run(async () => { await api("/corpus/documents", { body: nd }); setNd({ canonical_number: "", title_id: "", instrument_type: "POJK" }); }, "Dokumen terdaftar. Unggah versi pertamanya.")}>Daftarkan dokumen</button>
          </div>
        </section>}
      </aside>
    </div>
  </>;
}

// Tipe fungsi run() dari useAction: menjalankan aksi API lalu menampilkan pesan sukses/gagal
type Run = (fn: () => Promise<unknown>, okText?: string) => Promise<boolean>;

/** Hapus versi draf / dokumen yang belum pernah terbit; tarik (bukan hapus) versi yang sudah terbit.
 *  Konfirmasi dua langkah di dalam halaman agar tidak terhapus karena salah klik. */
function CorpusActions({ doc, busy, run, onRemoved }: { doc: Doc; busy: boolean; run: Run; onRemoved: (id: string) => void }) {
  // Aksi yang sedang menunggu konfirmasi (null = belum ada yang diklik)
  const [pending, setPending] = useState<{ kind: "version" | "withdraw" | "document"; id: string; label: string } | null>(null);
  // Alasan penarikan (wajib untuk "Tarik versi")
  const [reason, setReason] = useState("");
  // Dokumen yang pernah terbit tidak boleh dihapus → tombol "Hapus dokumen" disembunyikan
  const everPublished = doc.versions.some(v => v.state === "PUBLISHED" || v.state === "WITHDRAWN");
  // Dijalankan saat klik "Ya, hapus/tarik": panggil endpoint sesuai jenis aksi, lalu tutup konfirmasi bila berhasil
  const go = async () => {
    if (!pending) return;
    const ok = pending.kind === "version" ? await run(() => api(`/corpus/versions/${pending.id}`, { method: "DELETE" }), `${pending.label} dihapus.`)
      : pending.kind === "withdraw" ? await run(() => api(`/corpus/versions/${pending.id}/withdraw`, { body: { reason } }), `${pending.label} ditarik dari korpus.`)
      : await run(() => api(`/corpus/documents/${pending.id}`, { method: "DELETE" }), `Dokumen ${doc.canonical_number} dihapus.`);
    if (ok) { onRemoved(pending.id); setPending(null); setReason(""); }
  };
  return <div style={{ marginTop: 8 }}>
    {/* Tahap 1: tombol aksi. Versi terbit → "Tarik", versi draf → "Hapus" */}
    {!pending && <div className="row" style={{ gap: 4 }}>
      {doc.versions.map(v => v.state === "WITHDRAWN" ? null : v.state === "PUBLISHED"
        ? <button key={v.id} className="btn sm ghost" disabled={busy} onClick={() => setPending({ kind: "withdraw", id: v.id, label: `Versi ${v.version_number}` })}>Tarik v{v.version_number}</button>
        : <button key={v.id} className="btn sm ghost danger-text" disabled={busy} onClick={() => setPending({ kind: "version", id: v.id, label: `Versi ${v.version_number}` })}>Hapus v{v.version_number}</button>)}
      {!everPublished && <button className="btn sm ghost danger-text" disabled={busy} onClick={() => setPending({ kind: "document", id: doc.id, label: doc.canonical_number })}>Hapus dokumen</button>}
    </div>}
    {/* Tahap 2: kotak konfirmasi agar tidak terhapus karena salah klik */}
    {pending && <div className="decision" style={{ marginTop: 6 }}>
      <p className="small" style={{ marginTop: 0 }}>{pending.kind === "withdraw"
        ? <>Tarik <b>{pending.label}</b>? Versi tidak lagi dipakai pencarian, copilot, dan ekstraksi, tetapi teks & jejak auditnya tetap tersimpan.</>
        : <>Hapus <b>{pending.label}</b> secara permanen? Tindakan ini tidak dapat dibatalkan dan tercatat di jejak audit.</>}</p>
      {pending.kind === "withdraw" && <input value={reason} onChange={e => setReason(e.target.value)} placeholder="Alasan penarikan (wajib)" style={{ width: "100%", marginBottom: 6 }} />}
      <div className="row"><button className="btn sm danger" disabled={busy || (pending.kind === "withdraw" && !reason.trim())} onClick={go}>{pending.kind === "withdraw" ? "Ya, tarik" : "Ya, hapus"}</button>
        <button className="btn sm ghost" onClick={() => { setPending(null); setReason(""); }}>Batal</button></div>
    </div>}
  </div>;
}

const CHANGE_LABEL: Record<string, string> = { TEXT_MODIFIED: "Teks diubah", PROVISION_ADDED: "Pasal ditambahkan", PROVISION_DELETED: "Pasal dihapus" };
const SEMANTIC = ["DEADLINE_CHANGED", "OBLIGATION_ADDED", "OBLIGATION_REMOVED", "OBLIGATION_MODIFIED", "THRESHOLD_CHANGED", "SCOPE_CHANGED",
  "DEFINITION_CHANGED", "SANCTION_CHANGED", "EFFECTIVE_DATE_CHANGED", "EDITORIAL_ONLY"];
const REVIEW_STEPS: [string, string][] = [["DETECTED", "Terdeteksi"], ["IN_REVIEW", "Direviu"], ["VALIDATED", "Divalidasi analis"], ["MATERIAL_CONFIRMED", "Material dikonfirmasi"]];

export function Perubahan({ ctx }: { ctx: Ctx }) {
  const [docs] = useLoad<Doc[]>(() => api("/corpus/documents"), [], ctx.notify);
  const [sets, reloadSets] = useLoad<any[]>(() => api("/corpus/changesets"), [], ctx.notify);
  const [sel, setSel] = useState<string | null>(null);
  const { run, busy } = useAction(ctx.notify, reloadSets);
  const analyst = can(ctx.me.role, "corpus_write");
  const cmp = (d: Doc) => run(async () => {
    const v = d.versions; const r = await api("/corpus/changes", { body: { base_version_id: v[v.length - 2].id, new_version_id: v[v.length - 1].id } });
    setSel(r.change_set_id);
  }, "Perbandingan selesai. Perubahan belum berdampak apa pun sampai divalidasi analis dan dikonfirmasi Manajer.");
  const multi = docs?.filter(d => d.versions.filter(v => v.state === "PUBLISHED").length > 1) || [];
  const current = sel || sets?.[0]?.id;
  return <>
    <PageHead crumbs="Pusat Regulasi" title="Perubahan regulasi" intro="Diff deterministik antarversi, lalu reviu manusia: analis memvalidasi jenis & materialitas, Manajer Kepatuhan mengonfirmasi (titik kendali 1). Hanya konfirmasi yang menandai kewajiban & keputusan terkait untuk ditinjau." />
    <div className="cols">
      <div>{current ? <ChangeSetView key={current} id={current} ctx={ctx} onChange={reloadSets} /> : <Empty>Belum ada perbandingan versi.</Empty>}</div>
      <aside>
        <section className="panel"><h2>Hasil perbandingan</h2>
          {sets?.length ? <ul className="list">{sets.map(s => <li key={s.id}><button className="rowlink" onClick={() => setSel(s.id)}>
            <div className="title">{s.document} · v{s.base_version} → v{s.new_version}</div>
            <div className="sub">{s.total} perubahan · {Object.entries(s.states).map(([k, v]) => `${v} ${k.toLowerCase().replace("_", " ")}`).join(", ")}</div>
          </button></li>)}</ul> : <Empty>Belum ada.</Empty>}
        </section>
        {analyst && <section className="panel"><h2>Bandingkan versi</h2>
          {multi.length ? <ul className="list">{multi.map(d => <li key={d.id} className="between"><span className="small"><b>{d.canonical_number}</b></span>
            <button className="btn sm" disabled={busy} onClick={() => cmp(d)}>Bandingkan</button></li>)}</ul> : <p className="muted small">Tidak ada dokumen dengan dua versi terbit.</p>}
        </section>}
      </aside>
    </div>
  </>;
}

function ChangeSetView({ id, ctx, onChange }: { id: string; ctx: Ctx; onChange: () => void }) {
  const [cs, reload] = useLoad<any>(() => api(`/corpus/changesets/${id}`), [id], ctx.notify);
  if (!cs) return <div className="panel">Memuat…</div>;
  return <section className="panel">
    <header><div><h2>{cs.document}: v{cs.base_version} → v{cs.new_version}</h2><p>{cs.title}</p></div></header>
    {cs.changes.length ? <ul className="list">{cs.changes.map((c: any) => <ChangeItem key={c.id} c={c} ctx={ctx} onDone={() => { reload(); onChange(); }} />)}</ul> : <Empty>Tidak ada perubahan.</Empty>}
  </section>;
}

function ChangeItem({ c, ctx, onDone }: { c: any; ctx: Ctx; onDone: () => void }) {
  const [f, setF] = useState({ material: c.is_material, semantic_type: c.change_type === "PROVISION_ADDED" ? "OBLIGATION_ADDED" : "DEADLINE_CHANGED", reason: "" });
  const [q, setQ] = useState(""), [why, setWhy] = useState("");
  const { run, busy } = useAction(ctx.notify, onDone);
  const role = ctx.me.role;
  return <li>
    <div className="between"><div className="row"><b style={{ fontFamily: "var(--serif)" }}>{c.provision}</b><span className="badge">{CHANGE_LABEL[c.change_type] || c.change_type}</span>
      {c.is_material ? <span className="badge amber" title="Indikasi deterministik, bukan keputusan">Indikasi material</span> : <span className="badge">Indikasi non-material</span>}
      <span className="small muted">kemiripan {c.similarity}</span></div><Status s={c.review_state} /></div>
    {c.review_state !== "REJECTED" && c.review_state !== "ESCALATED" && <div style={{ marginTop: 8 }}><Flow steps={REVIEW_STEPS} now={c.review_state} /></div>}
    {/* diff_html di-escape di server; hanya tag <ins>/<del> yang dihasilkan */}
    {c.diff_html && <div className="verbatim" dangerouslySetInnerHTML={{ __html: c.diff_html }} />}
    {c.review_reason && <p className="small">Analis {c.validated_by}: {c.semantic_type} — {c.review_reason}</p>}
    {c.legal_question && <p className="small">Pertanyaan hukum: {c.legal_question}{c.legal_answer && <><br />Posisi hukum: {c.legal_answer}</>}</p>}
    {c.return_reason && <p className="small" style={{ color: "var(--red)" }}>Dikembalikan Manajer: {c.return_reason}</p>}
    {c.review_state === "MATERIAL_CONFIRMED" && <div className="notice ok"><span>Dikonfirmasi {c.confirmed_by}. Ditandai untuk ditinjau: {c.impact?.obligations?.length || 0} kewajiban, {c.impact?.applicability_decisions?.length || 0} keputusan keberlakuan, {c.impact?.controls?.length || 0} kontrol.{c.impact?.note ? ` ${c.impact.note}` : ""}</span></div>}
    {role === "REGULATORY_ANALYST" && ["DETECTED", "IN_REVIEW"].includes(c.review_state) && <div className="decision"><h4>Validasi perubahan</h4><div className="form">
      <div className="form-2">
        <label className="field">Penilaian materialitas<select value={f.material ? "1" : "0"} onChange={e => setF({ ...f, material: e.target.value === "1" })}><option value="1">Material — ajukan konfirmasi</option><option value="0">Tidak material — tolak</option></select></label>
        <label className="field">Jenis perubahan<select value={f.semantic_type} onChange={e => setF({ ...f, semantic_type: e.target.value })}>{SEMANTIC.map(x => <option key={x}>{x}</option>)}</select></label>
      </div>
      <label className="field">Alasan<input value={f.reason} onChange={e => setF({ ...f, reason: e.target.value })} placeholder="mis. tenggat pelaporan dipercepat" /></label>
      <div className="row"><button className="btn primary" disabled={busy || !f.reason} onClick={() => run(() => api(`/corpus/changes/${c.id}/validate`, { body: f }), "Penilaian perubahan tersimpan.")}>Simpan validasi</button>
        <input className="grow" value={q} onChange={e => setQ(e.target.value)} placeholder="Pertanyaan untuk Peninjau Hukum" />
        <button className="btn" disabled={busy || !q} onClick={() => run(() => api(`/corpus/changes/${c.id}/escalate`, { body: { question: q } }), "Diteruskan ke Peninjau Hukum.")}>Eskalasi</button></div>
    </div></div>}
    {role === "LEGAL_REVIEWER" && c.review_state === "ESCALATED" && <div className="decision"><h4>Posisi hukum</h4>
      <div className="row"><input className="grow" value={why} onChange={e => setWhy(e.target.value)} placeholder="Posisi hukum beserta sitasi" />
        <button className="btn primary" disabled={busy || !why} onClick={() => run(() => api(`/corpus/changes/${c.id}/legal-answer`, { body: { answer: why } }), "Posisi hukum tercatat; kembali ke analis.")}>Kirim</button></div></div>}
    {role === "COMPLIANCE_MANAGER" && c.review_state === "VALIDATED" && <div className="decision"><h4>Konfirmasi materialitas (titik kendali 1)</h4>
      <p className="small" style={{ marginTop: 0 }}>Konfirmasi akan menandai kewajiban dan keputusan keberlakuan yang menyitasi pasal ini menjadi Perlu ditinjau. Tidak ada yang disunting otomatis.</p>
      <div className="row"><input className="grow" value={why} onChange={e => setWhy(e.target.value)} placeholder="Alasan (wajib bila dikembalikan)" />
        <button className="btn primary" disabled={busy} onClick={() => run(() => api(`/corpus/changes/${c.id}/confirm-materiality`, { body: { outcome: "APPROVED", reason: why } }), "Materialitas dikonfirmasi; dampak hilir ditandai.")}>Konfirmasi material</button>
        <button className="btn danger" disabled={busy || !why} onClick={() => run(() => api(`/corpus/changes/${c.id}/confirm-materiality`, { body: { outcome: "REJECTED", reason: why } }), "Dikembalikan ke analis.")}>Kembalikan</button></div></div>}
  </li>;
}

function DocGovernance({ doc, docs, ctx, onChange }: { doc: Doc; docs: Doc[]; ctx: Ctx; onChange: () => void }) {
  const [labels, reloadL] = useLoad<any[]>(() => api(`/corpus/documents/${doc.id}/labels`), [doc.id], ctx.notify);
  const [rels, reloadR] = useLoad<any[]>(() => api(`/corpus/relationships?document_id=${doc.id}`), [doc.id], ctx.notify);
  const [rf, setRf] = useState({ target_document_id: "", relation_type: "AMENDS", citing: "" });
  const [provs, setProvs] = useState<Prov[]>([]);
  useEffect(() => { const v = doc.versions[doc.versions.length - 1]; if (v) api<Prov[]>(`/corpus/versions/${v.id}/provisions`).then(setProvs).catch(() => setProvs([])); }, [doc.id]);
  const { run, busy } = useAction(ctx.notify, () => { reloadL(); reloadR(); onChange(); });
  const analyst = can(ctx.me.role, "corpus_write"), manager = ctx.me.role === "COMPLIANCE_MANAGER";
  return <section className="panel"><h2>Klasifikasi & silsilah</h2>
    <p className="muted small" style={{ marginTop: 2 }}>Label dari taksonomi terkendali; saran aturan perlu dikonfirmasi analis.</p>
    {labels?.length ? <ul className="list">{labels.map(l => <li key={l.id} className="between"><span className="small"><b>{l.value}</b> <span className="muted">{l.dimension}</span></span>
      <span className="row"><Status s={l.state === "SUGGESTED" ? "SUBMITTED" : l.state === "CONFIRMED" ? "ACCEPTED" : "REJECTED"} />
        {analyst && l.state === "SUGGESTED" && <button className="btn sm" disabled={busy} onClick={() => run(() => api(`/corpus/labels/${l.id}/confirm`, { method: "POST" }), "Label dikonfirmasi.")}>Konfirmasi</button>}
        {analyst && l.state !== "REMOVED" && <button className="btn sm ghost" disabled={busy} onClick={() => run(() => api(`/corpus/labels/${l.id}/remove`, { body: { reason: "Tidak sesuai isi dokumen" } }), "Label dihapus dengan alasan.")}>Hapus</button>}</span></li>)}</ul> : <p className="small muted">Belum ada label.</p>}
    <h3 style={{ fontSize: 16, marginTop: 14 }}>Relasi dokumen</h3>
    {rels?.length ? <ul className="list">{rels.map(r => <li key={r.id} className="between"><span className="small">{r.source} <b>{r.relation_type}</b> {r.target}</span>
      <span className="row"><Status s={r.state === "PROPOSED" ? "SUBMITTED" : r.state === "CONFIRMED" ? "ACCEPTED" : "REJECTED"} />
        {(analyst || manager) && r.state === "PROPOSED" && <button className="btn sm" disabled={busy} onClick={() => run(() => api(`/corpus/relationships/${r.id}/confirm`, { method: "POST" }), "Relasi dikonfirmasi; status dokumen target diperbarui.")}>Konfirmasi</button>}</span></li>)}</ul> : <p className="small muted">Belum ada relasi.</p>}
    {analyst && <div className="form" style={{ marginTop: 8 }}>
      <div className="form-2"><label className="field">Dokumen ini…<select value={rf.relation_type} onChange={e => setRf({ ...rf, relation_type: e.target.value })}>{["AMENDS", "REVOKES", "PARTIALLY_REVOKES", "REFERS_TO", "IMPLEMENTS"].map(x => <option key={x}>{x}</option>)}</select></label>
        <label className="field">Dokumen target<select value={rf.target_document_id} onChange={e => setRf({ ...rf, target_document_id: e.target.value })}><option value="">Pilih</option>{docs.filter(d => d.id !== doc.id).map(d => <option key={d.id} value={d.id}>{d.canonical_number}</option>)}</select></label></div>
      <label className="field">Pasal penetap (wajib untuk konfirmasi)<select value={rf.citing} onChange={e => setRf({ ...rf, citing: e.target.value })}><option value="">Pilih pasal</option>{provs.map(p => <option key={p.provision_version_id} value={p.provision_version_id}>{p.number_label}</option>)}</select></label>
      <div><button className="btn" disabled={busy || !rf.target_document_id} onClick={() => run(() => api("/corpus/relationships", { body: { source_document_id: doc.id, target_document_id: rf.target_document_id, relation_type: rf.relation_type, citing_provision_version_id: rf.citing || null } }), "Relasi diusulkan.")}>Usulkan relasi</button></div>
    </div>}
  </section>;
}
