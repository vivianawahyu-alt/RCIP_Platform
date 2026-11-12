import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { Me, Role } from "./types";
import { canDo } from "./permissions";

export type Notify = (kind: "ok" | "error", text: string) => void;
export type Ctx = { me: Me; notify: Notify; go: (route: string) => void; openCite: (pvId: string) => void };

/** Menjalankan aksi API: menampilkan pesan sukses/gagal lalu memuat ulang data. */
export function useAction(notify: Notify, after?: () => void) {
  const [busy, setBusy] = useState(false);
  const run = useCallback(async (fn: () => Promise<unknown>, okText?: string) => {
    setBusy(true);
    try { await fn(); if (okText) notify("ok", okText); after?.(); return true; }
    catch (e) { notify("error", (e as Error).message); return false; }
    finally { setBusy(false); }
  }, [notify, after]);
  return { run, busy };
}

export function useLoad<T>(fn: () => Promise<T>, deps: unknown[], notify: Notify): [T | null, () => void] {
  const [data, setData] = useState<T | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => { let live = true; fn().then(d => live && setData(d)).catch(e => notify("error", (e as Error).message)); return () => { live = false; }; },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [...deps, tick]);
  return [data, () => setTick(t => t + 1)];
}

export const ROLE_LABEL: Record<Role, string> = {
  REGULATORY_ANALYST: "Analis Regulasi", COMPLIANCE_OFFICER: "Pejabat Kepatuhan", BUSINESS_CONTROL_OWNER: "Pemilik Bisnis/Kontrol",
  LEGAL_REVIEWER: "Peninjau Hukum", COMPLIANCE_MANAGER: "Manajer Kepatuhan", INTERNAL_AUDITOR: "Auditor Internal",
  EXECUTIVE: "Eksekutif", SYSTEM_ADMINISTRATOR: "Administrator Sistem",
};

const STATE_LABEL: Record<string, [string, string]> = {
  AI_DRAFT: ["Draf AI", "ai"], IN_VALIDATION: ["Validasi", "amber"], PENDING_APPROVAL: ["Menunggu persetujuan", "blue"],
  ACTIVE: ["Aktif", "green"], PENDING_USE_REVIEW: ["Reviu penggunaan", "blue"], SUSPENDED: ["Ditangguhkan", "red"], REVIEW_REQUIRED: ["Perlu ditinjau", "red"], SUPERSEDED: ["Digantikan", ""], RETIRED: ["Pensiun", ""],
  OPEN: ["Terbuka", "red"], ACTION_PLANNED: ["Tindakan direncanakan", "amber"], IN_REMEDIATION: ["Dalam remediasi", "blue"],
  PENDING_CLOSURE_VALIDATION: ["Menunggu validasi penutupan", "teal"], CLOSED: ["Ditutup", "green"], RISK_ACCEPTED: ["Risiko diterima", "amber"],
  IN_PROGRESS: ["Berjalan", "blue"], DONE: ["Selesai", "green"], CANCELLED: ["Dibatalkan", ""],
  SUBMITTED: ["Menunggu tinjauan", "amber"], ACCEPTED: ["Diterima", "green"], REJECTED: ["Ditolak", "red"], EXPIRED: ["Kedaluwarsa", ""],
  CONCLUDED: ["Disimpulkan", "amber"], PENDING_SIGNOFF: ["Menunggu sign-off", "blue"], SIGNED_OFF: ["Sign-off", "green"],
  DRAFT: ["Draf", "amber"], ISSUED: ["Terbit", "green"], WITHDRAWN: ["Ditarik", "red"],
  PUBLISHED: ["Terbit", "green"], SEGMENTED_DRAFT: ["Draf segmentasi", "amber"], UNDER_CORRECTION: ["Dikoreksi", "amber"], IN_FORCE: ["Berlaku", "green"],
  EFFECTIVE: ["Efektif", "green"], PARTIALLY_EFFECTIVE: ["Sebagian efektif", "amber"], INEFFECTIVE: ["Tidak efektif", "red"],
  NOT_ASSESSED: ["Belum diasesmen", ""], NOT_TESTED: ["Belum diuji", ""], NOT_APPLICABLE: ["Tidak berlaku", ""],
};
export function Status({ s }: { s?: string | null }) {
  if (!s) return <span className="badge">—</span>;
  const [label, tone] = STATE_LABEL[s] || [s, ""];
  return <span className={`badge ${tone}`} title={s}>{label}</span>;
}
const SEV: Record<string, [string, string]> = { CRITICAL: ["Kritis", "#7a0916"], HIGH: ["Tinggi", "#b42318"], MEDIUM: ["Sedang", "#b54708"], LOW: ["Rendah", "#667085"] };
export function Sev({ s }: { s: string }) {
  const [l, c] = SEV[s] || [s, "#667085"];
  return <span className="sev" style={{ ["--c" as any]: c, color: c }}>{l}</span>;
}
export const SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

