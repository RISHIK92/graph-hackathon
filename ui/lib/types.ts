// Shapes returned by api/app.py and brain/tools.py (evidence packs, 03 §1.1).

export type Label = "graph" | "text_only" | "unverified_path" | string;

export interface Fact {
  assertion_id: string;
  run_id: string;
  predicate: string;
  qualifier?: string;
  subject_id: string;
  object_id: string;
  object_value?: string;
  negated: boolean;
  valid_from: number;
  valid_to: number;
  status: string; // current | superseded | disputed | proposed | retracted | unknown_at_T
  authority: number;
  statement: string;
  recorded_at?: number;
  open_disputes: string[];
  action_id?: string;
  confirmed_by?: { assertion_id: string };
  overruled_by?: { confirmed_at: number; run_id: string };
}

export interface SpanItem {
  span_id: string;
  text: string;
  source_id: string;
  doc_key?: string;
  uri?: string;
  title?: string;
  kind?: string;
  ts?: number;
  char_start?: number;
  char_end?: number;
  live: boolean;
  cites: string[];
  section?: string;
  form?: string;
  authority?: number;
  quote_start?: number | null;
  quote_end?: number | null;
}

export interface PathNode {
  id: string;
  labels: string[];
  name: string;
}
export interface PathEdge {
  type: string;
  aid: string;
  valid_from: number | null;
  valid_to: number | null;
}
export interface PathStep {
  node: PathNode;
  edge: PathEdge | null;
  evidence?: SpanItem[];
}
export interface Path {
  path_id: string;
  steps: PathStep[];
}

export interface ActionSummary {
  action_id: string;
  kind?: string;
  status?: string;
  actor?: { id: string; name: string };
  recorded_at?: number;
  eligibility?: string;
  summary?: string;
  based_on?: string[];
  produced?: string[];
  sources?: string[];
  targets?: string[];
  undone_at?: number;
}

export interface PackItem {
  item_id: string;
  label: Label;
  score: number;
  path: Path | null;
  facts: Fact[];
  actions: ActionSummary[];
  spans: SpanItem[];
  rows: Record<string, unknown>[] | null;
  note: string;
  then_now?: {
    then: { based_on: Fact[]; produced: Fact[] };
    now: { based_on: Fact[]; produced: Fact[] };
  };
  changed_since?: { assertion_id: string; then: string; now: string; statement: string }[];
  confirms?: { proposal: string; confirmed: string; status: string; action: string | null }[];
}

export interface Pack {
  pack_id: string;
  tool: string;
  args: Record<string, unknown>;
  as_of: number;
  belief_at: number | null;
  items: PackItem[];
}

export interface Person {
  id: string;
  name: string;
  title?: string;
  team: string[];
  leads: string[];
  decides: string[];
}

export interface Eligible {
  person_id: string;
  name: string;
  rule: string;
  path: string;
  aids?: string[];
  path_id?: string;
}

export interface ConfirmPreview {
  admissible: boolean;
  refusal: string | null;
  eligible: Eligible[];
  fallback: boolean;
  actor_eligible: boolean;
  missing_fact?: string | null;
  request_id: string;
}

export interface UndoPreview {
  allowed: boolean;
  undoers: Eligible[];
  reason: string | null;
}

export interface Refusal {
  refused: boolean;
  reason: string;
  eligible: Eligible[];
  fallback_available: boolean;
  action_id: string;
}

export interface WriteResult {
  refusal?: Refusal;
  action_id?: string;
  pack?: Pack;
  [k: string]: unknown;
}

export interface ActionView {
  pack: Pack;
  undo: UndoPreview;
  draft_source: string | null;
  request_id: string;
}

export interface Ref {
  id: string;
  name: string;
  aid?: string;
  disputed?: boolean;
}

