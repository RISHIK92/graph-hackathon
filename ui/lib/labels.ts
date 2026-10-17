/** Every user-facing label in one place (item 16, M17/copy table): relations, source kinds, statuses, chips,
 * eligibility, action kinds, intents and id -> display name. Components never inline these strings. */

export const STATUS_LABEL: Record<string, string> = {
  current: "Current", current_then: "Current then", historical: "Historical", disputed: "Disputed", overruled: "Overruled", proposed: "Proposed",
  confirmed: "Confirmed", withdrawn: "Undone", retracted: "Retracted", unknown: "Unknown at date",
  done: "Done", waiting: "Waiting for approval", approved: "Approved", refused: "Refused", undone: "Undone", superseded: "Superseded", accepted: "Accepted", rejected: "Rejected", open: "Open", closed: "Closed",
};

/** Humanised name from an id: "system:postgres-main" → "Postgres Main". */
export function entityName(id: string): string {
  const tail = id.includes(":") ? id.split(":").slice(1).join(":") : id;
  return tail.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export const KIND_LABEL: Record<string, string> = {
  catalog: "Catalogue", roster: "Roster", ticket: "Ticket", wiki: "Wiki", meeting: "Meeting note", adr: "ADR",
  chat: "Chat", chat_session: "Chat", session: "Chat", draft: "Agent draft", confirmation: "Confirmed",
};

/** Where a source was written (item 24): the product name for "Open in …" and the in-app source view. */
export const SYSTEM_LABEL: Record<string, string> = {
  slack: "Slack", linear: "Linear", github: "GitHub", jira: "Jira", confluence: "Confluence", backstage: "Backstage",
  repo: "the repository", hr: "the HR roster", notes: "meeting notes", upload: "the uploaded file",
};

/** "history of ch_DEPENDS_ON:system:checkout>system:ledger" → "Checkout depends on Ledger". */
export function chainLabel(note: string): string {
  const m = note.match(/ch_([A-Z_]+):([^>]+)>(.+)$/);
  if (!m) return note.replace(/^history of /, "");
  return `${entityName(m[2])} ${edgeVerb(m[1])} ${entityName(m[3])}`;
}

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
  holder: "Owner's lead or decider", receiver: "Receiver", owner_lead: "Owner's lead", ticket_leads: "Ticket's lead", team_lead: "Team lead",
  decider: "Decider", requester: "Requester",
};

export function eligibilityLabel(e?: string | null): string {
  if (!e) return "";
  if (e.startsWith("fallback")) return "No team lead. Any team lead can decide.";
  return ELIGIBILITY_LABEL[e] || e.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

/** Planner intent → human. */
export function intentLabel(i?: string): string {
  const m: Record<string, string> = {
    ownership: "Ownership", expertise: "Expertise", impact: "Impact", decision_trace: "Decision", history: "History",
    memory: "Earlier in this chat", aggregate: "Count", fact: "Fact",
    action: "Action", pending: "Pending", path: "Connection", general: "Question",
  };
  if (!i) return "Question";
  return m[i] || i.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

/** How a citation's source reads after its kind: "ADR (text)", "Wiki (earlier version)" (copy table). */
export function sourceSuffix(label: string | undefined, live: boolean): string {
  const how = label === "text_only" ? " (text)" : label === "graph" || !label ? "" : " (unverified)";
  return how + (live ? "" : " (earlier version)");
}

const RAW_ID = /\b(system|person|team|project|decision|ticket):[a-z0-9][a-z0-9-]*/g;

/** Raw ids inside source text ("person:ana-costa commented …") read as names (M17). */
export function displayText(text: string): string {
  return text.replace(RAW_ID, (id) => entityName(id));
}

/** Source kinds as the Graph filter names them: imported chat versus this app's own chat (m10). */
export function filterKindLabel(k: string): string {
  return k === "chat_session" ? "Chat in this app" : k === "chat" ? "Chat (imported)" : KIND_LABEL[k] || k;
}
