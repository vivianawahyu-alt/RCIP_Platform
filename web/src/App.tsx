import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import type { Me, Role } from "./types";
import { PasalText, ROLE_LABEL, canSeePage, fmtDate, homeRoute } from "./ui";
import { api, hasToken, setToken } from "./api";
import { canDo } from "./permissions";
import type { Ctx } from "./ui";
import { Beranda } from "./pages/Beranda";
import { Postur } from "./pages/Eksekutif";
import { KontrolSaya } from "./pages/KontrolSaya";
import { Regulasi, Perubahan } from "./pages/Regulasi";
import { Katalog } from "./pages/Katalog";
import { Peraturan } from "./pages/Peraturan";
import { Kewajiban } from "./pages/Kewajiban";
import { Kontrol, Asesmen } from "./pages/Kontrol";
import { Temuan } from "./pages/Temuan";
import { Laporan } from "./pages/Laporan";
import { Audit } from "./pages/Audit";
import { Copilot } from "./pages/Copilot";
import { Cari } from "./pages/Cari";
import { Keberlakuan } from "./pages/Keberlakuan";
import { Admin } from "./pages/Admin";
import { Sumber } from "./pages/Sumber";  // [A19] halaman registri sumber regulasi


type Item = { route: string; label: string; desc: string; only?: Role[] };
const MENU: { label: string; items: Item[] }[] = [
  { label: "Beranda", items: [{ route: "beranda", label: "Beranda", desc: "Postur kepatuhan", only: ["EXECUTIVE"] }] },
  { label: "Kontrol saya", items: [{ route: "kontrol-saya", label: "Kontrol saya", desc: "Bukti & temuan milik Anda", only: ["BUSINESS_CONTROL_OWNER"]},
    { route: "regulasi", label: "Korpus & pasal", desc: "Dokumen, versi imutabel, dan teks pasal" },
    { route: "sumber", label: "Sumber regulasi", desc: "Registri sumber & persetujuan penggunaan" },  // [A19]
    { route: "perubahan", label: "Perubahan regulasi", desc: "Bandingkan versi, deteksi perubahan material" },
    { route: "copilot", label: "Tanya regulasi", desc: "Jawaban bersitasi + antrean tinjauan" }] },
  { label: "Kepatuhan", items: [
    { route: "keberlakuan", label: "Keberlakuan", desc: "Apakah peraturan mengikat organisasi" },
    { route: "kewajiban", label: "Kewajiban", desc: "Draf AI, validasi, dan persetujuan" },
    { route: "kontrol", label: "Risiko & kontrol", desc: "Pemetaan, pemilik, bukti kontrol" },
    { route: "asesmen", label: "Asesmen & sign-off", desc: "Efektivitas desain dan operasional" }] },
  { label: "Temuan & Remediasi", items: [{ route: "temuan", label: "Register temuan", desc: "Tindakan, bukti penutupan, validasi" }] },
  { label: "Laporan & Audit", items: [
    { route: "laporan", label: "Laporan kepatuhan", desc: "Draf, persetujuan, dan penerbitan" },
    { route: "audit", label: "Jejak audit", desc: "Siapa melakukan apa, kapan" },
    { route: "admin", label: "Administrasi", desc: "Parameter runtime, pengguna, metrik" }] },
];
const SEARCH_KINDS = ["Semua", "Peraturan", "Kewajiban", "Temuan"];

