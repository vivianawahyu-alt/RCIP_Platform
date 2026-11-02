import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { Me, Role } from "./types";

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
  ACTIVE: ["Aktif", "green"], REVIEW_REQUIRED: ["Perlu ditinjau", "red"], SUPERSEDED: ["Digantikan", ""], RETIRED: ["Pensiun", ""],
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

/** Matriks izin UI (cermin dari otorisasi server; server tetap sumber kebenaran). */
export const can = (role: Role, action: string): boolean => {
  const M: Record<string, Role[]> = {
    corpus_write: ["REGULATORY_ANALYST"], obligation_extract: ["COMPLIANCE_OFFICER"], obligation_validate: ["COMPLIANCE_OFFICER"],
    obligation_approve: ["COMPLIANCE_MANAGER"], risk_control_write: ["COMPLIANCE_OFFICER"], evidence_upload: ["COMPLIANCE_OFFICER", "BUSINESS_CONTROL_OWNER"],
    evidence_review: ["COMPLIANCE_OFFICER"], assess: ["COMPLIANCE_OFFICER"], signoff: ["COMPLIANCE_MANAGER"],
    finding_create: ["COMPLIANCE_OFFICER"], gap_scan: ["COMPLIANCE_OFFICER", "COMPLIANCE_MANAGER"],
    action_create: ["COMPLIANCE_OFFICER", "BUSINESS_CONTROL_OWNER"], closure_validate: ["COMPLIANCE_MANAGER"],
    report_generate: ["COMPLIANCE_OFFICER"], report_issue: ["COMPLIANCE_MANAGER"],
    audit_read: ["INTERNAL_AUDITOR", "SYSTEM_ADMINISTRATOR", "COMPLIANCE_MANAGER", "LEGAL_REVIEWER", "REGULATORY_ANALYST", "COMPLIANCE_OFFICER"],
    evidence_download: ["REGULATORY_ANALYST", "COMPLIANCE_OFFICER", "BUSINESS_CONTROL_OWNER", "LEGAL_REVIEWER", "COMPLIANCE_MANAGER", "INTERNAL_AUDITOR"],
  };
  return (M[action] || []).includes(role);
};

export function ImpactIcon({ level }: { level: "high" | "medium" | "low" }) {
  const c = level === "high" ? "#b42318" : level === "medium" ? "#b54708" : "#667085";
  const bars = level === "high" ? 3 : level === "medium" ? 2 : 1;
  return <svg className="impact-ico" viewBox="0 0 18 18" aria-label={`dampak ${level}`} role="img">
    {[0, 1, 2].map(i => <rect key={i} x={2 + i * 5.5} y={12 - i * 4} width="4" height={4 + i * 4} rx="1" fill={i < bars ? c : "#dde2ea"} />)}
  </svg>;
}
