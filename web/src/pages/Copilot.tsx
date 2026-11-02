import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api";
import type { Ctx } from "../ui";
import { AiBadge, Cite, PageHead, useAction } from "../ui";

const EXAMPLES = ["Berapa lama batas pelaporan insiden TI?", "Kapan laporan transaksi keuangan mencurigakan disampaikan ke PPATK?",
  "Berapa kali uji penetrasi sistem elektronik kritikal setahun?", "Berapa tarif pajak penghasilan badan?"];

export function Copilot({ ctx }: { ctx: Ctx }) {
  const [q, setQ] = useState(""), [a, setA] = useState<any>(null), [asked, setAsked] = useState("");
  const { run, busy } = useAction(ctx.notify);
  const ask = (question: string) => run(async () => { setAsked(question); setA(await api("/copilot/query", { body: { question } })); });
  const submit = (e: FormEvent) => { e.preventDefault(); if (q.trim()) ask(q.trim()); };
  return <>
    <PageHead crumbs="Pusat Regulasi" title="Tanya regulasi" intro="Copilot hanya membaca pasal yang sudah terbit dan selalu menyertakan sitasi. Copilot tidak memberi nasihat hukum dan tidak dapat mengubah rekaman kepatuhan." />
    <div className="cols">
      <div>
        <section className="panel"><form className="form" onSubmit={submit}>
          <label className="field">Pertanyaan<textarea value={q} onChange={e => setQ(e.target.value)} placeholder="Tulis pertanyaan tentang kewajiban regulasi" /></label>
          <div><button className="btn primary" disabled={busy || !q.trim()}>Tanyakan</button></div></form></section>
        {a && <section className="panel">
          <div className="between"><h2 style={{ fontSize: 19 }}>{asked}</h2><AiBadge /></div>
          {a.legal_notice && <div className="notice error" style={{ marginTop: 10 }}><span>{a.legal_notice}</span></div>}
          <p className="small muted" style={{ margin: "6px 0 0" }}>Moda: kutipan pasal (tanpa narasi generatif) · relevansi tertinggi {Math.round((a.confidence || 0) * 100)}%</p>
          <div className="copilot-answer" style={{ marginTop: 12 }}>
            {a.hits?.length ? a.hits.map((h: any) => <div key={h.provision_version_id} style={{ marginBottom: 12 }}>
              <Cite c={h} onOpen={ctx.openCite} /><div className="verbatim">{h.text}</div></div>) : <pre className="answer">{a.answer}</pre>}
          </div>
          <p className="small muted" style={{ marginTop: 14 }}>{a.disclaimer}</p>
        </section>}
      </div>
      <aside><section className="panel"><h2>Contoh pertanyaan</h2><ul className="list">{EXAMPLES.map(e => <li key={e}><button className="rowlink" onClick={() => { setQ(e); ask(e); }}><span className="title">{e}</span></button></li>)}</ul></section></aside>
    </div>
  </>;
}
