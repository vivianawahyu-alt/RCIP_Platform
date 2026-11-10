import { useState } from "react";
import { api } from "../api";
import type { Source } from "../types";
import type { Ctx } from "../ui";
import { Empty, Flow, PageHead, Status, can, fmtDate, useAction, useLoad } from "../ui";

// Kategori sumber (sama dengan SourceCategory di backend)
const CATEGORIES: [string, string][] = [["OJK", "Otoritas Jasa Keuangan"], ["BANK_INDONESIA", "Bank Indonesia"], ["PERATURAN_JDIH", "JDIH / peraturan.go.id"]];
// Alur status utama yang ditampilkan sebagai langkah
const STEPS: [string, string][] = [["DRAFT", "Draf"], ["PENDING_USE_REVIEW", "Reviu penggunaan"], ["ACTIVE", "Aktif"]];
// Isi awal formulir "Daftarkan sumber"
const blank = { name: "", category: "OJK", issuer_name: "", base_url: "", allow: "", permitted_use_statement: "", citation_requirement_text: "" };

/** FR-RKM-001 — Registri sumber regulasi (baris "Registri Regulatory Source" pada matriks RBAC).
 *  Analis mendaftarkan & mengajukan → Administrator Sistem (orang berbeda) menyetujui atau menolak dengan alasan →
 *  hanya sumber Aktif yang dapat menerima dokumen baru. Administrator juga menangguhkan atau mempensiunkan sumber. */
