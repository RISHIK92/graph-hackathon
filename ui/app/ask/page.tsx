"use client";

import { ArrowUp, FileText, Flag, GitBranch, ListTree, MessageSquare, Search, Square, UserRound, Zap } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { ActionChip, EligibilityBadge, FactRow, PackContext } from "@/components/Chips";
import { ConfirmControl, RefusalCard, WhoCan } from "@/components/ConfirmControl";
import { collectDisputes, DisputeLine } from "@/components/Dispute";
import { Button, Chip, Notice, Placeholder } from "@/components/ui";
import { streamTurn, type StreamEvent } from "@/lib/api";
import { fmtDate, fmtDateTime, initials, intentLabel, plural, predicateLabel } from "@/lib/format";
import { useStore } from "@/lib/store";
import type { Claim, Fact, Line, Pack, Path, Refusal, SpanItem } from "@/lib/types";

interface Turn {
  text: string;
  at: number;
  asOf: number | null;
  stages: StreamEvent[];
  answer?: { claims: Claim[]; abstained: boolean; assembled: { lines: Line[]; explanation: string }; packs: Record<string, Pack>; nearest?: (Path | null)[]; missing?: string[] };
  actions: StreamEvent[];
  turnId?: string;
  done: boolean;
  error?: string;
}

const SUGGEST_Q = ["Who owns Ledger?", "Who knows about Ledger?", "Why is Ledger on Aurora?", "What breaks if Ledger goes down, and who do I tell?", "Is anything pending for ADR-007?"];
const SUGGEST_A = ["Route RDS-42 to the owner", "Infra owns Ledger now"];

export default function AskPage() {
  return <Suspense fallback={null}><Ask /></Suspense>;
}

function Ask() {
  const s = useStore();
  const params = useSearchParams();
  const [text, setText] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<string>("");
  const logRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const q = params.get("q");
    if (q) { setText(q); taRef.current?.focus(); }
  }, [params]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const sendQ = async (q: string) => {
    if (!s.session || !q.trim() || busy) return;
    setBusy(true);
    setText("");
    const idx = turns.length;
    setTurns((t) => [...t, { text: q, at: Date.now(), asOf: s.asOf, stages: [], actions: [], done: false }]);
    const upd = (f: (t: Turn) => Turn) => setTurns((all) => all.map((t, i) => (i === idx ? f(t) : t)));
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      await streamTurn(s.session.id, { text: q, as_of: s.asOf }, (e) => {
        if (e.event === "answer") upd((t) => ({ ...t, answer: e as unknown as Turn["answer"], turnId: String(e.turn_id) }));
        else if (e.event === "action" || e.event === "refusal") upd((t) => ({ ...t, actions: [...t.actions, e] }));
        else if (e.event === "error") upd((t) => ({ ...t, error: String(e.message) }));
        else if (e.event === "done") upd((t) => ({ ...t, done: true }));
        else upd((t) => ({ ...t, stages: [...t.stages, e], turnId: t.turnId || (e.turn_id as string | undefined) }));
      }, ac.signal);
      upd((t) => ({ ...t, done: true }));
      s.bump();
    } catch (err) {
      const msg = ac.signal.aborted ? "Stopped." : String((err as Error).message || err);
      upd((t) => ({ ...t, error: msg, done: true }));
      if (!ac.signal.aborted && /429|rate limited/i.test(msg)) s.toast({ tone: "warning", title: "Rate limited", body: "Wait a moment before asking again." });
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  };

  const stop = () => abortRef.current?.abort();

  return (
    <div className="ask">
      <div className="conv" ref={logRef}>
        <div className="conv-inner">
          {!turns.length && (
            <div className="stack-6" style={{ paddingTop: 48 }}>
              <div className="stack">
                <h1 className="t-display">Ask the company brain</h1>
                <p className="text-2">Every claim is checked against the graph before it is shown. Answers cite the source span they came from.</p>
              </div>
              <div className="suggest-grid">
                <div className="stack">
                  <span className="t-label">Questions</span>
                  <div className="suggest-list">
                    {SUGGEST_Q.map((q) => <button key={q} className="suggest" onClick={() => sendQ(q)} disabled={!s.session}><Search />{q}</button>)}
                  </div>
                </div>
                <div className="stack">
                  <span className="t-label">Actions (write)</span>
                  <div className="suggest-list">
                    {SUGGEST_A.map((q) => <button key={q} className="suggest" onClick={() => sendQ(q)} disabled={!s.session}><Zap />{q}</button>)}
                  </div>
                  <div className="t-small text-3">Actions create a proposal or record a fact under the acting person{s.session?.anonymous ? ". In demo mode they are previewed, not stored." : "."}</div>
                </div>
              </div>
            </div>
          )}
          {turns.map((t, i) => (
            <TurnView key={i} t={t} idx={i} selected={selected} onSelect={setSelected} priorDisputes={disputeKeysBefore(turns, i)} />
          ))}
        </div>
      </div>
      <div className="composer-wrap">
        <form
          className="composer"
          onSubmit={(e) => { e.preventDefault(); sendQ(text); }}
        >
          <div className="box">
            <textarea
              ref={taRef}
              rows={2}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Ask a question or describe an action…"
              aria-label="Your question"
              disabled={!s.session}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendQ(text); }
                if ((e.metaKey || e.ctrlKey) && e.key === ".") { e.preventDefault(); stop(); }
              }}
            />
            {busy ? (
              <Button type="button" variant="secondary" icon={Square} onClick={stop} aria-label="Stop">Stop</Button>
            ) : (
              <Button type="submit" variant="primary" icon={ArrowUp} disabled={!s.session || !text.trim()} aria-label="Ask">Ask</Button>
            )}
          </div>
          <div className="hint">
            <span><kbd>Enter</kbd> to send</span>
            <span><kbd>Shift</kbd> + <kbd>Enter</kbd> for a new line</span>
            {busy && <span><kbd>⌘</kbd> + <kbd>.</kbd> to stop</span>}
            {!s.session && !s.sessionError && <span className="right">Connecting…</span>}
            {s.asOf && <span className="right text-warning">Asking as of {fmtDate(s.asOf)}</span>}
          </div>
        </form>
      </div>
    </div>
  );
}