export function Cite({ c, onOpen }: { c?: { canonical_number?: string | null; number_label?: string | null; provision_version_id: string } | null; onOpen: (id: string) => void }) {
  if (!c) return null;
  return <button type="button" className="cite" onClick={() => onOpen(c.provision_version_id)}>{c.canonical_number} {c.number_label}</button>;
}
export function AiBadge() { return <span className="badge ai">Draf AI · perlu validasi manusia</span>; }
export function Empty({ children }: { children: ReactNode }) { return <div className="empty">{children}</div>; }
export function PageHead({ title, intro, crumbs, children }: { title: string; intro?: string; crumbs?: string; children?: ReactNode }) {
  return <div className="pagehead"><div>{crumbs && <div className="crumbs">{crumbs}</div>}<h1>{title}</h1>{intro && <p>{intro}</p>}</div>{children && <div className="row">{children}</div>}</div>;
}
export function Flow({ steps, now }: { steps: [string, string][]; now: string }) {
  const idx = steps.findIndex(s => s[0] === now);
  return <div className="flow" aria-label="Alur status">{steps.map(([k, l], i) => <span key={k} className={i < idx ? "done" : i === idx ? "now" : ""}>{l}</span>)}</div>;
}
export const fmtDate = (s?: string | null) => s ? new Date(s.length === 10 ? s + "T00:00:00" : s).toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" }) : "—";
export const fmtTime = (s?: string | null) => s ? new Date(s).toLocaleString("id-ID", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—";
export const inDays = (n: number) => new Date(Date.now() + n * 86400000).toISOString().slice(0, 10);

/** Izin UI = salinan matriks RBAC server (web/src/permissions.ts, dibangkitkan otomatis). Server tetap sumber kebenaran. */
const ACTION: Record<string, [string, string]> = {
  corpus_write: ["ingestion", "X"], obligation_extract: ["obligation", "C"], obligation_validate: ["obligation", "U"],
  obligation_approve: ["obligation", "A"], risk_control_write: ["control_library", "C"], evidence_upload: ["evidence_upload", "C"],
  evidence_review: ["evidence_request", "U"], assess: ["assessment_conclusion", "C"], signoff: ["assessment_conclusion", "A"],
  finding_create: ["finding", "C"], gap_scan: ["finding", "C"], action_create: ["remediation", "C"],
  closure_validate: ["finding_closure", "A"], closure_propose: ["finding_closure", "C"], report_generate: ["report_draft", "C"],
  report_issue: ["report_issue", "A"], audit_read: ["audit_trail", "R"], evidence_download: ["evidence_access", "R"],
  applicability_create: ["applicability", "C"], profile_update: ["org_profile", "U"],
  user_admin_read: ["user_admin", "R"], user_admin_write: ["user_admin", "C"], config_read: ["system_config", "R"],
  // [A7] registri sumber: daftarkan/ajukan = C (Analis, Admin); setujui, tangguhkan, pensiunkan = D (hanya Administrator,
  //      sama dengan penjagaan server yang mempersempit U ke Administrator)
  source_write: ["source_registry", "C"], source_approve: ["source_registry", "D"],
  // [A7] putusan tinjauan jawaban copilot = Promosi keluaran copilot (Analis, Pejabat, Peninjau Hukum)
  copilot_review: ["copilot_promote", "C"],
};
export const can = (role: Role, action: string): boolean => {
  const [cap, letter] = ACTION[action] || ["", ""];
  return !!cap && canDo(role, cap, letter);
};
/** Halaman → kapabilitas yang harus bisa DIBACA agar halaman/menu tampil. Peran tanpa akses tidak melihat halamannya. */
const PAGE_READ: Record<string, [string, string][]> = {
  beranda: [["dashboard", "R"]], cari: [["corpus_search", "R"]], copilot: [["copilot_query", "X"]],
  regulasi: [["source_registry", "R"], ["document_version", "R"]], perubahan: [["change_review", "R"]],
    katalog: [["corpus_search", "R"]], peraturan: [["corpus_search", "R"]],  // Katalog peraturan & halaman detail (semua peran)
  keberlakuan: [["applicability", "R"]], kewajiban: [["obligation", "R"]], kontrol: [["control_library", "R"]],
  asesmen: [["assessment_conclusion", "R"]], temuan: [["finding", "R"]], laporan: [["report_published", "R"]],
  audit: [["audit_trail", "R"]], admin: [["system_config", "R"], ["user_admin", "R"]],
  sumber: [["source_registry", "R"]],  // [A19] halaman Sumber regulasi
  "kontrol-saya": [["control_library", "R"]],
};
/** [A18] log interaksi copilot: Promosi keluaran copilot (R) atau Jejak audit (R) — sama dengan server */
export const canReadCopilotLog = (role: Role) => canDo(role, "copilot_promote", "R") || canDo(role, "audit_trail", "R");
/** Halaman yang hanya untuk peran tertentu. */
const ONLY_ROLE: Record<string, Role[]> = { "kontrol-saya": ["BUSINESS_CONTROL_OWNER"] };
/** Peran dengan layar khusus (sesuai mockup): hanya rute ini yang bisa dibuka. Hanya penataan UI; server tetap menegakkan RBAC. */
const ROLE_ROUTES: Partial<Record<Role, string[]>> = {
  EXECUTIVE: ["beranda", "laporan", "cari", "peraturan"],
  BUSINESS_CONTROL_OWNER: ["kontrol-saya", "temuan", "cari", "peraturan"],
};
/** Halaman awal setelah login. */
export const homeRoute = (role: Role): string => (role === "BUSINESS_CONTROL_OWNER" ? "kontrol-saya" : "beranda");

export const canSeePage = (role: Role, page: string): boolean => {
  if (ONLY_ROLE[page] && !ONLY_ROLE[page].includes(role)) return false;
  const allowed = ROLE_ROUTES[role];
  if (allowed && !allowed.includes(page)) return false;
  return (PAGE_READ[page] || [["dashboard", "R"]]).some(([c, l]) => canDo(role, c, l));
};

export function ImpactIcon({ level }: { level: "high" | "medium" | "low" }) {
  const c = level === "high" ? "#b42318" : level === "medium" ? "#b54708" : "#667085";
  const bars = level === "high" ? 3 : level === "medium" ? 2 : 1;
  return <svg className="impact-ico" viewBox="0 0 18 18" aria-label={`dampak ${level}`} role="img">
    {[0, 1, 2].map(i => <rect key={i} x={2 + i * 5.5} y={12 - i * 4} width="4" height={4 + i * 4} rx="1" fill={i < bars ? c : "#dde2ea"} />)}
  </svg>;
}

// ------------------------------------------------------------------------------------------------------
// [A8] Tampilan teks pasal: ayat (1), angka 1., huruf a. masing-masing di baris sendiri, menjorok sesuai tingkatnya.
// Teks asli di database TIDAK diubah; ini hanya cara menampilkan.
// ------------------------------------------------------------------------------------------------------
// Penanda butir di AWAL baris: "(1)" ayat · "1." / "1)" angka · "a." / "a)" huruf
const MARK_RE = /^(\(\d{1,3}\)|\d{1,3}[.)]|[a-z][.)])(?=\s|$)/;
// Baris nomor halaman hasil PDF, mis. "- 3 -" → dibuang
const PAGE_RE = /^-\s*\d+\s*-$/;
// Kata rujukan di akhir baris sebelumnya: "...dimaksud pada ayat" + "(1) dilaksanakan" adalah RUJUKAN, bukan ayat baru.
// Dicek per jenis penanda, agar "a. ...; dan" + "b. ..." tetap terpecah menjadi dua huruf.
const REF_END: Record<string, RegExp> = { ayat: /\bayat$/i, huruf: /\bhuruf$/i, angka: /\b(angka|pasal|butir|nomor)$/i };
// Judul butir penjelasan, mis. "Ayat (1)", "Huruf a", "Angka 3" → paragraf baru
const PENJ_RE = /^(Ayat \(\d{1,3}\)|Huruf [a-z]|Angka \d{1,3})(\s|$)/;
type Line = { mark: string; text: string; depth: number };

