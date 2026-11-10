import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api";
import type { Interaction } from "../types";
import type { Ctx } from "../ui";
import { AiBadge, Cite, Empty, PageHead, PasalText, can, canReadCopilotLog, fmtTime, useAction, useLoad } from "../ui";

const EXAMPLES = ["Berapa lama batas pelaporan insiden TI?", "Kapan laporan transaksi keuangan mencurigakan disampaikan ke PPATK?",
  "Berapa kali uji penetrasi sistem elektronik kritikal setahun?", "Berapa tarif pajak penghasilan badan?"];
// Label putusan tinjauan
const VERDICT_LABEL: Record<string, [string, string]> = {
  CONFIRMED: ["Dikonfirmasi benar", "green"], CORRECTED: ["Dikoreksi", "amber"], REJECTED: ["Tidak dapat dipakai", "red"] };

export function Copilot({ ctx }: { ctx: Ctx }) {
  const [q, setQ] = useState(""), [a, setA] = useState<any>(null), [asked, setAsked] = useState("");
  // [A17] catatan untuk peninjau + status "sudah dikirim" untuk jawaban yang sedang tampil
  const [note, setNote] = useState(""), [sent, setSent] = useState(false);
  const reviewer = can(ctx.me.role, "copilot_review"), logReader = canReadCopilotLog(ctx.me.role);
  // [A18] antrean tinjauan (Analis/Officer) dan riwayat tinjauan (semua peran yang boleh membaca log)
  const [queue, reloadQueue] = useLoad<Interaction[]>(() => reviewer ? api("/copilot/interactions?review=pending") : Promise.resolve([]), [], ctx.notify);
  const [log, reloadLog] = useLoad<Interaction[]>(() => logReader ? api("/copilot/interactions?limit=50") : Promise.resolve([]), [], ctx.notify);
  const reloadAll = () => { reloadQueue(); reloadLog(); };
  const { run, busy } = useAction(ctx.notify);
  const ask = (question: string) => run(async () => { setAsked(question); setSent(false); setNote(""); setA(await api("/copilot/query", { body: { question } })); });
  const submit = (e: FormEvent) => { e.preventDefault(); if (q.trim()) ask(q.trim()); };
  // [A17] kirim jawaban yang sedang tampil ke antrean tinjauan
  const requestReview = () => run(async () => {
    await api(`/copilot/interactions/${a.interaction_id}/request-review`, { body: { note: note.trim() || null } });
    setSent(true); reloadAll();
  }, "Jawaban dikirim untuk ditinjau Analis Regulasi / Pejabat Kepatuhan / Peninjau Hukum.");
  const reviewed = (log || []).filter(x => x.review?.state === "COMPLETED");

  return <>
    <PageHead crumbs="Pusat Regulasi" title="Tanya regulasi" intro="Copilot hanya membaca pasal yang sudah terbit dan selalu menyertakan sitasi. Copilot tidak memberi nasihat hukum dan tidak dapat mengubah rekaman kepatuhan." />
    <div className="cols">
      <div>
        <section className="panel"><form className="form" onSubmit={submit}>
          <label className="field">Pertanyaan<textarea value={q} onChange={e => setQ(e.target.value)} placeholder="Tulis pertanyaan tentang kewajiban regulasi" /></label>
          <div><button className="btn primary" disabled={busy || !q.trim()}>Tanyakan</button></div></form></section>
        {a && <section className="panel">
          <div className="between"><h2 style={{ fontSize: 19 }}>{asked}</h2><span className="row">
            {/* [A17] tanda keyakinan rendah: di bawah ambang copilot.review_threshold (bawaan 70%) */}
            {a.low_confidence && <span className="badge amber" title={`Ambang ${Math.round((a.review_threshold || 0.7) * 100)}%`}>Keyakinan rendah</span>}
            <AiBadge /></span></div>
          {a.legal_notice && <div className="notice error" style={{ marginTop: 10 }}><span>{a.legal_notice}</span></div>}
          <p className="small muted" style={{ margin: "6px 0 0" }}>Moda: kutipan pasal (tanpa narasi generatif) · relevansi tertinggi {Math.round((a.confidence || 0) * 100)}%</p>
          <div className="copilot-answer" style={{ marginTop: 12 }}>
            {a.hits?.length ? a.hits.map((h: any) => <div key={h.provision_version_id} style={{ marginBottom: 12 }}>
              <Cite c={h} onOpen={ctx.openCite} /><PasalText text={h.text} /></div>) : <pre className="answer">{a.answer}</pre>}
          </div>
          {/* [A17] minta tinjauan manusia — disarankan untuk jawaban berkeyakinan rendah, tetapi boleh untuk jawaban apa pun */}
          {a.interaction_id && <div className={a.low_confidence ? "decision" : ""} style={{ marginTop: 12 }}>
            {sent ? <p className="small" style={{ margin: 0 }}>Sudah dikirim untuk ditinjau. Hasilnya tampil di <b>Riwayat tinjauan</b>.</p> : <>
              {a.low_confidence && <h4>Jawaban ini perlu dicek manusia</h4>}
              <div className="row"><input className="grow" value={note} onChange={e => setNote(e.target.value)} placeholder="Catatan untuk peninjau (opsional)" />
                <button className={`btn ${a.low_confidence ? "primary" : ""}`} disabled={busy} onClick={requestReview}>Kirim untuk ditinjau</button></div></>}
          </div>}
          <p className="small muted" style={{ marginTop: 14 }}>{a.disclaimer}</p>
        </section>}

        {/* [A18] antrean tinjauan untuk Analis / Pejabat Kepatuhan / Peninjau Hukum */}
        {reviewer && <section className="panel"><h2>Antrean tinjauan copilot</h2>
          <p className="small muted" style={{ marginTop: 2 }}>Beri putusan atas jawaban yang dikirim pengguna lain. Anda tidak dapat meninjau permintaan Anda sendiri.</p>
          {queue?.length ? <ul className="list">{queue.map(x => <ReviewItem key={x.id} x={x} ctx={ctx} onDone={reloadAll} />)}</ul>
            : <Empty>Tidak ada jawaban yang menunggu tinjauan.</Empty>}
        </section>}
      </div>
      <aside>
        <section className="panel"><h2>Contoh pertanyaan</h2><ul className="list">{EXAMPLES.map(e => <li key={e}><button className="rowlink" onClick={() => { setQ(e); ask(e); }}><span className="title">{e}</span></button></li>)}</ul></section>
        {/* [A18] riwayat putusan tinjauan (terbaru dulu) */}
        {logReader && <section className="panel"><h2>Riwayat tinjauan</h2>
          {reviewed.length ? <ul className="list">{reviewed.slice(0, 10).map(x => { const [l, tone] = VERDICT_LABEL[x.review!.verdict || ""] || ["—", ""];
            return <li key={x.id}><div className="between"><span className="title small">{x.question}</span><span className={`badge ${tone}`}>{l}</span></div>
              <div className="sub">ditanya {x.user || "—"} · ditinjau {x.review!.reviewer} · {fmtTime(x.review!.reviewed_at)}</div>
              {x.review!.corrected_text && <div className="small" style={{ marginTop: 4 }}>Koreksi: {x.review!.corrected_text}</div>}</li>; })}</ul>
            : <p className="small muted">Belum ada tinjauan selesai.</p>}
        </section>}
      </aside>
    </div>
  </>;
}

