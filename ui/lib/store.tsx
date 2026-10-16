"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { fetchNames, get, getToken, send, setToken as saveToken, type StreamEvent } from "./api";
import type { Claim, Line, NameMap, Pack, Path, Person } from "./types";

// inspector views (DESIGN.md §2.3: one panel, one level, breadcrumb inside)

export interface EvidenceTarget {
  tab: "source" | "path" | "timeline";
  spanId?: string;
  sourceId?: string;
  quote?: { start?: number | null; end?: number | null };
  path?: Path | null;
  pathId?: string | null;
  packId?: string | null;
  /** all paths of an impact pack, shown by Expand instead of the neighbourhood (04 §2.3) */
  impactPaths?: Path[];
  timeline?: { entityId: string; predicate: string } | null;
  title?: string;
  /** the packs the citation came from, for edge status and evidence in the Path tab */
  packs?: Pack[];
  /** whether packs are from a turn (so GET /paths can resolve per-edge evidence) */
  fromTurn?: boolean;
}

export type InspectorView =
  | { kind: "entity"; id: string; name?: string; tab?: string }
  | { kind: "evidence"; target: EvidenceTarget }
  | { kind: "action"; id: string }
  | { kind: "edge"; aid: string; source: string; target: string; type: string; edgeKind: "normal" | "disputed" | "stale"; label?: string }
  | { kind: "trace"; turnId: string }
  | { kind: "inbox"; actionId?: string; assertionId?: string; summary: string };

/** One Ask turn as the page shows it. */
export interface Turn {
  text: string;
  at: number;
  asOf: number | null;
  stages: StreamEvent[];
  answer?: { claims: Claim[]; abstained: boolean; assembled: {
    lines: Line[]; explanation: string; lead?: string;
    /** The answer contract (item 20): the claims line 1 states, lines left out, a status line and a next step. */
    lead_claims?: string[]; more?: number; status?: { kind: string; text: string } | null; next?: string | null;
  }; packs: Record<string, Pack>; nearest?: (Path | null)[]; missing?: string[];
    /** A reply about the assistant itself (what it can do), not an answer about the graph. */
    help?: boolean };
  actions: StreamEvent[];
  turnId?: string;
  actor: string;   // who asked: the acting person at the time, not whoever is acting now (M2)
  writeSeq: number;
  done: boolean;
  error?: string;
}

export interface Toast {
  id: number;
  tone: "success" | "info" | "warning" | "error";
  title: string;
  body?: string;
  action?: { label: string; onClick: () => void };
  ttl?: number;
}

interface Session {
  id: string;
  anonymous: boolean;
}


interface Store {
  ready: boolean;
  token: string;
  setToken: (t: string) => void;
  session: Session | null;
  sessionError: string;
  retrySession: () => void;
  people: Person[];
  personName: (id: string) => string;
  actingAs: string;
  setActingAs: (pid: string) => Promise<void>;
  asOf: number | null;
  setAsOf: (v: number | null) => void;
  version: number;
  bump: () => void;
  /** The latest confirm or undo, so answers asked before it can say they're out of date (M1). */
  lastWrite: { seq: number; text: string } | null;
  thread: Turn[];
  setThread: React.Dispatch<React.SetStateAction<Turn[]>>;
  noteWrite: (text: string) => void;
  pendingCount: number;
  debug: boolean;
  nextResetAt: number | null;
  // ui chrome
  sessionSheetOpen: boolean;
  setSessionSheetOpen: (v: boolean) => void;
  paletteOpen: boolean;
  setPaletteOpen: (v: boolean) => void;
  // inspector
  inspector: InspectorView[];
  inspectorPinned: boolean;
  setInspectorPinned: (v: boolean) => void;
  openInspector: (v: InspectorView, mode?: "replace" | "push") => void;
  popInspector: () => void;
  closeInspector: () => void;
  // conveniences kept for existing call sites
  openEntity: (id: string, name?: string, mode?: "replace" | "push") => void;
  openAction: (id: string, mode?: "replace" | "push") => void;
  openEvidence: (t: EvidenceTarget | null, mode?: "replace" | "push") => void;
  // toasts
  toasts: Toast[];
  toast: (t: Omit<Toast, "id">) => void;
  dismissToast: (id: number) => void;
  holdToasts: (on: boolean) => void;
  // names
  names: NameMap;
  resolveNames: (ids: string[]) => void;
}