/** Ubah teks mentah menjadi baris-baris butir. Penanda hanya dikenali di awal baris teks asli,
 *  jadi rujukan di tengah kalimat ("ayat (1) huruf a") tidak ikut terpecah. */
export function splitPasal(raw: string): Line[] {
  const lines: Line[] = [];
  const kinds: string[] = [];  // urutan jenis penanda yang muncul → menentukan tingkat jorokan
  let cur: Line | null = null, blank = false;
  for (const rawLine of (raw || "").split(/\r?\n/)) {
    const t = rawLine.replace(/\s+/g, " ").trim();
    if (!t) { blank = true; continue; }
    if (PAGE_RE.test(t)) continue;
    const m = t.match(MARK_RE);
    const kind = !m ? "" : m[1].startsWith("(") ? "ayat" : /^\d/.test(m[1]) ? "angka" : "huruf";
    if (m && !(cur && REF_END[kind].test(cur.text))) {
      const mark = m[1];
      if (!kinds.includes(kind)) kinds.push(kind);
      cur = { mark, text: t.slice(mark.length).trim(), depth: kinds.indexOf(kind) };
      lines.push(cur);
    } else if (!cur || PENJ_RE.test(t) || (blank && /[.:;]$/.test(cur.text))) {
      // paragraf baru: awal teks, judul butir penjelasan, atau baris kosong setelah kalimat selesai (mis. "Cukup jelas.")
      cur = { mark: "", text: t, depth: 0 };
      lines.push(cur);
    } else {
      cur.text += (cur.text ? " " : "") + t;  // lanjutan baris yang terpotong PDF
    }
    blank = false;
  }
  return lines;
}