// a turn

/** Dispute keys already shown by earlier turns, so a dispute notice appears once per conversation (DESIGN.md §4.2). */
function disputeKeysBefore(turns: Turn[], idx: number): Set<string> {
  const out = new Set<string>();
  for (let i = 0; i < idx; i++) {
    const packs = Object.values(turns[i].answer?.packs || {});
    const cited = new Set((turns[i].answer?.claims || []).flatMap((c) => c.assertion_ids));
    collectDisputes(packs, cited).forEach((g) => out.add(disputeKey(g)));
  }
  return out;
}
function disputeKey(g: ReturnType<typeof collectDisputes>[number]): string {
  return g.recorded?.run_id || g.recorded?.assertion_id || g.challengers[0]?.fact.assertion_id || "";
}

function TurnView({ t, idx, selected, onSelect, priorDisputes }: { t: Turn; idx: number; selected: string; onSelect: (k: string) => void; priorDisputes: Set<string> }) {
  const s = useStore();
  const packs = useMemo(() => Object.values(t.answer?.packs || {}), [t.answer]);
  const spanIndex = useMemo(() => {
    const m = new Map<string, SpanItem>();
    packs.forEach((p) => p.items.forEach((it) => it.spans.forEach((sp) => m.has(sp.span_id) || m.set(sp.span_id, sp))));
    return m;
  }, [packs]);
  const pathIndex = useMemo(() => {
    const m = new Map<string, Path>();
    packs.forEach((p) => p.items.forEach((it) => it.path && m.set(it.path.path_id, it.path)));
    return m;
  }, [packs]);
  const factIndex = useMemo(() => {
    const m = new Map<string, Fact>();
    packs.forEach((p) => p.items.forEach((it) => it.facts.forEach((f) => m.has(f.assertion_id) || m.set(f.assertion_id, f))));
    return m;
  }, [packs]);
  const claims = useMemo(() => new Map((t.answer?.claims || []).map((c) => [c.claim_id, c])), [t.answer]);
  const cited = useMemo(() => new Set((t.answer?.claims || []).flatMap((c) => c.assertion_ids)), [t.answer]);
  const disputes = useMemo(() => collectDisputes(packs, cited).filter((g) => !priorDisputes.has(disputeKey(g))), [packs, cited, priorDisputes]);
  const plan = t.stages.find((e) => e.event === "plan");
  const toolCalls = t.stages.filter((e) => e.event === "tool_call");
  const verification = t.stages.find((e) => e.event === "verification");
  const me = s.people.find((p) => p.id === s.actingAs);

  // group lines by intent (DESIGN.md §4.2)
  const lines = useMemo(() => (t.answer?.assembled.lines || []).map((l) => ({ ...l, text: l.text.replace(/\s*\(disputed\)/gi, "") })), [t.answer]);
  const groups = useMemo(() => {
    const intent = String(plan?.intent || "");
    const rows = lines.map((l) => {
      const c0 = claims.get(l.claim_id);
      const extra = (l.also || []).map((x) => claims.get(x)).filter(Boolean) as Claim[];
      const c = c0 ? { ...c0, span_ids: [...new Set([c0, ...extra].flatMap((x) => x.span_ids))] } : c0;
      const f = c?.assertion_ids?.[0] ? factIndex.get(c.assertion_ids[0]) : undefined;
      const path = c?.path_id ? pathIndex.get(c.path_id) || null : null;
      return { l, c, f, path };
    });
    const key = (r: typeof rows[number]) => {
      const p = r.f?.predicate || "";
      if (intent === "impact") return ["OWNS", "LEADS", "MEMBER_OF", "WORKS_ON"].includes(p) ? "Who to tell" : "What breaks";
      if (intent === "ownership") return p === "LEADS" ? "Lead" : p === "OWNS" ? "Owner" : predicateLabel(p);
      if (intent === "expertise") return "Who knows";
      if (intent === "decision") return "Decision trace";
      return p ? predicateLabel(p) : "Answer";
    };
    const out = new Map<string, typeof rows>();
    rows.forEach((r) => { const k = key(r); const group = out.get(k) ?? []; group.push(r); out.set(k, group); });
    return Array.from(out.entries());
  }, [lines, claims, factIndex, pathIndex, plan]);

  const lead = useMemo(() => {
    if (!lines.length) return "";
    const intent = String(plan?.intent || "");
    if (intent === "impact") {
      const breaks = groups.find(([k]) => k === "What breaks")?.[1].length || 0;
      const tell = groups.find(([k]) => k === "Who to tell")?.[1].map((r) => r.l.text).filter((x) => /leads/.test(x)).map((x) => x.replace(/ leads .*/, "")) || [];
      return `${plural(breaks, "dependency", "dependencies")} would be affected${tell.length ? `. Tell ${uniq(tell).join(", ")}` : ""}.`;
    }
    return lines.slice(0, 2).map((l) => l.text.replace(/\.$/, "")).join(". ") + ".";
  }, [lines, groups, plan]);

  return (
    <PackContext.Provider value={{ packs, fromTurn: true }}>
      <div className="turn">
        <div className="turn-user">
          <span className="avatar">{me ? initials(me.name) : "?"}</span>
          <div className="stack" style={{ gap: 2 }}>
            <div className="q">{t.text}</div>
            <div className="meta">
              <span>{me?.name || "You"}</span><span>·</span><span className="tnum">{fmtDateTime(t.at)}</span>
              {t.asOf && <Chip tone="warning">As of {fmtDate(t.asOf)}</Chip>}
            </div>
          </div>
        </div>

        <StatusLine t={t} plan={plan} toolCalls={toolCalls} verification={verification} />

        {t.error && <Notice tone={t.error === "Stopped." ? "info" : "error"} title={t.error === "Stopped." ? "Stopped" : "The turn failed"}>{t.error !== "Stopped." ? t.error : null}</Notice>}

        {t.answer && (
          <div className="answer">
            {t.answer.abstained ? (
              <div className="stack-3" style={{ padding: 16 }}>
                <Notice tone="info" title="No verified answer">{t.answer.missing?.length ? t.answer.missing.join(" ") : "Nothing in the graph supported a claim the verifier would keep."}</Notice>
                {t.answer.nearest?.filter(Boolean).length ? (
                  <div className="stack">
                    <span className="t-label">Nearest evidence</span>
                    {(t.answer.nearest ?? []).filter((p): p is Path => p !== null).map((p) => (
                      <button key={p.path_id} className="suggest" onClick={() => s.openEvidence({ tab: "path", path: p, packs, fromTurn: true, title: "Nearest path" })}>
                        <GitBranch />{p.steps.map((x) => x.node.name).join(" → ")}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : (
              <>
                {lead && <div className="answer-lead">{lead}</div>}
                {groups.map(([k, rows]) => (
                  <div key={k} className="answer-group facts-host">
                    {(groups.length > 1 || k !== "Answer") && <span className="t-label">{k}</span>}
                    <div className="facts bare">
                      {rows.map(({ l, c, f, path }) => {
                        const key = `${idx}:${l.claim_id}`;
                        const span = c?.span_ids?.[0] ? spanIndex.get(c.span_ids[0]) : undefined;
                        const fact: Fact = f || {
                          assertion_id: c?.assertion_ids?.[0] || l.claim_id, run_id: "", predicate: "", subject_id: "", object_id: "", negated: false,
                          valid_from: 0, valid_to: 0, status: l.status, authority: 0, statement: l.text, open_disputes: [],
                        };
                        const spans = (c?.span_ids || []).map((id) => spanIndex.get(id)).filter((sp): sp is SpanItem => sp !== undefined).map((sp) => ({ ...sp, cites: [...(sp.cites || []), fact.assertion_id] }));
                        return (
                          <FactRow
                            key={l.claim_id}
                            fact={{ ...fact, statement: l.text }}
                            spans={spans}
                            label={c?.label}
                            path={path}
                            showInterval={!!f}
                            selected={selected === key}
                            onSelect={() => {
                              onSelect(key);
                              if (span) s.openEvidence({ tab: "source", spanId: span.span_id, sourceId: span.source_id, quote: { start: span.quote_start, end: span.quote_end }, path, timeline: f ? timelineKeyOf(f) : null, title: span.title, packs, fromTurn: true });
                              else if (path) s.openEvidence({ tab: "path", path, packs, fromTurn: true, title: l.text });
                            }}
                            extra={(c?.action_ids || []).map((a) => <ActionChip key={a} actionId={a} label="Proposed by action" />)}
                          />
                        );
                      })}
                    </div>
                  </div>
                ))}
                {t.answer.assembled.explanation && (
                  <div className="answer-foot"><strong>Explanation (not verified):</strong> {t.answer.assembled.explanation}</div>
                )}
              </>
            )}
          </div>
        )}

        {disputes.map((g, i) => {
          const f = g.recorded || g.challengers[0]?.fact;
          const ent = f ? (["OWNS", "LEADS", "AFFECTS"].includes(f.predicate) && f.object_id ? f.object_id : f.subject_id) : "";
          return <DisputeLine key={i} g={g} onOpen={() => s.openInspector({ kind: "entity", id: ent, tab: "disputes" })} />;
        })}
        {t.actions.map((a, i) => <ActionCard key={i} e={a} />)}
      </div>
    </PackContext.Provider>
  );
}

function uniq<T>(xs: T[]): T[] { return Array.from(new Set(xs)); }
function timelineKeyOf(f: Fact) {
  const ent = ["OWNS", "LEADS", "AFFECTS"].includes(f.predicate) && f.object_id ? f.object_id : f.subject_id;
  return { entityId: ent, predicate: f.predicate };
}

const TOOL_LABEL: Record<string, string> = {
  link_entities: "Linking entities", get_owner: "Reading owners", find_experts: "Finding experts", find_paths: "Tracing dependencies",
  trace_decision: "Tracing decisions", get_history: "Reading history", query_graph: "Querying the graph", get_pending: "Checking pending items",
};

/** Replaces the raw trace: a human status while streaming, a summary line with a Trace button when done. */
function StatusLine({ t, plan, toolCalls, verification }: { t: Turn; plan?: StreamEvent; toolCalls: StreamEvent[]; verification?: StreamEvent }) {
  const s = useStore();
  if (!t.done) {
    const last = toolCalls[toolCalls.length - 1];
    const phase = verification ? "Assembling the answer…" : last ? `${TOOL_LABEL[String(last.name)] || String(last.name)}…` : plan ? "Reading the graph…" : "Planning…";
    return (
      <div className="stack" style={{ gap: 6 }}>
        <div className="statusline"><span>{phase}</span>{toolCalls.length > 0 && <><span className="sep">·</span><span>{plural(toolCalls.length, "tool")}</span></>}</div>
        <div className="progress"><i /></div>
      </div>
    );
  }
  const kept = verification ? Number(verification.kept) : undefined;
  const dropped = verification ? (verification.dropped as unknown[]).length : undefined;
  return (
    <div className="statusline">
      <span className="t-strong">{intentLabel(String(plan?.intent || ""))}</span>
      {plan?.wants_action && plan.wants_action !== "none" ? <Chip tone="accent" icon={Zap}>Action</Chip> : null}
      {toolCalls.length > 0 && <><span className="sep">·</span><span>{plural(toolCalls.length, "tool")}</span></>}
      {kept !== undefined && <><span className="sep">·</span><span>{plural(kept, "claim")} verified</span></>}
      {dropped !== undefined && dropped > 0 && <><span className="sep">·</span><span className="text-warning">{dropped} dropped</span></>}
      {t.turnId && <Button size="sm" variant="ghost" icon={ListTree} className="right" onClick={() => s.openInspector({ kind: "trace", turnId: t.turnId! })}>Trace</Button>}
    </div>
  );
}

function ActionCard({ e }: { e: StreamEvent }) {
  const s = useStore();
  if (e.event === "refusal") return <RefusalCard r={e as unknown as Refusal} />;
  const res = (e.result || {}) as Record<string, unknown>;
  const kind = String(e.kind || "");
  const title = kind === "route_to_owner" ? "Route to owner" : kind === "learn_fact" ? "Record a fact" : kind === "draft_adr_supersession" ? "Draft ADR supersession" : kind.replace(/_/g, " ") || "Action";
  if (e.status === "card") {
    return (
      <Notice tone="info" title={title} actions={<Button size="sm" variant="link" onClick={() => s.toast({ tone: "info", title: "Open Inbox to act on it" })}>Open inbox</Button>}>
        {String(e.summary)}
      </Notice>
    );
  }
  if (e.status === "needs_token") {
    return (
      <Notice tone="warning" title={`${title}: previewed only`} actions={<Button size="sm" onClick={() => s.setSessionSheetOpen(true)}>Enable writes</Button>}>
        {String(e.summary)} Writes are off in demo mode, so nothing was stored.
      </Notice>
    );
  }
  const eligible = (res.eligible || res.who_can_confirm || []) as { person_id: string; name: string; rule: string; path: string; aids?: string[] }[];
  return (
    <div className="action-card">
      <div className="head">
        <Zap />
        <span className="t-strong">{title}</span>
        {kind === "learn_fact" && <Chip tone={res.status === "disputed" ? "error" : "success"} icon={res.status === "disputed" ? Flag : undefined}>{String(res.outcome)} · {String(res.status)}</Chip>}
        {e.action_id ? <span className="right"><ActionChip actionId={String(e.action_id)} label="Action record" /></span> : null}
      </div>
      <div className="body">
        <dl className="kv">
          {e.summary ? <><dt>Summary</dt><dd>{String(e.summary)}</dd></> : null}
          {kind === "route_to_owner" && <><dt>Proposed assignee</dt><dd className="row"><UserRound className="icon-sm text-3" />{s.personName(String(res.target))}</dd></>}
          {res.eligibility ? <><dt>Eligibility</dt><dd><EligibilityBadge e={String(res.eligibility)} /></dd></> : null}
        </dl>
        {kind === "learn_fact" && res.status === "disputed" && (
          <Notice tone="warning" title="Recorded at chat rank as a challenger">It disputes the recorded fact until someone eligible confirms one side.</Notice>
        )}
        {eligible.length > 0 && <WhoCan people={eligible.map((p) => ({ ...p, path: p.path || "" }))} verb="confirm" />}
        {(kind === "route_to_owner" || kind === "draft_adr_supersession") && e.action_id ? (
          <ConfirmControl actionId={String(e.action_id)} label="Confirm proposal" what={String(e.summary || "")} />
        ) : null}
        {kind === "learn_fact" && res.status === "disputed" && res.assertion_id ? (
          <ConfirmControl assertionId={String(res.assertion_id)} label="Confirm the challenger" what={String(e.summary || "")} />
        ) : null}
        {kind === "learn_fact" && res.status !== "disputed" && !res.assertion_id && <Placeholder><FileText className="icon-sm" /> Nothing new was recorded.</Placeholder>}
        {!e.action_id && !eligible.length && kind !== "learn_fact" && <Placeholder><MessageSquare className="icon-sm" />{String(e.summary || "Done.")}</Placeholder>}
      </div>
    </div>
  );
}
