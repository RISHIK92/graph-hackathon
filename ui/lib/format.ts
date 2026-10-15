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

export const STATUS_LABEL: Record<string, string> = {
  current: "Current", current_then: "Current then", historical: "Historical", disputed: "Disputed", overruled: "Overruled", proposed: "Proposed",
  confirmed: "Confirmed", withdrawn: "Withdrawn", retracted: "Retracted", unknown: "Unknown at date",
  done: "Done", waiting: "Waiting for approval", approved: "Approved", refused: "Refused", undone: "Undone", superseded: "Superseded", accepted: "Accepted", rejected: "Rejected", open: "Open", closed: "Closed",
};

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

/** Humanised name from an id: "system:postgres-main" → "Postgres Main". */
export function entityName(id: string): string {
  const tail = id.includes(":") ? id.split(":").slice(1).join(":") : id;
  return tail.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
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

export const KIND_LABEL: Record<string, string> = {
  catalog: "Catalogue", roster: "Roster", ticket: "Ticket", wiki: "Wiki", meeting: "Meeting note", adr: "ADR",
  chat: "Chat", chat_session: "Session", session: "Session", draft: "Agent draft", confirmation: "Confirmation",
};

/** "history of ch_DEPENDS_ON:system:checkout>system:ledger" → "Checkout depends on Ledger". */
export function chainLabel(note: string): string {
  const m = note.match(/ch_([A-Z_]+):([^>]+)>(.+)$/);
  if (!m) return note.replace(/^history of /, "");
  return `${entityName(m[2])} ${edgeVerb(m[1])} ${entityName(m[3])}`;
}

export const SOURCE_KINDS = ["catalog", "roster", "ticket", "wiki", "meeting", "adr", "chat"];
export const ENTITY_LABELS = ["Team", "Person", "System", "Project", "Decision", "Ticket"];

/** Predicate → human section name. */
export const PREDICATE_LABEL: Record<string, string> = {
  OWNS: "Ownership", LEADS: "Lead", DEPENDS_ON: "Depends on", PART_OF: "Part of", AFFECTS: "Affects",
  MEMBER_OF: "Membership", ASSIGNED_TO: "Assignee", HAS_STATE: "State", ABOUT: "About", HAS_STATUS: "Status",
  REPLACES: "Replaces", WORKS_ON: "Works on", DECIDED_BY: "Decided by",
};
export function predicateLabel(p: string): string {
  return PREDICATE_LABEL[p] || p.toLowerCase().replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
const REVERSE_VERB: Record<string, string> = {
  OWNS: "is owned by", LEADS: "is led by", DEPENDS_ON: "is depended on by", PART_OF: "includes", AFFECTS: "is affected by",
  MEMBER_OF: "has member", ASSIGNED_TO: "has assigned", ABOUT: "is the subject of", REPLACES: "is replaced by",
  WORKS_ON: "is worked on by", DECIDED_BY: "decided",
};

/** Edge type as a verb phrase for paths: "owns", "depends on"; walked backwards, "is owned by" (M14). */
export function edgeVerb(t: string, dir?: "forward" | "backward"): string {
  if (dir === "backward" && REVERSE_VERB[t]) return REVERSE_VERB[t];
  const m: Record<string, string> = {
    OWNS: "owns", LEADS: "leads", DEPENDS_ON: "depends on", PART_OF: "is part of", AFFECTS: "affects",
    MEMBER_OF: "is a member of", ASSIGNED_TO: "is assigned to", ABOUT: "is about", REPLACES: "replaces",
    WORKS_ON: "works on", DECIDED_BY: "was decided by", HAS_STATE: "has state", HAS_STATUS: "has status",
  };
  return m[t] || t.toLowerCase().replace(/_/g, " ");
}

export const ACTION_KIND_LABEL: Record<string, string> = {
  route_to_owner: "Route to owner", learn_fact: "Record a fact", draft_adr_supersession: "Draft ADR supersession",
  confirm_fact: "Confirmation", undo: "Undo",
};
export function actionKindLabel(k?: string): string {
  if (!k) return "Action";
  return ACTION_KIND_LABEL[k] || k.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export const ELIGIBILITY_LABEL: Record<string, string> = {
  holder: "Holder", receiver: "Receiver", owner_lead: "Owner's lead", ticket_leads: "Ticket's lead", team_lead: "Team lead",
  decider: "Decider", requester: "Requester",
};
export function eligibilityLabel(e?: string | null): string {
  if (!e) return "";
  if (e.startsWith("fallback")) return "Fallback: any team lead";
  return ELIGIBILITY_LABEL[e] || e.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

/** Planner intent → human. */
export function intentLabel(i?: string): string {
  const m: Record<string, string> = {
    ownership: "Ownership", expertise: "Expertise", impact: "Impact", decision: "Decision trace", history: "History",
    action: "Action", pending: "Pending", path: "Connection", general: "Question",
  };
  if (!i) return "Question";
  return m[i] || i.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase() || "").join("");
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}