export function PasalText({ text, className = "" }: { text: string; className?: string }) {
  const lines = splitPasal(text);
  return <div className={`verbatim pasal ${className}`} lang="id">{lines.map((l, i) =>
    <div key={i} className={l.mark ? "pasal-item" : "pasal-para"} style={{ marginLeft: `${l.depth * 1.6}em` }}>
      {l.mark && <span className="pasal-mark">{l.mark}</span>}<span>{l.text}</span>
    </div>)}</div>;
}
/** Jenis instrumen yang bisa dipilih di form dokumen (SEOJK = Surat Edaran OJK, SEBI = Surat Edaran BI). */
export const INSTRUMENT_TYPES = ["UU", "PERPPU", "PP", "PERPRES", "KEPPRES", "PMK", "PERMEN", "POJK", "SEOJK", "PADK", "PDK",
  "PBI", "PADG", "SEBI", "PPATK", "PERDA", "PUTUSAN", "OTHER"];

/** Cuplikan hasil pencarian: bagian yang cocok dibungkus [[...]] oleh server → ditandai dengan <mark>. */
export function Highlight({ text }: { text: string }) {
  return <>{text.split(/(\[\[[\s\S]*?\]\])/g).map((p, i) =>
    p.startsWith("[[") && p.endsWith("]]") ? <mark key={i}>{p.slice(2, -2)}</mark> : <span key={i}>{p}</span>)}</>;
}
