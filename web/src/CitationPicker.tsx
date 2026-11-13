import { useState } from "react";
import { api } from "./api";

export type Cite = { id: string; label: string };

// Pemilih sitasi: cari ketentuan pada versi terbit, pilih satu atau lebih; yang dikirim ke server adalah provision_version_id.
export function CitationPicker({ value, onChange }: { value: Cite[]; onChange: (v: Cite[]) => void }) {
  const [q, setQ] = useState(""), [hits, setHits] = useState<any[]>([]), [busy, setBusy] = useState(false);
  const search = async () => {
    if (!q.trim()) return;
    setBusy(true);
    try { setHits(await api<any[]>(`/corpus/search?q=${encodeURIComponent(q.trim())}&limit=8`)); } catch { setHits([]); }
    setBusy(false);
  };
  const add = (h: any) => {
    if (value.some(v => v.id === h.provision_version_id)) return;
      onChange([...value, { id: h.provision_version_id, label: `${h.canonical_number} ${h.number_label}${h.version_number != null ? ` v${h.version_number}` : ""}` }]);  };
  return <div style={{ marginTop: 8 }}>
    <div className="row">
      <input className="grow" value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); search(); } }}
        placeholder="Cari ketentuan yang disitasi (kata kunci), lalu pilih" />
      <button type="button" className="btn" disabled={busy || !q.trim()} onClick={search}>Cari</button>
    </div>
    {hits.length > 0 && <ul className="list" style={{ marginTop: 6 }}>{hits.map(h => <li key={h.provision_version_id}>
      <button type="button" className="rowlink" onClick={() => add(h)}>
    <div className="title">{h.canonical_number} · {h.number_label}{h.version_number != null && ` · v${h.version_number}`}</div>        <div className="sub">{String(h.text).slice(0, 140)}</div>
      </button></li>)}</ul>}
    {value.length > 0 && <div className="row" style={{ marginTop: 6, flexWrap: "wrap" }}>
      {value.map(v => <span key={v.id} className="badge">{v.label}{" "}
        <button type="button" className="btn sm ghost" onClick={() => onChange(value.filter(x => x.id !== v.id))}>×</button></span>)}
    </div>}
    {value.length === 0 && <p className="small muted" style={{ margin: "6px 0 0" }}>Sitasi wajib: pilih minimal satu ketentuan.</p>}
  </div>;
}