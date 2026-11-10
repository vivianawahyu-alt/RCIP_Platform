import { useEffect, useState } from "react";
import { canDo } from "../permissions";
import { ApiError, api, openFile } from "../api";
import type { Doc, Source } from "../types";
import type { Ctx } from "../ui";
import { Empty, Flow, PageHead, PasalText, Status, can, fmtDate, useAction, useLoad } from "../ui";

// [A10] jenis instrumen yang bisa dipilih (SEOJK = Surat Edaran OJK)
const INSTRUMENTS = ["UU", "PP", "POJK", "SEOJK", "PBI", "PADG"];
// [A10] ukuran berkas yang mudah dibaca: 1532 → "1,5 KB"
const fmtSize = (n?: number | null) => n == null ? "" : n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toLocaleString("id-ID", { maximumFractionDigits: 1 })} KB` : `${(n / 1048576).toLocaleString("id-ID", { maximumFractionDigits: 1 })} MB`;

// [11a] low_confidence_text = true → teks pasal hasil OCR yang belum dikonfirmasi analis
type Prov = { provision_version_id: string; number_label: string; path: string; text: string; confidence: number; corrected_by_human: boolean; low_confidence_text?: boolean };
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
  const [nd, setNd] = useState({ canonical_number: "", title_id: "", instrument_type: "POJK", source_id: "" });
  // [A11] registri sumber: hanya sumber ACTIVE yang boleh dipilih saat mendaftarkan dokumen
  const [sources] = useLoad<Source[]>(() => api("/corpus/sources"), [], ctx.notify);
  const activeSources = (sources || []).filter(x => x.status === "ACTIVE");
  // [A12] filter daftar dokumen: kata kunci (nomor/judul/penerbit), status dokumen, jenis instrumen
  const [fq, setFq] = useState(""), [fStatus, setFStatus] = useState(""), [fType, setFType] = useState("");
  const { run, busy } = useAction(ctx.notify, reload);
  const analyst = can(ctx.me.role, "corpus_write"), officer = can(ctx.me.role, "obligation_extract");
  useEffect(() => { if (!sel && docs?.[0]?.versions.length) setSel(docs[0].versions[docs[0].versions.length - 1].id); }, [docs]);
  // [11b] muat ulang daftar pasal versi terpilih (dipanggil saat ganti versi dan setelah koreksi/konfirmasi teks)
  const loadProvs = () => { if (sel) api<Prov[]>(`/corpus/versions/${sel}/provisions`).then(setProvs).catch(e => ctx.notify("error", e.message)); };
  useEffect(loadProvs, [sel]);
  const selDoc = docs?.find(d => d.versions.some(v => v.id === sel));
  const selVer = selDoc?.versions.find(v => v.id === sel);
  // [11b] draft = versi masih boleh diubah (belum terbit); hanya saat draf tombol koreksi/konfirmasi muncul
  const draft = !!selVer && ["SEGMENTED_DRAFT", "UNDER_CORRECTION"].includes(selVer.state);
  // [11b] jumlah pasal OCR yang belum diperiksa → ditampilkan di kotak peringatan
  const ocrPending = provs.filter(p => p.low_confidence_text).length;
  // [A12] terapkan filter; huruf besar/kecil diabaikan
  const term = fq.trim().toLowerCase();
  const shown = (docs || []).filter(d => (!fStatus || d.status === fStatus) && (!fType || d.instrument_type === fType)
    && (!term || [d.canonical_number, d.title_id, d.issuer || ""].some(x => x.toLowerCase().includes(term))));
  const statuses = Array.from(new Set((docs || []).map(d => d.status)));

  // [A13] unggah versi: URL asal WAJIB; berkas yang sama persis dengan versi lain ditolak (DUPLICATE_SUSPECTED)
  const upload = (docId: string, file: File, origin: string) => run(async () => {
    const form = new FormData();
    form.append("file", file); form.append("origin_url", origin.trim());
    form.append("effective_date", new Date().toISOString().slice(0, 10));
    try {
      const r = await api(`/corpus/documents/${docId}/versions`, { form }); setSel(r.version_id);
      // [11c] PDF hasil pindaian: beri tahu halaman mana yang dibaca lewat OCR
      if (r.extraction_method === "OCR") ctx.notify("ok", `PDF hasil pindaian: halaman ${r.ocr_pages.join(", ")} dibaca lewat OCR. Periksa setiap pasal sebelum publikasi.`);
      // [A13] URL tetap diterima walau di luar situs sumber, tetapi analis diberi tahu agar memeriksa ulang
      if (r.origin_outside_source) ctx.notify("ok", "Versi diunggah. Perhatian: URL asal berada di luar situs sumber dokumen ini; pastikan URL-nya benar.");
    } catch (e) {
      // [A13] duplikat: tunjukkan dokumen yang sudah memuat berkas itu dan buka versinya
      if (e instanceof ApiError && e.code === "DUPLICATE_SUSPECTED" && e.offending?.existing_version_id) {
        setSel(e.offending.existing_version_id);
        throw new Error(`${e.message}. Versi tersebut sekarang ditampilkan; unggahan dibatalkan.`);
      }
      throw e;
    }
  }, "Versi baru diunggah dan tersegmentasi. Periksa pasal lalu publikasikan.");
  const extract = (pv: string) => run(() => api("/compliance/obligations/extract", { body: { provision_version_id: pv } }),
    "Draf kewajiban dibuat dan berlabel Draf AI. Validasi di halaman Kewajiban.");

  return <>
    <PageHead crumbs="Pusat Regulasi" title="Korpus & pasal" intro="Dokumen regulasi terkurasi. Versi yang sudah terbit tidak dapat diubah; setiap kewajiban menyitasi pasal pada versi tertentu." />
    <div className="cols">
      <div>
        {selVer ? <section className="panel">
          {/* [11d] judul versi; bila teksnya dari OCR ditambah keterangan " · teks via OCR" */}
          <header><div><h2>{selDoc?.canonical_number}</h2><p>{selDoc?.title_id} · versi {selVer.version_number}, berlaku {fmtDate(selVer.effective_date)}{selVer.extraction_method === "OCR" ? " · teks via OCR" : ""}</p>
            {/* [A14] provenans: sumber, URL asal, berkas asli → semua peran dapat membuka PDF aslinya untuk dibandingkan */}
            <div className="prov-meta">{selDoc?.source?.name && <>Sumber: {selDoc.source.name} · </>}
              {selVer.origin_url ? <>URL asal: <a href={selVer.origin_url} target="_blank" rel="noreferrer">{selVer.origin_url}</a></> : "URL asal belum tercatat"}
              {selVer.file_name && <> · {selVer.file_name} ({fmtSize(selVer.size_bytes)})</>}</div></div>
            <span className="row">{selVer.has_file && <button className="btn sm" onClick={() => openFile(`/corpus/versions/${selVer.id}/file`).catch(e => ctx.notify("error", e.message))}>Lihat berkas asli</button>}
              <Status s={selVer.state} /></span></header>
          {/* [11d] kotak peringatan kuning: publikasi diblokir selama masih ada pasal OCR yang belum dikonfirmasi */}
          {draft && ocrPending > 0 && <div className="notice warn"><span>{ocrPending} pasal berasal dari OCR dan belum diperiksa. Bandingkan dengan PDF aslinya, lalu klik <b>Konfirmasi teks</b> atau <b>Koreksi teks</b> pada setiap pasal sebelum publikasi.</span></div>}
          {/* Pasal dikelompokkan per BAB; setiap BAB bisa dilipat/dibuka */}
          {provs.length ? groupByBab(provs).map(g => <details key={g.bab} className="bab" open>
            <summary><span className="bab-title">{g.bab}</span> <span className="small muted">{g.pasal.length} pasal</span></summary>
            {/* [11e] setiap pasal ditampilkan lewat komponen ProvItem (lihat di bawah) */}
            <ul className="list">{g.pasal.map(p => <ProvItem key={p.provision_version_id} p={p} draft={draft} analyst={analyst}
              canExtract={officer && selVer.state === "PUBLISHED"} busy={busy} run={run} extract={extract} onSaved={loadProvs} />)}</ul>
          </details>) : <Empty>Versi ini belum memiliki pasal.</Empty>}
        </section> : <Empty>Pilih versi dokumen di samping untuk membaca pasalnya.</Empty>}
      </div>
      <aside>
        <section className="panel">
          <h2>Dokumen</h2>
          {/* [A12] kotak pencarian + filter status & jenis instrumen */}
          <div className="doc-filter">
            <input value={fq} onChange={e => setFq(e.target.value)} placeholder="Cari nomor, judul, atau penerbit" aria-label="Cari dokumen" />
            <div className="form-2">
              <select value={fStatus} onChange={e => setFStatus(e.target.value)} aria-label="Filter status"><option value="">Semua status</option>{statuses.map(x => <option key={x} value={x}>{x}</option>)}</select>
              <select value={fType} onChange={e => setFType(e.target.value)} aria-label="Filter jenis"><option value="">Semua jenis</option>{INSTRUMENTS.map(x => <option key={x}>{x}</option>)}</select>
            </div>
            {docs && <span className="small muted">{shown.length} dari {docs.length} dokumen</span>}
          </div>
          {shown.length ? <ul className="list">{shown.map(d => <li key={d.id}>
            <div className="between"><div className="title">{d.canonical_number}</div><Status s={d.status} /></div><div className="sub">{d.issuer} · {d.title_id}</div>
            {!!d.labels?.length && <div className="row" style={{ marginTop: 6, gap: 4 }}>{d.labels.map((l, i) => <span key={i} className={`badge ${l.state === "CONFIRMED" ? "teal" : ""}`} title={`${l.dimension} · ${l.state === "CONFIRMED" ? "terkonfirmasi" : "saran aturan"}`}>{l.value}</span>)}</div>}
            <div className="row" style={{ marginTop: 8 }}>{d.versions.map(v => <span key={v.id} className="row" style={{ gap: 4 }}>
              {/* Tombol pilih versi; versi yang ditarik diberi keterangan "(ditarik)" */}
              <button className={`btn sm ${v.id === sel ? "primary" : ""}`} onClick={() => setSel(v.id)}>v{v.version_number}{v.state === "WITHDRAWN" ? " (ditarik)" : ""}</button>
              {analyst && v.state !== "PUBLISHED" && v.state !== "WITHDRAWN" && <button className="btn sm" disabled={busy} onClick={() => run(() => api(`/corpus/versions/${v.id}/publish`, { method: "POST" }), `Versi ${v.version_number} dipublikasikan dan dibekukan.`)}>Publikasikan</button>}
            </span>)}</div>
            {/* Tombol Hapus/Tarik versi & Hapus dokumen (khusus Analis); kosongkan pilihan bila versi yang dibuka ikut terhapus */}
            {analyst && <CorpusActions role={ctx.me.role} doc={d} busy={busy} run={run} onRemoved={id => { if (d.versions.some(v => v.id === sel) && (id === d.id || id === sel)) setSel(""); }} />}
            {/* [A13] formulir unggah: URL asal wajib diisi sebelum berkas dikirim */}
            {analyst && <UploadForm busy={busy} onUpload={(f, url) => upload(d.id, f, url)} />}
          </li>)}</ul> : <Empty>{docs?.length ? "Tidak ada dokumen yang cocok dengan filter." : "Belum ada dokumen."}</Empty>}
        </section>
        {/* [A15] ubah judul/nomor/jenis/penerbit dokumen terpilih (matriks: Perubahan status dokumen U = Analis) */}
        {selDoc && canDo(ctx.me.role, "doc_status", "U") && <DocEdit key={`edit-${selDoc.id}`} doc={selDoc} busy={busy} run={run} />}
        {selDoc && <DocGovernance key={selDoc.id} doc={selDoc} docs={docs || []} ctx={ctx} onChange={reload} />}
        {analyst && <section className="panel">
          <h2>Daftarkan dokumen</h2>
          <div className="form">
            <label className="field">Nomor regulasi<input value={nd.canonical_number} onChange={e => setNd({ ...nd, canonical_number: e.target.value })} placeholder="POJK 4/POJK.05/2021" /></label>
            <label className="field">Judul<input value={nd.title_id} onChange={e => setNd({ ...nd, title_id: e.target.value })} placeholder="Penerapan Manajemen Risiko bagi Bank Umum" /></label>
            <label className="field">Jenis instrumen<select value={nd.instrument_type} onChange={e => setNd({ ...nd, instrument_type: e.target.value })}>{INSTRUMENTS.map(x => <option key={x}>{x}</option>)}</select></label>
            {/* [A11] sumber wajib dipilih dari registri; sumber yang belum disetujui Manajer tidak muncul */}
            <label className="field">Sumber regulasi<select value={nd.source_id} onChange={e => setNd({ ...nd, source_id: e.target.value })}>
              <option value="">Pilih sumber aktif</option>{activeSources.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
            {sources && !activeSources.length && <p className="small muted" style={{ margin: 0 }}>Belum ada sumber aktif. Daftarkan di menu <button className="rowlink" style={{ display: "inline", padding: 0 }} onClick={() => ctx.go("sumber")}>Sumber regulasi</button>.</p>}
            <button className="btn primary" disabled={busy || !nd.canonical_number || !nd.title_id || !nd.source_id} onClick={() => run(async () => {
              // issuer diisi dari penerbit sumber agar konsisten
              const src = activeSources.find(x => x.id === nd.source_id);
              await api("/corpus/documents", { body: { ...nd, issuer: src?.issuer_name } });
              setNd({ canonical_number: "", title_id: "", instrument_type: "POJK", source_id: "" });
            }, "Dokumen terdaftar. Unggah versi pertamanya.")}>Daftarkan dokumen</button>
          </div>
        </section>}
      </aside>
    </div>
  </>;
}

// Tipe fungsi run() dari useAction: menjalankan aksi API lalu menampilkan pesan sukses/gagal
type Run = (fn: () => Promise<unknown>, okText?: string) => Promise<boolean>;

/** [11f] KOMPONEN BARU. Satu pasal: label OCR, tombol Konfirmasi teks / Koreksi teks (hanya Analis, hanya versi draf),
 *  dan tombol Ekstrak kewajiban (hanya Officer, hanya versi terbit). */
function ProvItem({ p, draft, analyst, canExtract, busy, run, extract, onSaved }: {
  p: Prov; draft: boolean; analyst: boolean; canExtract: boolean; busy: boolean; run: Run; extract: (pv: string) => void; onSaved: () => void }) {
  // edit = kotak koreksi sedang terbuka; text = isi kotak koreksi
  const [edit, setEdit] = useState(false), [text, setText] = useState(p.text);
  // Simpan koreksi: PATCH teks baru → bila berhasil, tutup kotak & muat ulang daftar pasal
  const save = async () => {
    if (await run(() => api(`/corpus/provision-versions/${p.provision_version_id}`, { method: "PATCH", body: { text } }),
      `${p.number_label} dikoreksi; tercatat di jejak audit.`)) { setEdit(false); onSaved(); }
  };
  // Konfirmasi teks: teks OCR sudah benar → hapus tanda OCR tanpa mengubah teks
  const confirm = async () => {
    if (await run(() => api(`/corpus/provision-versions/${p.provision_version_id}/confirm-text`, { method: "POST" }),
      `${p.number_label}: teks dikonfirmasi sesuai PDF.`)) onSaved();
  };
  return <li>
    <div className="between">
      {/* judul pasal + badge status teks */}
      <div><b style={{ fontFamily: "var(--serif)", fontSize: 17 }}>{p.number_label}</b> <span className="small muted">keyakinan segmentasi {p.confidence}</span>
        {p.low_confidence_text && <span className="badge amber" style={{ marginLeft: 6 }}>Teks OCR · perlu konfirmasi</span>}
        {p.corrected_by_human && !p.low_confidence_text && <span className="badge" style={{ marginLeft: 6 }}>Diperiksa analis</span>}</div>
      {/* tombol aksi: Ekstrak (Officer, versi terbit) · Koreksi & Konfirmasi (Analis, versi draf) */}
      <span className="row">
        {canExtract && <button className="btn sm" disabled={busy} onClick={() => extract(p.provision_version_id)}>Ekstrak kewajiban</button>}
        {draft && analyst && !edit && <button className="btn sm ghost" onClick={() => { setText(p.text); setEdit(true); }}>Koreksi teks</button>}
        {draft && analyst && p.low_confidence_text && !edit && <button className="btn sm" disabled={busy} onClick={confirm}>Konfirmasi teks</button>}
      </span>
    </div>
    {/* mode koreksi: kotak teks + Simpan/Batal; mode baca: teks pasal rata kanan-kiri */}
    {edit ? <div className="form" style={{ marginTop: 8 }}>
      <textarea rows={Math.min(14, Math.max(4, text.split("\n").length + 1))} value={text} onChange={e => setText(e.target.value)} />
      <div className="row">
        <button className="btn primary sm" disabled={busy || !text.trim()} onClick={save}>Simpan koreksi</button>
        <button className="btn sm ghost" onClick={() => setEdit(false)}>Batal</button>
      </div>
    </div> : <PasalText text={p.text} className="justify" />}
    {/* [A8] teks ditampilkan per ayat/angka/huruf; teks asli tetap utuh (terlihat saat Koreksi teks) */}
  </li>;
}

/** [A13] KOMPONEN BARU. Unggah versi: isi URL asal (wajib) → pilih berkas → klik Unggah. */
function UploadForm({ busy, onUpload }: { busy: boolean; onUpload: (f: File, url: string) => Promise<boolean> }) {
  const [url, setUrl] = useState(""), [file, setFile] = useState<File | null>(null), [k, setK] = useState(0);
  const okUrl = /^https?:\/\/\S+\.\S+/.test(url.trim());  // pemeriksaan ringan; server tetap memeriksa
  return <div className="form" style={{ marginTop: 10 }}>
    <label className="field">URL asal dokumen (wajib)<input value={url} onChange={e => setUrl(e.target.value)} placeholder="https://www.ojk.go.id/id/regulasi/..." /></label>
    <label className="field">Berkas versi baru (.pdf/.txt)<input key={k} type="file" accept=".pdf,.txt" onChange={e => setFile(e.target.files?.[0] || null)} /></label>
    <div><button className="btn sm primary" disabled={busy || !file || !okUrl} onClick={async () => {
      if (file && await onUpload(file, url)) { setFile(null); setUrl(""); setK(x => x + 1); }  // k berubah → input berkas dikosongkan
    }}>Unggah versi</button>{url && !okUrl && <span className="small" style={{ color: "var(--red)", marginLeft: 8 }}>URL harus diawali http:// atau https://</span>}</div>
  </div>;
}

/** [A15] KOMPONEN BARU. Ubah data dokumen. Nomor regulasi dikunci bila dokumen pernah terbit
 *  (kewajiban & sitasi sudah memakai nomor itu); judul, jenis, dan penerbit tetap boleh diperbaiki. */
function DocEdit({ doc, busy, run }: { doc: Doc; busy: boolean; run: Run }) {
  const [f, setF] = useState({ canonical_number: doc.canonical_number, title_id: doc.title_id, instrument_type: doc.instrument_type, issuer: doc.issuer || "" });
  const [open, setOpen] = useState(false);
  const frozen = doc.versions.some(v => v.state === "PUBLISHED" || v.state === "WITHDRAWN");
  // kirim hanya kolom yang berubah
  const changes = Object.fromEntries(Object.entries(f).filter(([k, v]) => v.trim() !== String((doc as any)[k] ?? "")).map(([k, v]) => [k, v.trim()]));
  return <section className="panel">
    <div className="between"><h2>Data dokumen</h2>{!open && <button className="btn sm ghost" onClick={() => setOpen(true)}>Ubah</button>}</div>
    {open && <div className="form">
      <label className="field">Nomor regulasi<input value={f.canonical_number} disabled={frozen} onChange={e => setF({ ...f, canonical_number: e.target.value })} /></label>
      {frozen && <p className="small muted" style={{ margin: 0 }}>Nomor dikunci karena dokumen pernah terbit.</p>}
      <label className="field">Judul<input value={f.title_id} onChange={e => setF({ ...f, title_id: e.target.value })} /></label>
      <div className="form-2">
        <label className="field">Jenis<select value={f.instrument_type} onChange={e => setF({ ...f, instrument_type: e.target.value })}>{INSTRUMENTS.map(x => <option key={x}>{x}</option>)}</select></label>
        <label className="field">Penerbit<input value={f.issuer} onChange={e => setF({ ...f, issuer: e.target.value })} /></label>
      </div>
      <div className="row">
        <button className="btn primary sm" disabled={busy || !Object.keys(changes).length || !f.canonical_number.trim() || !f.title_id.trim()}
          onClick={async () => { if (await run(() => api(`/corpus/documents/${doc.id}`, { method: "PATCH", body: changes }), "Data dokumen diperbarui; tercatat di jejak audit.")) setOpen(false); }}>Simpan</button>
        <button className="btn sm ghost" onClick={() => { setOpen(false); setF({ canonical_number: doc.canonical_number, title_id: doc.title_id, instrument_type: doc.instrument_type, issuer: doc.issuer || "" }); }}>Batal</button>
      </div>
    </div>}
  </section>;
}

/** Hapus versi draf / dokumen yang belum pernah terbit; tarik (bukan hapus) versi yang sudah terbit.
 *  Konfirmasi dua langkah di dalam halaman agar tidak terhapus karena salah klik. */
function CorpusActions({ doc, busy, run, onRemoved, role }: { doc: Doc; busy: boolean; run: Run; onRemoved: (id: string) => void; role: string }) {
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
        ? !canDo(role, "doc_status", "U") ? null : <button key={v.id} className="btn sm ghost" disabled={busy} onClick={() => setPending({ kind: "withdraw", id: v.id, label: `Versi ${v.version_number}` })}>Tarik v{v.version_number}</button>
        : <button key={v.id} className="btn sm ghost danger-text" disabled={busy} onClick={() => setPending({ kind: "version", id: v.id, label: `Versi ${v.version_number}` })}>Hapus v{v.version_number}</button>)}
      {!everPublished && canDo(role, "source_registry", "D") && <button className="btn sm ghost danger-text" disabled={busy} onClick={() => setPending({ kind: "document", id: doc.id, label: doc.canonical_number })}>Hapus dokumen</button>}
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
  // Taxonomy Label dan Relasi regulasi punya hak baca sendiri di tabel: hanya dimuat bila peran berhak membacanya
  const canLab = canDo(ctx.me.role, "taxonomy", "R"), canRel = canDo(ctx.me.role, "relationship", "R");
  const [labels, reloadL] = useLoad<any[]>(() => canLab ? api(`/corpus/documents/${doc.id}/labels`) : Promise.resolve([]), [doc.id], ctx.notify);
  const [rels, reloadR] = useLoad<any[]>(() => canRel ? api(`/corpus/relationships?document_id=${doc.id}`) : Promise.resolve([]), [doc.id], ctx.notify);
  const [rf, setRf] = useState({ target_document_id: "", relation_type: "AMENDS", citing: "" });
  const [provs, setProvs] = useState<Prov[]>([]);
  useEffect(() => { const v = doc.versions[doc.versions.length - 1]; if (v) api<Prov[]>(`/corpus/versions/${v.id}/provisions`).then(setProvs).catch(() => setProvs([])); }, [doc.id]);
  const { run, busy } = useAction(ctx.notify, () => { reloadL(); reloadR(); onChange(); });
  const analyst = canDo(ctx.me.role, "taxonomy", "U"), manager = ctx.me.role === "COMPLIANCE_MANAGER";
  const canAddRel = canDo(ctx.me.role, "relationship", "C");
  if (!canLab && !canRel) return null;  // peran tanpa hak baca label maupun relasi tidak melihat panel ini sama sekali
  return <section className="panel"><h2>Klasifikasi & silsilah</h2>
    {canLab && <>
    <p className="muted small" style={{ marginTop: 2 }}>Label dari taksonomi terkendali; saran aturan perlu dikonfirmasi analis.</p>
    {labels?.length ? <ul className="list">{labels.map(l => <li key={l.id} className="between"><span className="small"><b>{l.value}</b> <span className="muted">{l.dimension}</span></span>
      <span className="row"><Status s={l.state === "SUGGESTED" ? "SUBMITTED" : l.state === "CONFIRMED" ? "ACCEPTED" : "REJECTED"} />
        {analyst && l.state === "SUGGESTED" && <button className="btn sm" disabled={busy} onClick={() => run(() => api(`/corpus/labels/${l.id}/confirm`, { method: "POST" }), "Label dikonfirmasi.")}>Konfirmasi</button>}
        {canDo(ctx.me.role, "taxonomy", "D") && l.state !== "REMOVED" && <button className="btn sm ghost" disabled={busy} onClick={() => run(() => api(`/corpus/labels/${l.id}/remove`, { body: { reason: "Tidak sesuai isi dokumen" } }), "Label dihapus dengan alasan.")}>Hapus</button>}</span></li>)}</ul> : <p className="small muted">Belum ada label.</p>}
    </>}
    {canRel && <>
    <h3 style={{ fontSize: 16, marginTop: 14 }}>Relasi dokumen</h3>
    {rels?.length ? <ul className="list">{rels.map(r => <li key={r.id} className="between"><span className="small">{r.source} <b>{r.relation_type}</b> {r.target}</span>
      <span className="row"><Status s={r.state === "PROPOSED" ? "SUBMITTED" : r.state === "CONFIRMED" ? "ACCEPTED" : "REJECTED"} />
        {manager && r.state === "PROPOSED" && <button className="btn sm" disabled={busy} onClick={() => run(() => api(`/corpus/relationships/${r.id}/confirm`, { method: "POST" }), "Relasi dikonfirmasi; status dokumen target diperbarui.")}>Konfirmasi</button>}</span></li>)}</ul> : <p className="small muted">Belum ada relasi.</p>}
    {canAddRel && <div className="form" style={{ marginTop: 8 }}>
      <div className="form-2"><label className="field">Dokumen ini…<select value={rf.relation_type} onChange={e => setRf({ ...rf, relation_type: e.target.value })}>{["AMENDS", "REVOKES", "PARTIALLY_REVOKES", "REFERS_TO", "IMPLEMENTS"].map(x => <option key={x}>{x}</option>)}</select></label>
        <label className="field">Dokumen target<select value={rf.target_document_id} onChange={e => setRf({ ...rf, target_document_id: e.target.value })}><option value="">Pilih</option>{docs.filter(d => d.id !== doc.id).map(d => <option key={d.id} value={d.id}>{d.canonical_number}</option>)}</select></label></div>
      <label className="field">Pasal penetap (wajib untuk konfirmasi)<select value={rf.citing} onChange={e => setRf({ ...rf, citing: e.target.value })}><option value="">Pilih pasal</option>{provs.map(p => <option key={p.provision_version_id} value={p.provision_version_id}>{p.number_label}</option>)}</select></label>
      <div><button className="btn" disabled={busy || !rf.target_document_id} onClick={() => run(() => api("/corpus/relationships", { body: { source_document_id: doc.id, target_document_id: rf.target_document_id, relation_type: rf.relation_type, citing_provision_version_id: rf.citing || null } }), "Relasi diusulkan.")}>Usulkan relasi</button></div>
    </div>}
    </>}
  </section>};