function useRoute(): [string, (r: string) => void] {
  const read = () => window.location.hash.replace(/^#\/?/, "") || "beranda";
  const [r, setR] = useState(read());
  useEffect(() => { const f = () => setR(read()); window.addEventListener("hashchange", f); return () => window.removeEventListener("hashchange", f); }, []);
  return [r, (to: string) => { window.location.hash = "/" + to; window.scrollTo(0, 0); }];
}

export default function App() {
  const [me, setMe] = useState<Me | null>(JSON.parse(sessionStorage.getItem("rcip_me") || "null"));
  const [route, go] = useRoute();
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string; at: number } | null>(null);
  const [cite, setCite] = useState<any>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [q, setQ] = useState(""), [kind, setKind] = useState("Semua");
  const notify = useCallback((kind: "ok" | "error", text: string) => { setMsg({ kind, text, at: Date.now() }); if (kind === "ok") setTimeout(() => setMsg(m => (m?.text === text ? null : m)), 4000); }, []);
  const openCite = useCallback((pv: string) => { api("/citations/resolve", { body: { provision_version_ids: [pv] } }).then(r => setCite(r.resolved[0])).catch(e => notify("error", e.message)); }, [notify]);
  useEffect(() => { const close = () => setOpen(null); document.addEventListener("click", close); return () => document.removeEventListener("click", close); }, []);
  // pesan lama dibersihkan saat pindah halaman; pesan dari aksi yang baru saja memicu navigasi tetap tampil
  useEffect(() => setMsg(m => (m && Date.now() - m.at < 1500 ? m : null)), [route]);

  if (!me || !hasToken()) return <Login onDone={setMe} />;
  const ctx: Ctx = { me, notify, go, openCite };
  const [page, param] = route.split("/");
  const logout = () => { setToken(""); sessionStorage.removeItem("rcip_me"); setMe(null); };
  const search = (e: FormEvent) => { e.preventDefault(); if (q.trim()) go(`cari/${encodeURIComponent(kind)}/${encodeURIComponent(q.trim())}`); };

  return <>
    <div className="utility"><div className="wrap">
      <span>PT Bank Sinar Nusantara <span className="muted">(profil sintetis)</span></span>
      <span className="hide-sm">{fmtDate(new Date().toISOString())}</span>
      <span className="spacer" />
      <span>Masuk sebagai <b>{me.username}</b> — {ROLE_LABEL[me.role]}</span>
      <button onClick={logout}>Keluar</button>
    </div></div>
    <div className="mainbar"><div className="wrap">
      <button className="wordmark" onClick={() => go(homeRoute(me.role))} aria-label="Beranda RCIP"><strong>RCIP</strong><span>Regulatory & Compliance Intelligence</span></button>
      <nav className="menu" aria-label="Menu utama">
        {MENU.map(g => ({ ...g, items: g.items.filter(i => canSeePage(me.role, i.route) && (!i.only || i.only.includes(me.role))) })).filter(g => g.items.length > 0).map(g => {
                    const active = g.items.some(i => i.route === (page === "peraturan" ? "katalog" : page));  // halaman detail ikut menandai Katalog
          if (g.items.length === 1) return <div className="menu-group" key={g.label}><button className={active ? "active" : ""} onClick={() => go(g.items[0].route)}>{g.label}</button></div>;
          return <div key={g.label} className={`menu-group ${open === g.label ? "open" : ""}`} onClick={e => e.stopPropagation()}>
            <button className={active ? "active" : ""} aria-expanded={open === g.label} onClick={() => setOpen(open === g.label ? null : g.label)}>{g.label} ▾</button>
            <div className="dropdown" role="menu">{g.items.map(i => <button key={i.route} role="menuitem" onClick={() => { setOpen(null); go(i.route); }}><b>{i.label}</b><small>{i.desc}</small></button>)}</div>
          </div>;
        })}
      </nav>
    </div></div>
    <div className="searchband"><div className="wrap">
      <form className="searchrow" onSubmit={search} role="search">
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Cari pasal, kewajiban, atau temuan — mis. laporan insiden TI" aria-label="Kata kunci pencarian" />
        <button type="submit">Cari</button>
      </form>
      <div className="chips">{SEARCH_KINDS.filter(k => k === "Kewajiban" ? canDo(me.role, "obligation", "R") : k === "Temuan" ? canDo(me.role, "finding", "R") : true).map(k => <button key={k} type="button" className={`chip-filter ${k === kind ? "on" : ""}`} onClick={() => setKind(k)}>{k}</button>)}</div>
    </div></div>
    <main className="wrap">
      {msg && <div className={`notice ${msg.kind}`} role="status"><span>{msg.text}</span><button onClick={() => setMsg(null)}>Tutup</button></div>}
            {canSeePage(me.role, page) && page === "katalog" && <Katalog ctx={ctx} />}
      {canSeePage(me.role, page) && page === "peraturan" && <Peraturan ctx={ctx} id={param} />}
      {!canSeePage(me.role, page) && (queueMicrotask(() => go(homeRoute(me.role))), null)}
      {canSeePage(me.role, page) && page === "beranda" && (me.role === "EXECUTIVE" ? <Postur ctx={ctx} /> : <Beranda ctx={ctx} />)}
{canSeePage(me.role, page) && page === "kontrol-saya" && <KontrolSaya ctx={ctx} />}
      {canSeePage(me.role, page) && page === "regulasi" && <Regulasi ctx={ctx} />}
      {canSeePage(me.role, page) && page === "perubahan" && <Perubahan ctx={ctx} />}
      {canSeePage(me.role, page) && page === "sumber" && <Sumber ctx={ctx} />}
      {canSeePage(me.role, page) && page === "keberlakuan" && <Keberlakuan ctx={ctx} />}
      {canSeePage(me.role, page) && page === "admin" && <Admin ctx={ctx} />}
      {canSeePage(me.role, page) && page === "kewajiban" && <Kewajiban ctx={ctx} />}
      {canSeePage(me.role, page) && page === "kontrol" && <Kontrol ctx={ctx} selected={param} />}
      {canSeePage(me.role, page) && page === "asesmen" && <Asesmen ctx={ctx} />}
      {canSeePage(me.role, page) && page === "temuan" && <Temuan ctx={ctx} selected={param} />}
      {canSeePage(me.role, page) && page === "laporan" && <Laporan ctx={ctx} selected={param} />}
      {canSeePage(me.role, page) && page === "audit" && <Audit ctx={ctx} />}
      {canSeePage(me.role, page) && page === "copilot" && <Copilot ctx={ctx} />}
      {canSeePage(me.role, page) && page === "cari" && <Cari ctx={ctx} kind={decodeURIComponent(param || "Semua")} q={decodeURIComponent(route.split("/").slice(2).join("/"))} />}
    </main>
    {/* Footer ringkas: nama aplikasi + program, rata tengah (lihat footer.site di styles.css) */}
    <footer className="site"><div className="wrap">
      <b>RCIP</b><p>Capstone V-TEKI × UKDW.</p>
    </div></footer>
    {cite && <div className="modal" onClick={() => setCite(null)}><div onClick={e => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Teks pasal">
      <div className="crumbs">{cite.document.issuer} · {cite.document.title_id}</div>
      <h2>{cite.document.canonical_number} — {cite.number_label}</h2>
      <p className="muted small">Versi {cite.document_version.version_number} ({cite.document_version.state}), berlaku {fmtDate(cite.document_version.effective_date)} · jalur {cite.hierarchical_path}</p>
      <PasalText text={cite.text} />{/* [A8] teks pasal per ayat/huruf */}
      <button className="btn primary" onClick={() => setCite(null)} autoFocus>Tutup</button>
    </div></div>}
  </>;
}

const PERSONAS: [string, string][] = [["officer", "Pejabat Kepatuhan"], ["manager", "Manajer Kepatuhan"], ["owner", "Pemilik Kontrol"],
  ["analyst", "Analis Regulasi"], ["auditor", "Auditor Internal"], ["legal", "Peninjau Hukum"], ["executive", "Eksekutif"], ["admin", "Administrator"]];

function Login({ onDone }: { onDone: (m: Me) => void }) {
  const [u, setU] = useState("officer"), [p, setP] = useState("demo1234"), [err, setErr] = useState("");
  const go = async (e: FormEvent) => {
    e.preventDefault();
    try { const r = await api("/auth/login", { body: { username: u, password: p } }); setToken(r.access_token); const m = { username: r.username, role: r.role, user_id: r.user_id }; sessionStorage.setItem("rcip_me", JSON.stringify(m)); onDone(m); }
    catch (e) { setErr((e as Error).message); }
  };
  return <div className="login-shell">
    <section className="login-art">
      <div><strong style={{ fontFamily: "var(--serif)", fontSize: 28, color: "#fff" }}>RCIP</strong></div>
      <div>
        <h1>Dari pasal regulasi sampai bukti pelaksanaannya.</h1>
        <div className="verbatim">“Bank wajib menyampaikan laporan insiden TI kepada Otoritas Jasa Keuangan paling lambat 12 (dua belas) jam setelah insiden TI diketahui.”</div>
        <p style={{ maxWidth: "52ch" }}>Setiap kewajiban di platform ini dapat ditelusuri ke pasal dan versi peraturan yang melahirkannya, lalu ke kontrol, asesmen, bukti, temuan, dan laporan.</p>
      </div>
      <small>Korpus demo sintetis · bukan teks resmi</small>
    </section>
    <section className="login-form">
      <form onSubmit={go} className="form">
        <h2>Masuk</h2>
        <p className="muted small" style={{ margin: 0 }}>Pilih persona demo; setiap peran melihat aksi yang berbeda.</p>
        {err && <div className="notice error">{err}</div>}
        <label className="field">Username<input value={u} onChange={e => setU(e.target.value)} autoComplete="username" /></label>
        <label className="field">Password<input type="password" value={p} onChange={e => setP(e.target.value)} autoComplete="current-password" /></label>
        <button className="btn primary" type="submit">Masuk</button>
        <div className="persona">{PERSONAS.map(([n, l]) => <button type="button" key={n} className={u === n ? "on" : ""} onClick={() => { setU(n); setP("demo1234"); }}><b>{n}</b>{l}</button>)}</div>
        <p className="hint">Password semua akun demo: demo1234</p>
      </form>
    </section>
  </div>;
}