// The only way the UI reaches data: the Python HTTP API (04 §1). Never the database.

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

const TOKEN_KEY = "brain.token";

export function getToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setToken(t: string): void {
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: token lives for this page only */
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function headers(json = false): HeadersInit {
  const h: Record<string, string> = {};
  const t = getToken();
  if (t) h["Authorization"] = `Bearer ${t}`;
  if (json) h["Content-Type"] = "application/json";
  return h;
}

/** Resolve entity ids (prefixed or bare) to names and labels; cached by the store. */
export async function fetchNames(ids: string[]): Promise<Record<string, { id?: string; name: string; label: string }>> {
  if (!ids.length) return {};
  return get(`/names${qs({ ids: ids.join(",") })}`);
}

export function qs(params: Record<string, string | number | null | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== "") p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

async function parseResponse<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = r.statusText;
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {
      /* not JSON */
    }
    throw new ApiError(r.status, msg || `HTTP ${r.status}`);
  }
  return r.json() as Promise<T>;
}

// m16: several components asking for the same thing at once (an action record's panel, chips, page)
// share one request instead of each fetching it
const inflight = new Map<string, Promise<unknown>>();

export function get<T>(path: string): Promise<T> {
  const key = `${path}|${getToken()}`;
  const hit = inflight.get(key);
  if (hit) return hit as Promise<T>;
  const req = fetch(`${API_URL}${path}`, { headers: headers(), cache: "no-store" })
    .then((r) => parseResponse<T>(r))
    .finally(() => inflight.delete(key));
  inflight.set(key, req);
  return req;
}

export async function send<T>(method: "POST" | "PUT", path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API_URL}${path}`, { method, headers: headers(true), body: JSON.stringify(body ?? {}) });
  return parseResponse<T>(r);
}

export interface StreamEvent {
  event: string;
  [k: string]: unknown;
}

/** POST a turn and parse the server-sent event stream (04 §1.1) as it arrives. */
export async function streamTurn(
  sessionId: string,
  body: { text: string; as_of?: number | null; transcript?: { role: string; text: string }[] },
  onEvent: (e: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const r = await fetch(`${API_URL}/sessions/${encodeURIComponent(sessionId)}/turns`, {
    method: "POST",
    headers: { ...headers(true), Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!r.ok || !r.body) {
    await parseResponse(r);
    return;
  }
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let i: number;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const data = block
        .split("\n")
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).replace(/^ /, ""))
        .join("\n");
      const evName = block
        .split("\n")
        .find((l) => l.startsWith("event:"))
        ?.slice(6)
        .trim();
      if (!data) continue;
      try {
        const j = JSON.parse(data);
        onEvent({ ...j, event: j.event || evName || "message" });
      } catch {
        /* keep-alive or malformed */
      }
    }
  }
}