export function Sumber({ ctx }: { ctx: Ctx }) {
  const [rows, reload] = useLoad<Source[]>(() => api("/corpus/sources"), [], ctx.notify);
  const [f, setF] = useState(blank);
  // alasan per sumber (dipakai untuk tolak / tangguhkan / aktifkan kembali / pensiunkan)
  const [why, setWhy] = useState<Record<string, string>>({});
  const { run, busy } = useAction(ctx.notify, reload);
  // maker = Analis (daftarkan & ajukan); checker = Administrator (setujui/tolak, tangguhkan, pensiunkan) — sesuai matriks RBAC
  const maker = can(ctx.me.role, "source_write") && ctx.me.role !== "SYSTEM_ADMINISTRATOR", checker = can(ctx.me.role, "source_approve"), steward = checker;
  // sumber yang menunggu keputusan diletakkan paling atas agar Manajer langsung melihatnya
  const sorted = [...(rows || [])].sort((a, b) => Number(b.status === "PENDING_USE_REVIEW") - Number(a.status === "PENDING_USE_REVIEW"));

  // Daftarkan sumber baru dan langsung ajukan ke Manajer (submit: true)
  const create = () => run(async () => {
    await api("/corpus/sources", { body: { name: f.name, category: f.category, issuer_name: f.issuer_name, base_url: f.base_url,
      url_allow_list: f.allow.split("\n").map(x => x.trim()).filter(Boolean), permitted_use_statement: f.permitted_use_statement || null,
      citation_requirement_text: f.citation_requirement_text || null, submit: true } });
    setF(blank);
  }, "Sumber didaftarkan dan diajukan untuk reviu penggunaan oleh Administrator Sistem.");

  // Ubah status (SUSPENDED / ACTIVE / RETIRED) dengan alasan wajib
  const setStatus = (s: Source, status: string, ok: string) =>
    run(() => api(`/corpus/sources/${s.id}/status`, { body: { status, reason: why[s.id] } }), ok).then(done => done && setWhy({ ...why, [s.id]: "" }));

  return <>
    <PageHead crumbs="Pusat Regulasi" title="Sumber regulasi"
      intro="Setiap dokumen korpus berasal dari sumber terdaftar. Hanya sumber berstatus Aktif yang dapat menerima dokumen baru; persetujuan dilakukan Administrator Sistem yang berbeda dari pengaju." />
    <div className="cols">
      <div>
        <section className="panel">
          <h2>Daftar sumber</h2>
          {sorted.length ? <ul className="list">{sorted.map(s => <li key={s.id}>
            <div className="between"><div><div className="title">{s.name}</div>
              <div className="sub">{s.issuer_name} · {s.category} · {s.documents} dokumen · <a href={s.base_url} target="_blank" rel="noreferrer">{s.base_url}</a></div></div>
              <Status s={s.status} /></div>
            {/* langkah alur hanya relevan sebelum sumber ditangguhkan/pensiun */}
            {s.status !== "SUSPENDED" && s.status !== "RETIRED" && <div style={{ marginTop: 8 }}><Flow steps={STEPS} now={s.status} /></div>}
            <dl className="kv small" style={{ marginTop: 8 }}>
              <dt>Awalan URL yang diizinkan</dt><dd>{s.url_allow_list.length ? s.url_allow_list.join(", ") : "—"}</dd>
              <dt>Penggunaan diizinkan</dt><dd>{s.permitted_use_statement || <span style={{ color: "var(--red)" }}>belum diisi — sumber tidak dapat disetujui</span>}</dd>
              {s.citation_requirement_text && <><dt>Kewajiban sitasi</dt><dd>{s.citation_requirement_text}</dd></>}
              <dt>Pengaju / penyetuju</dt><dd>{s.submitted_by || s.created_by || "data awal"} / {s.approved_by || "—"}{s.approved_at ? ` (${fmtDate(s.approved_at)})` : ""}</dd>
              {s.return_reason && <><dt>Dikembalikan</dt><dd style={{ color: "var(--red)" }}>{s.return_reason}</dd></>}
            </dl>

            {/* Analis: sumber yang dikembalikan (DRAFT) dapat diajukan ulang */}
            {maker && s.status === "DRAFT" && <button className="btn sm" disabled={busy} onClick={() => run(() => api(`/corpus/sources/${s.id}/submit`, { method: "POST" }), "Diajukan ulang untuk reviu.")}>Ajukan ulang</button>}

            {/* Administrator: setujui / tolak (alasan wajib bila ditolak). Server menolak bila penyetuju = pengaju. */}
            {checker && s.status === "PENDING_USE_REVIEW" && <div className="decision"><h4>Reviu penggunaan sumber</h4>
              <p className="small" style={{ marginTop: 0 }}>Periksa situs, penerbit, dan pernyataan penggunaan. Sumber tanpa pernyataan penggunaan tidak dapat diaktifkan.</p>
              <div className="row"><input className="grow" value={why[s.id] || ""} onChange={e => setWhy({ ...why, [s.id]: e.target.value })} placeholder="Alasan (wajib bila ditolak)" />
                <button className="btn primary" disabled={busy} onClick={() => run(() => api(`/corpus/sources/${s.id}/decision`, { body: { outcome: "APPROVED" } }), "Sumber disetujui dan kini Aktif.")}>Setujui</button>
                <button className="btn danger" disabled={busy || !why[s.id]?.trim()} onClick={() => run(() => api(`/corpus/sources/${s.id}/decision`, { body: { outcome: "REJECTED", reason: why[s.id] } }), "Sumber dikembalikan ke analis.")}>Tolak</button></div></div>}

            {/* Administrator: tangguhkan, aktifkan kembali, atau pensiunkan (alasan wajib) */}
            {steward && (s.status === "ACTIVE" || s.status === "SUSPENDED") && <div className="row" style={{ marginTop: 8 }}>
              <input className="grow" value={why[s.id] || ""} onChange={e => setWhy({ ...why, [s.id]: e.target.value })} placeholder="Alasan perubahan status" />
              {s.status === "ACTIVE"
                ? <button className="btn sm" disabled={busy || !why[s.id]?.trim()} onClick={() => setStatus(s, "SUSPENDED", "Sumber ditangguhkan; unggahan baru dari sumber ini ditolak.")}>Tangguhkan</button>
                : <button className="btn sm" disabled={busy || !why[s.id]?.trim()} onClick={() => setStatus(s, "ACTIVE", "Sumber diaktifkan kembali.")}>Aktifkan kembali</button>}
              <button className="btn sm ghost danger-text" disabled={busy || !why[s.id]?.trim()} onClick={() => setStatus(s, "RETIRED", "Sumber dipensiunkan.")}>Pensiunkan</button>
            </div>}
          </li>)}</ul> : <Empty>Belum ada sumber.</Empty>}
        </section>
      </div>
      <aside>
        {maker ? <section className="panel">
          <h2>Daftarkan sumber</h2>
          <div className="form">
            <label className="field">Nama sumber<input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} placeholder="JDIH Otoritas Jasa Keuangan" /></label>
            <label className="field">Kategori<select value={f.category} onChange={e => setF({ ...f, category: e.target.value })}>{CATEGORIES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
            <label className="field">Penerbit<input value={f.issuer_name} onChange={e => setF({ ...f, issuer_name: e.target.value })} placeholder="Otoritas Jasa Keuangan" /></label>
            <label className="field">Alamat situs (base URL)<input value={f.base_url} onChange={e => setF({ ...f, base_url: e.target.value })} placeholder="https://www.ojk.go.id" /></label>
            <label className="field">Awalan URL yang diizinkan (satu per baris, opsional)<textarea rows={2} value={f.allow} onChange={e => setF({ ...f, allow: e.target.value })} placeholder="https://www.ojk.go.id/id/regulasi/" /></label>
            <label className="field">Pernyataan penggunaan yang diizinkan<textarea rows={2} value={f.permitted_use_statement} onChange={e => setF({ ...f, permitted_use_statement: e.target.value })} placeholder="Dokumen publik; dipakai untuk keperluan akademik dengan sitasi sumber." /></label>
            <label className="field">Kewajiban sitasi (opsional)<input value={f.citation_requirement_text} onChange={e => setF({ ...f, citation_requirement_text: e.target.value })} /></label>
            <button className="btn primary" disabled={busy || !f.name.trim() || !f.issuer_name.trim() || !f.base_url.trim()} onClick={create}>Daftarkan & ajukan</button>
          </div>
        </section> : <section className="panel"><h2>Tentang registri</h2>
          <p className="small muted">Pendaftaran sumber dilakukan Analis Regulasi; persetujuan, penangguhan, dan pensiun oleh Administrator Sistem. Peran lain hanya dapat membaca.</p></section>}
      </aside>
    </div>
  </>;
}
