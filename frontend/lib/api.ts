import type {
  Activity,
  ClientHome,
  CoachClientDetail,
  CoachClientRow,
  PlanDoc,
  Profile,
  SessionDetail,
  WeekPlan,
} from "./types";

// Same-origin proxy by default (see next.config.ts). Set NEXT_PUBLIC_API_URL to call the backend directly.
export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function messageFrom(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d.length) {
      // FastAPI validation errors: [{loc, msg}]
      return d.map((e: { loc?: unknown[]; msg?: string }) => `${(e.loc ?? []).slice(1).join(".")}: ${e.msg}`).join("; ");
    }
  }
  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && typeof init.body === "string") headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers, credentials: "include" });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check your internet connection and try again.");
  }
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, messageFrom(body, `Something went wrong (${res.status}).`));
  }
  const ct = res.headers.get("content-type") ?? "";
  return (ct.includes("application/json") ? res.json() : (res.blob() as unknown)) as Promise<T>;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  // ---- coach
  login: (password: string) => request<{ ok: boolean }>("/coach/login", json("POST", { password })),
  logout: () => request<{ ok: boolean }>("/coach/logout", json("POST")),
  me: () => request<{ ok: boolean; voice_enabled: boolean }>("/coach/me"),
  clients: () => request<CoachClientRow[]>("/coach/clients"),
  createClient: (name: string) =>
    request<{ id: string; token: string; link: string }>("/coach/clients", json("POST", { name })),
  client: (id: string) => request<CoachClientDetail>(`/coach/clients/${id}`),
  patchClient: (id: string, patch: Partial<Profile> & { coach_notes?: string | null }) =>
    request<{ ok: boolean }>(`/coach/clients/${id}`, json("PATCH", patch)),
  clientActivity: (id: string) => request<Activity>(`/coach/clients/${id}/activity`),
  generatePlan: (id: string) => request<PlanDoc>(`/coach/clients/${id}/plan`, json("POST")),
  approvePlan: (planId: string, plan?: WeekPlan) =>
    request<{ ok: boolean; plan: WeekPlan; notes: string[] }>(`/plans/${planId}/approve`, json("POST", { plan })),
  session: (id: string) => request<SessionDetail>(`/sessions/${id}`),
  approveSession: (id: string, client_message: string, progress_message: string | null, coach_note: string | null) =>
    request<{ ok: boolean }>(`/sessions/${id}/approve`, json("POST", { client_message, progress_message, coach_note })),
  voiceNote: (id: string, text: string) => request<Blob>(`/sessions/${id}/voice`, json("POST", { text })),
  overlayUrl: (id: string) => `${API_BASE}/sessions/${id}/overlay.mp4`,

  // ---- client (private link token)
  home: (token: string) => request<ClientHome>(`/c/${token}`),
  putProfile: (token: string, profile: Record<string, unknown>) =>
    request<{ ok: boolean }>(`/c/${token}/profile`, json("PUT", profile)),
  activity: (token: string) => request<Activity>(`/c/${token}/activity`),
};

/** Upload with progress (fetch cannot report upload progress). */
export function uploadVideo(
  token: string,
  form: FormData,
  onProgress: (pct: number) => void,
): Promise<{ session_id: string; status: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/c/${token}/videos`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
    xhr.onerror = () => reject(new ApiError(0, "The upload failed. Check your internet connection and try again."));
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* ignore */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as { session_id: string; status: string });
      else reject(new ApiError(xhr.status, messageFrom(body, `The upload failed (${xhr.status}).`)));
    };
    xhr.send(form);
  });
}