export interface Overview {
  as_of: number;
  teams: { id: string; name: string; leads: Ref[]; members: Ref[]; owns: Ref[] }[];
  decisions: { id: string; name: string; title: string; aid: string; affects: Ref[] }[];
  pending: { action_id: string; kind: string; summary: string }[];
}

export interface EntityPanel {
  id: string;
  name: string;
  d?: string;
  labels: string[];
  owner?: Pack;
  depended_on_by?: Pack;
  depends_on?: Ref[];
  decisions?: Pack;
  lead?: Ref[];
  history: Record<string, Pack>;
  sources: { kind: string; sources: { id: string; title: string }[] }[];
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  aid: string;
  vf: number;
  vt: number;
  authority: number;
  kinds: string[];
}
export interface GraphData {
  as_of: number;
  nodes: { id: string; name: string; labels: string[] }[];
  edges: GraphEdge[];
  disputed: { run: string; assertion_id: string; source: string; target: string; statement: string }[];
  stale: { source: string; target: string; doc: string; why: string; span: string; statement: string }[];
  ticks: number[];
}

export interface Claim {
  claim_id: string;
  text: string;
  tense: string;
  assertion_ids: string[];
  span_ids: string[];
  action_ids: string[];
  path_id?: string | null;
  label: Label;
  disputed: boolean;
  quote?: string;
}

export interface Line {
  claim_id: string;
  text: string;
  status: string;
  also?: string[];
}

export interface QueryLog {
  template: string;
  cypher: string;
  params: Record<string, unknown>;
  rows: number;
  ms: number;
  hash?: string;
  unverified?: boolean;
}

export interface Trace {
  turn_id: string;
  tool_calls: { name: string; args: Record<string, unknown>; pack_id: string; queries: QueryLog[] }[];
  verification: { kept: number; dropped: unknown[]; rewritten: unknown[] } | null;
  packs?: Record<string, Pack>;
}

export interface SpanView {
  text: string;
  kind: string;
  ts: number;
  revisions: { source: string; title: string; uri: string; cs: number; ce: number; latest: boolean; live: boolean }[];
}

export interface SourceView {
  source: Record<string, unknown> & { id: string; kind?: string; title?: string; uri?: string; is_latest?: boolean };
  spans: { span: string; text: string; cs: number; ce: number; ord: number }[];
  text: string;
  banner?: string;
}

// Directory (GET /directory)
export interface DirRef { id: string; name: string; aid?: string; disputed?: boolean }
export interface DirSystem { id: string; name: string; description?: string; owner: DirRef | null; project: DirRef | null; depends_on: number; depended_on_by: number; decisions: number; disputed: boolean }
export interface DirProject { id: string; name: string; description?: string; owner: DirRef | null; systems: DirRef[]; people: number; disputed: boolean }
export interface DirPerson { id: string; name: string; title?: string; team: DirRef | null; leads: DirRef[]; decides: DirRef[]; tickets: number; disputed: boolean }
export interface DirDecision { id: string; name: string; title?: string; description?: string; status?: string; decided_at?: number | null; affects: DirRef[]; deciders: DirRef[]; replaces: DirRef[]; replaced_by: DirRef[]; disputed: boolean }
export interface DirTicket { id: string; name: string; description?: string; about: DirRef | null; assignee: DirRef | null; state?: string | null; disputed: boolean }
export interface Directory {
  as_of: number;
  teams: Overview["teams"];
  systems: DirSystem[];
  projects: DirProject[];
  people: DirPerson[];
  decisions: DirDecision[];
  tickets: DirTicket[];
}

export interface PendingItem { type: string; action_id?: string; assertion_id?: string; summary: string; fallback: boolean; kind?: string }
export interface PendingData {
  awaiting: PendingItem[];
  mine: { action_id: string; kind: string; summary: string }[];
  log: { id: string; kind: string; status: string; summary: string; at: number; undo?: UndoPreview }[];
}

export type NameMap = Record<string, { id?: string; name: string; label: string }>;
