let token = sessionStorage.getItem("rcip_token") || "";
export const setToken = (t: string) => { token = t; t ? sessionStorage.setItem("rcip_token", t) : sessionStorage.removeItem("rcip_token"); };
export const hasToken = () => !!token;

// [A5] offending = detail tambahan dari server (mis. dokumen yang sudah ada saat DUPLICATE_SUSPECTED)
export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number, public offending?: any) { super(message); }
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; form?: FormData } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.body); }
  const res = await fetch(`/api/v1${path}`, { method: opts.method || (body ? "POST" : "GET"), headers, body });
  const json = await res.json().catch(() => ({}));
  if (res.status === 401 && token) { setToken(""); sessionStorage.removeItem("rcip_me"); }
  if (!res.ok) {
    const detail = Array.isArray(json.detail) ? json.detail.map((d: any) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join("; ") : json.detail;
    throw new ApiError(json.error_code || String(res.status), json.message || detail || "Permintaan gagal", res.status, json.offending);
  }
  return json.data as T;
}

/** Unduh berkas biner (bukti, ekspor CSV) dengan token. */
export async function download(path: string, filename: string) {
  const res = await fetch(`/api/v1${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) { const j = await res.json().catch(() => ({})); throw new ApiError(j.error_code || String(res.status), j.message || "Unduhan gagal", res.status); }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a"); a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** [A6] Buka berkas (mis. PDF asli versi regulasi) di tab baru dengan token.
 *  Tab dibuka lebih dulu (sinkron, saat klik) agar tidak diblokir pemblokir pop-up, lalu diisi setelah berkas terunduh. */
export async function openFile(path: string) {
  const tab = window.open("", "_blank");
  try {
    const res = await fetch(`/api/v1${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!res.ok) { const j = await res.json().catch(() => ({})); throw new ApiError(j.error_code || String(res.status), j.message || "Berkas tidak dapat dibuka", res.status); }
    const url = URL.createObjectURL(await res.blob());
    if (tab) tab.location.href = url; else window.open(url, "_blank");
    setTimeout(() => URL.revokeObjectURL(url), 60000);  // beri waktu tab memuat berkas
  } catch (e) { tab?.close(); throw e; }
}