/** [A18] KOMPONEN BARU. Satu permintaan tinjauan: pertanyaan, pasal yang diambil, dan formulir putusan.
 *  CONFIRMED = jawaban benar · CORRECTED = perlu koreksi (teks wajib) · REJECTED = jawaban tidak dapat dipakai. */
function ReviewItem({ x, ctx, onDone }: { x: Interaction; ctx: Ctx; onDone: () => void }) {
  const [verdict, setVerdict] = useState("CONFIRMED"), [text, setText] = useState("");
  const { run, busy } = useAction(ctx.notify, onDone);
  const mine = x.review?.requested_by === ctx.me.username;  // peminta tidak boleh meninjau sendiri (server juga menolak)
  return <li>
    <div className="between"><span className="title">{x.question}</span>
      <span className="row">{x.low_confidence && <span className="badge amber">Keyakinan rendah</span>}<span className="small muted">{Math.round(x.confidence * 100)}%</span></span></div>
    <div className="sub">diminta {x.review?.requested_by} · {fmtTime(x.review?.requested_at)}{x.review?.request_note ? ` · “${x.review.request_note}”` : ""}</div>
    {/* pasal yang diambil copilot saat menjawab, bisa dibuka sitasinya */}
    {!!x.retrieved?.length && <div className="row" style={{ marginTop: 6, gap: 4 }}>{x.retrieved.map((r: any, i: number) =>
      <button key={i} type="button" className="cite" onClick={() => ctx.openCite(r.provision_version_id)}>{r.citation}</button>)}</div>}
    {mine ? <p className="small muted">Permintaan Anda sendiri — menunggu peninjau lain.</p> : <div className="form" style={{ marginTop: 8 }}>
      <div className="row">
        <select value={verdict} onChange={e => setVerdict(e.target.value)} aria-label="Putusan">
          <option value="CONFIRMED">Benar (konfirmasi)</option><option value="CORRECTED">Perlu koreksi</option><option value="REJECTED">Tidak dapat dipakai</option></select>
        <button className="btn primary sm" disabled={busy || (verdict === "CORRECTED" && !text.trim())}
          onClick={() => run(() => api(`/copilot/reviews/${x.review!.id}/verdict`, { body: { verdict, corrected_text: text.trim() || null } }), "Putusan tinjauan tersimpan dan tercatat di jejak audit.")}>Simpan putusan</button>
      </div>
      {verdict !== "CONFIRMED" && <textarea rows={2} value={text} onChange={e => setText(e.target.value)}
        placeholder={verdict === "CORRECTED" ? "Jawaban yang benar beserta pasalnya (wajib)" : "Alasan (opsional)"} />}
    </div>}
  </li>;
}