const Ctx = createContext<Store | null>(null);

/** True inside the inspector: links there push a breadcrumb level; links elsewhere replace the panel (DESIGN.md §2.3). */
export const InInspector = createContext(false);
export function useOpenMode(): "replace" | "push" {
  return useContext(InInspector) ? "push" : "replace";
}

const ACTING_KEY = "brain.actingAs";
const PENDING_POLL_MS = 30_000;

export function StoreProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [token, setTokenState] = useState("");
  const [session, setSession] = useState<Session | null>(null);
  const [sessionError, setSessionError] = useState("");
  const [sessionTry, setSessionTry] = useState(0);
  const [people, setPeople] = useState<Person[]>([]);
  const [actingAs, setActing] = useState("");
  const [asOf, setAsOf] = useState<number | null>(null);
  const [version, setVersion] = useState(0);
  const [pendingCount, setPendingCount] = useState(0);
  const [debug, setDebug] = useState(false);
  const [nextResetAt, setNextResetAt] = useState<number | null>(null);
  const [sessionSheetOpen, setSessionSheetOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [inspector, setInspector] = useState<InspectorView[]>([]);
  const [inspectorPinned, setInspectorPinned] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [names, setNames] = useState<NameMap>({});
  const sessionRef = useRef<Session | null>(null);
  const toastId = useRef(0);
  const toastHover = useRef(false);
  const pendingNames = useRef<Set<string>>(new Set());

  const bump = useCallback(() => setVersion((v) => v + 1), []);
  const [lastWrite, setLastWrite] = useState<{ seq: number; text: string } | null>(null);
  const [thread, setThread] = useState<Turn[]>([]);
  const noteWrite = useCallback((text: string) => {
    setLastWrite((w) => ({ seq: (w?.seq || 0) + 1, text }));
    bump();
  }, [bump]);

  // first load: token, debug flag, people, health
  useEffect(() => {
    setTokenState(getToken());
    setDebug(new URLSearchParams(window.location.search).get("debug") === "1");
    get<Person[]>("/people").then(setPeople).catch(() => setPeople([]));
    get<{ next_reset_at: number | null }>("/health")
      .then((h) => setNextResetAt(h.next_reset_at ?? null))
      .catch(() => undefined);
    setReady(true);
  }, []);

  // a session per page load and token: POST /sessions, acting-as restored from localStorage
  useEffect(() => {
    if (!ready) return;
    let stored = "";
    try {
      stored = localStorage.getItem(ACTING_KEY) || "";
    } catch {
      /* ignore */
    }
    setSessionError("");
    send<{ session_id: string; anonymous: boolean; acting_as: string }>("POST", "/sessions", stored ? { acting_as: stored } : {})
      .then((s) => {
        const sess = { id: s.session_id, anonymous: s.anonymous };
        sessionRef.current = sess;
        setSession(sess);
        setActing(s.acting_as);
      })
      .catch((e) => setSessionError(String(e.message || e)));
  }, [ready, token, sessionTry]);

  const refreshPending = useCallback(() => {
    if (!actingAs) return;
    get<{ awaiting: number }>(`/people/${encodeURIComponent(actingAs)}/pending/count`)
      .then((p) => setPendingCount(p.awaiting))
      .catch(() => setPendingCount(0));
  }, [actingAs]);

  useEffect(() => {
    refreshPending();
  }, [refreshPending, version]);

  // Proposals from other people and sessions arrive without a local write, so poll for them.
  useEffect(() => {
    const t = setInterval(() => {
      if (!document.hidden) refreshPending();
    }, PENDING_POLL_MS);
    return () => clearInterval(t);
  }, [refreshPending]);

  const setToken = useCallback((t: string) => {
    saveToken(t.trim());
    setTokenState(t.trim());
    setVersion((v) => v + 1);
  }, []);

  const setActingAs = useCallback(async (pid: string) => {
    const s = sessionRef.current;
    try {
      localStorage.setItem(ACTING_KEY, pid);
    } catch {
      /* ignore */
    }
    if (s) await send("PUT", `/sessions/${encodeURIComponent(s.id)}/acting-as`, { person_id: pid });
    setActing(pid);
    setVersion((v) => v + 1);
  }, []);

  const personName = useCallback(
    (id: string) => people.find((p) => p.id === id)?.name || names[id]?.name || id.replace(/^person:/, ""),
    [people, names],
  );

  const openInspector = useCallback((v: InspectorView, mode: "replace" | "push" = "replace") => {
    setInspector((cur) => (mode === "push" && cur.length ? [...cur, v] : cur.length ? [...cur.slice(0, -1), v] : [v]));
  }, []);
  const popInspector = useCallback(() => setInspector((cur) => cur.slice(0, -1)), []);
  const closeInspector = useCallback(() => setInspector([]), []);

  const toast = useCallback((t: Omit<Toast, "id">) => {
    const id = ++toastId.current;
    setToasts((cur) => [...cur.slice(-2), { ...t, id }]);
    // m6: long enough to click (7 s, 9 s with an action), and never while the pointer is over the toasts
    const expire = () => {
      if (toastHover.current) window.setTimeout(expire, 1500);
      else setToasts((cur) => cur.filter((x) => x.id !== id));
    };
    window.setTimeout(expire, t.ttl ?? (t.action ? 9000 : 7000));
  }, []);
  const dismissToast = useCallback((id: number) => setToasts((cur) => cur.filter((x) => x.id !== id)), []);

  const resolveNames = useCallback(
    (ids: string[]) => {
      const need = ids.filter((i) => i && !names[i] && !pendingNames.current.has(i));
      if (!need.length) return;
      need.forEach((i) => pendingNames.current.add(i));
      fetchNames(need)
        .then((m) => setNames((cur) => ({ ...cur, ...m })))
        .catch(() => undefined)
        .finally(() => need.forEach((i) => pendingNames.current.delete(i)));
    },
    [names],
  );

  const value = useMemo<Store>(
    () => ({
      ready, token, setToken, session, sessionError, retrySession: () => setSessionTry((t) => t + 1),
      people, personName, actingAs, setActingAs, asOf, setAsOf, version, bump, lastWrite, noteWrite, thread, setThread, pendingCount, debug,
      nextResetAt, sessionSheetOpen, setSessionSheetOpen, paletteOpen, setPaletteOpen,
      inspector, inspectorPinned, setInspectorPinned, openInspector, popInspector, closeInspector,
      openEntity: (id, name, mode = "replace") => openInspector({ kind: "entity", id, name }, mode),
      openAction: (id, mode = "replace") => openInspector({ kind: "action", id }, mode),
      openEvidence: (t, mode = "replace") => (t ? openInspector({ kind: "evidence", target: t }, mode) : closeInspector()),
      toasts, toast, dismissToast, holdToasts: (on: boolean) => { toastHover.current = on; }, names, resolveNames,
    }),
    [ready, token, setToken, session, sessionError, people, personName, actingAs, setActingAs, asOf, version, bump,
      lastWrite, noteWrite, thread, pendingCount, debug, nextResetAt, sessionSheetOpen,
      paletteOpen, inspector, inspectorPinned, openInspector, popInspector, closeInspector, toasts, toast, dismissToast,
      names, resolveNames],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useStore(): Store {
  const s = useContext(Ctx);
  if (!s) throw new Error("useStore outside StoreProvider");
  return s;
}

/** Small fetch hook: refetches when the path or the store version changes. */
export function useApi<T>(path: string | null): { data: T | null; error: string; loading: boolean; reload: () => void } {
  const { version } = useStore();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!path) {
      setData(null);
      return;
    }
    let live = true;
    setLoading(true);
    setError("");
    get<T>(path)
      .then((d) => live && setData(d))
      .catch((e) => live && setError(String(e.message || e)))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [path, version, tick]);
  return { data, error, loading, reload: () => setTick((t) => t + 1) };
}

/** Names for a list of ids (prefixed or bare); triggers a resolve for unknown ones. */
export function useNames(ids: string[]): NameMap {
  const { names, resolveNames } = useStore();
  const key = ids.join(",");
  useEffect(() => {
    resolveNames(key ? key.split(",") : []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return names;
}
