import type { Fact, SpanItem } from "./types";

export const MAX_MS = 9007199254740991;

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "12 Mar 2026" (UTC). Sentinels: open interval → "now", epoch start → "start". */
export function fmtDate(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "?";
  if (ms >= MAX_MS) return "now";
  if (ms <= 0) return "start";
  const d = new Date(ms);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

/** B3: a confirmed proposal is resolved: "Approved by Priya Raman, 14 Oct 2026". */
export function approvedText(c: NonNullable<Fact["confirmed_by"]>): string {
  return `Approved${c.by ? ` by ${c.by}` : ""}${c.at ? `, ${fmtDate(c.at)}` : ""}.`;
}

/** "12 Mar 2026, 15:07 UTC" */
export function fmtDateTime(ms: number | null | undefined): string {
  if (!ms) return "?";
  if (ms >= MAX_MS) return "now";
  const d = new Date(ms);
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${fmtDate(ms)}, ${hh}:${mm} UTC`;
}

export function fmtInterval(from: number | null | undefined, to: number | null | undefined): string {
  return `${fmtDate(from)} → ${fmtDate(to)}`;
}

export function fmtAge(ms: number | null | undefined): string {
  if (!ms) return "";
  const s = Math.max(0, (Date.now() - ms) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 14) return `${Math.floor(s / 86400)} d ago`;
  return fmtDate(ms);
}

/** The display status of a fact (04 §2.2). */
export type DisplayStatus =
  | "current" | "current_then" | "historical" | "disputed" | "overruled" | "proposed" | "confirmed" | "withdrawn" | "retracted" | "unknown";

/** With an As-of date, a since-replaced fact that held on that date is "Current then", not "Historical" (M11). */
export function factStatus(f: Fact, asOf?: number | null): DisplayStatus {
  switch (f.status) {
    case "current": return "current";
    case "superseded": return asOf && f.valid_from <= asOf && asOf < f.valid_to ? "current_then" : "historical";
    case "disputed": return f.overruled_by ? "overruled" : "disputed";
    case "proposed": return f.confirmed_by ? "confirmed" : "proposed";
    case "retracted": return f.action_id ? "withdrawn" : "retracted";
    case "unknown_at_T": return "unknown";
    default: return (f.status as DisplayStatus) || "unknown";
  }
}

/** Status → semantic encoding (DESIGN.md §3.2). Colour never alone: dot shape + word. */
export function statusTone(st: string): { tone: "success" | "error" | "accent" | "neutral" | "warning"; dot: string; strike?: boolean } {
  switch (st) {
    case "current": case "current_then": case "confirmed": case "done": case "accepted": return { tone: "success", dot: "dot success" };
    // A dispute needs review, it isn't an error (M19): amber, the same on both sides
    case "disputed": return { tone: "warning", dot: "dot warning" };
    case "refused": return { tone: "error", dot: "dot error" };
    case "proposed": case "waiting": return { tone: "accent", dot: "dot accent" };
    case "approved": return { tone: "success", dot: "dot success" };
    case "overruled": case "withdrawn": case "retracted": case "undone": return { tone: "neutral", dot: "dot", strike: true };
    case "unknown": return { tone: "neutral", dot: "dot dashed" };
    case "rejected": return { tone: "neutral", dot: "dot hollow", strike: true };
    case "historical": case "superseded": default: return { tone: "neutral", dot: "dot hollow" };
  }
}

export function spansFor(spans: SpanItem[] | undefined, aid: string): SpanItem[] {
  // One chip per span: several run members cite the same span (B4 duplicate keys, m2 duplicate chips).
  const seen = new Set<string>();
  return (spans || []).filter((s) => s.cites?.includes(aid) && !seen.has(s.span_id) && !!seen.add(s.span_id));
}

export function labelOf(labels: string[] | undefined, id?: string): string {
  const l = (labels || []).find((x) => x !== "Entity");
  if (l) return l;
  if (id && id.includes(":")) {
    const p = id.split(":")[0];
    return p.charAt(0).toUpperCase() + p.slice(1);
  }
  return "Entity";
}

export function dateInputValue(ms: number | null): string {
  return ms ? new Date(ms).toISOString().slice(0, 10) : "";
}

/** End of the chosen UTC day, so changes dated that day are included. */
export function fromDateInput(v: string): number | null {
  if (!v) return null;
  const t = Date.parse(`${v}T23:59:59.999Z`);
  return Number.isNaN(t) ? null : t;
}

export const SOURCE_KINDS = ["catalog", "roster", "ticket", "wiki", "meeting", "adr", "chat"];

export const ENTITY_LABELS = ["Team", "Person", "System", "Project", "Decision", "Ticket"];

export function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase() || "").join("");
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}
