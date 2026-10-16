"use client";

import { FileText, Flag, GitBranch, Info, ListTree, MessageSquare, Square, UserRound, Zap } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { ActionChip, EligibilityBadge, FactRow, PackContext } from "@/components/Chips";
import { ConfirmControl, RefusalCard, WhoCan } from "@/components/ConfirmControl";
import { collectDisputes, DisputeLine } from "@/components/Dispute";
import { nodeTone } from "@/components/TraceView";
import { Button, Chip, Notice, Placeholder } from "@/components/ui";
import { qs, streamTurn, type StreamEvent } from "@/lib/api";
import { fmtDate, fmtDateTime, plural } from "@/lib/format";
import { actionKindLabel, displayText, intentLabel, predicateLabel } from "@/lib/labels";
import { type Turn, useApi, useStore } from "@/lib/store";
import type { Claim, Directory, Fact, Pack, Path, Refusal, SpanItem } from "@/lib/types";


// The empty state (design brief addendum, AskStart board): six questions on keys 1-6, each saying what it returns
const SUGGEST_Q = [
  { kind: "OWNERSHIP", tone: "per", text: "Who owns Reporting?", returns: "a cited path · team and lead" },
  { kind: "THEN AND NOW", tone: "then", text: "Who owned Ledger before the reorg?", returns: "the earlier owner, dated and cited" },
  { kind: "BLAST RADIUS", tone: "sys", text: "What breaks if Aurora goes down, and who do I tell?", returns: "affected systems · who to tell" },
  { kind: "DECISION", tone: "rec", text: "Why was ADR-007 accepted?", returns: "the decision, its reasons, its sources" },
  { kind: "EXPERTS", tone: "per", text: "Who knows about Reporting?", returns: "people ranked by evidence" },
  { kind: "PENDING", tone: "now", text: "Is anything pending for ADR-007?", returns: "open proposals and who can confirm" },
];
const SUGGEST_A = [
  { kind: "ROUTE TO OWNER", text: "Route RDS-42 to the owner" },
  { kind: "RECORD A FACT", text: "Infra owns Ledger now" },
  { kind: "DRAFT ADR", text: "Draft an ADR superseding ADR-007: move Ledger to CockroachDB for multi-region writes" },
  { kind: "FLAG STALE DOCS", text: "Flag stale docs about Ledger" },
];

export default function AskPage() {
  return <Suspense fallback={null}><Ask /></Suspense>;
}

function Ask() {
  const s = useStore();
  const params = useSearchParams();
  const [text, setText] = useState("");
  // M3: the thread lives in the store, so it survives a visit to another page while the tab is open
  const { thread: turns, setThread: setTurns } = s;
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<string>("");
  const logRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const queued = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const q = params.get("q");
    if (q && params.get("send") === "1") queued.current = q;   // Overview examples and "Ask about it" send at once (M9)
    else if (q) { setText(q); taRef.current?.focus(); }
  }, [params]);

  // m22: a new question scrolls to its own header, not to the bottom of a long answer
  useEffect(() => {
    const last = logRef.current?.querySelectorAll(".turn");
    last?.[last.length - 1]?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [turns.length]);

  // A question sent while the session is still connecting waits for it instead of being dropped (M22)
  useEffect(() => {
    if (s.session && queued.current && !busy) {
      const q = queued.current;
      queued.current = null;
      void sendQ(q);
    }
  });

  const sendQ = async (q: string, then?: { asOf: number; of: number }) => {
    if (!q.trim() || busy) return;
    if (!s.session) { queued.current = q; setText(""); return; }
    setBusy(true);
    setText("");
    const idx = turns.length;
    const asOf = then ? then.asOf : s.asOf;
    setTurns((t) => [...t, { text: q, at: Date.now(), asOf, stages: [], actions: [], actor: s.actingAs, writeSeq: s.lastWrite?.seq || 0, done: false, thenOf: then?.of }]);
    const upd = (f: (t: Turn) => Turn) => setTurns((all) => all.map((t, i) => (i === idx ? f(t) : t)));
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      await streamTurn(s.session.id, { text: q, as_of: asOf }, (e) => {
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
  const fill = (q: string, caret = q.length) => { setText(q); requestAnimationFrame(() => { taRef.current?.focus(); taRef.current?.setSelectionRange(caret, caret); }); };

  // 1-6 ask the empty state's questions, unless the person is typing
  const empty = !turns.length;
  useEffect(() => {
    if (!empty) return;
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (e.metaKey || e.ctrlKey || e.altKey || ["INPUT", "TEXTAREA", "SELECT"].includes(el?.tagName) || el?.isContentEditable) return;
      const n = Number(e.key);
      if (n >= 1 && n <= SUGGEST_Q.length) { e.preventDefault(); void sendQ(SUGGEST_Q[n - 1].text); }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  const composer = (
    <form className={`composer ${empty ? "centred" : ""}`} onSubmit={(e) => { e.preventDefault(); sendQ(text); }}>
      <label htmlFor="ask-box" className="sr-only">Ask a question or describe an action</label>
      <textarea
        id="ask-box"
        ref={taRef}
        rows={2}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={empty ? "Ask a question, or tell Nodus something new…" : "Ask a follow-up, or tell Nodus something new…"}
        disabled={!s.session}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendQ(text); }
          if ((e.metaKey || e.ctrlKey) && e.key === ".") { e.preventDefault(); stop(); }
        }}
      />
      <div className="composer-bar">
        <button type="button" className={`composer-chip ${s.asOf ? "then" : ""}`} onClick={() => s.setSessionSheetOpen(true)} title="Change the date in Session settings">
          {s.asOf ? `As of ${fmtDate(s.asOf)}` : "As of today"}
        </button>
        <button type="button" className="composer-chip" onClick={() => s.setSessionSheetOpen(true)} title="Demo identity, not authentication">
          Acting as <span className="who">{s.personName(s.actingAs) || "…"}</span>
        </button>
        <span className="hint"><kbd>Enter</kbd> send · <kbd>Shift</kbd> <kbd>Enter</kbd> new line{busy ? <> · <kbd>⌘</kbd> <kbd>.</kbd> stop</> : null}</span>
        <span className="grow" />
        {busy ? (
          <Button type="button" variant="secondary" icon={Square} onClick={stop} aria-label="Stop">Stop</Button>
        ) : (
          <button type="submit" className="composer-send" disabled={!s.session || !text.trim()}>Ask <span aria-hidden>↵</span></button>
        )}
      </div>
    </form>
  );

  if (empty) return <AskStart composer={composer} onAsk={(q) => sendQ(q)} onFill={fill} />;
  return (
    <div className="ask">
      <div className="conv" ref={logRef}>
        <div className="conv-inner">
          {turns.map((t, i) => (
            <TurnView key={i} t={t} idx={i} selected={selected} onSelect={setSelected} priorDisputes={disputeKeysBefore(turns, i)} onAskAgain={sendQ}
              nowTurn={t.thenOf !== undefined ? turns[t.thenOf] : undefined}
              onThen={(asOf) => sendQ(t.text, { asOf, of: i })} onFill={fill} />
          ))}
        </div>
      </div>
      <div className="composer-wrap">{composer}</div>
    </div>
  );
}

function AskStart({ composer, onAsk, onFill }: { composer: React.ReactNode; onAsk: (q: string) => void; onFill: (q: string) => void }) {
  const s = useStore();
  const [tab, setTab] = useState<"ask" | "do">("ask");
  const dir = useApi<Directory>(`/directory${qs({ as_of: s.asOf })}`);
  const d = dir.data;
  const ro = !!s.session?.anonymous;
  return (
    <div className="ask-start">
      <div className="ask-start-inner">
        <div className="stack nx-rise" style={{ gap: 10 }}>
          <span className="eyebrow">ASK THE DEMO COMPANY</span>
          <h1 className="ask-start-title">What do you want to know?</h1>
          <p className="text-2" style={{ margin: 0, fontSize: 16 }}>Ask in plain words. Every answer is a path through the graph, with the sentence it came from.</p>
        </div>
        <div className="nx-rise nx-d1">{composer}</div>
        <div className="stack-3 nx-rise nx-d2">
          <div className="row-wrap" style={{ justifyContent: "space-between" }}>
            <div className="seg" role="tablist" aria-label="Suggestions">
              <button type="button" role="tab" aria-selected={tab === "ask"} className={tab === "ask" ? "on" : ""} onClick={() => setTab("ask")}>Ask a question <span className="n">{SUGGEST_Q.length}</span></button>
              <button type="button" role="tab" aria-selected={tab === "do"} className={tab === "do" ? "on" : ""} onClick={() => setTab("do")}>Do something <span className="n">{SUGGEST_A.length}</span></button>
            </div>
            <span className="t-small text-3">{tab === "ask" ? "Click to ask, or press 1–6" : ro ? "Changes the graph · needs a token on this demo" : "Changes the graph · recorded as the person you're acting as"}</span>
          </div>
          {tab === "ask" ? (
            <div className="start-grid">
              {SUGGEST_Q.map((q, i) => (
                <button key={q.text} type="button" className="start-card" onClick={() => onAsk(q.text)} disabled={!s.session}>
                  <span className="row" style={{ justifyContent: "space-between" }}>
                    <span className={`kind ${q.tone}`}><i />{q.kind}</span>
                    <kbd>{i + 1}</kbd>
                  </span>
                  <span className="text">{q.text}</span>
                  <span className="returns">returns: {q.returns}</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="stack" style={{ gap: 0 }}>
              {SUGGEST_A.map((a) => (
                <button key={a.text} type="button" className="start-row" onClick={() => onFill(a.text)}>
                  <span className="kind">{a.kind}</span>
                  <span className="text">{a.text}</span>
                  {ro && <span className="token">Needs a token</span>}
                </button>
              ))}
              <p className="start-note">Picking one fills the box so you can edit it first. Writes are recorded as the person you&apos;re acting as, the graph decides who may confirm them, and every one can be undone.</p>
            </div>
          )}
        </div>
        <div className="start-foot nx-rise nx-d3">
          <span className="eyebrow">THE GRAPH KNOWS</span>
          <span><b>{d?.teams.length ?? "–"}</b> teams</span>
          <span><b>{d?.systems.length ?? "–"}</b> systems</span>
          <span><b>{d?.decisions.length ?? "–"}</b> decisions</span>
          <span><b className="disp">{d ? d.systems.filter((x) => x.disputed).length : "–"}</b> open disputes</span>
          <span className="grow" />
          <Link href="/directory" className="home-link">Browse everything</Link>
        </div>
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

function TurnView({ t, idx, selected, onSelect, priorDisputes, onAskAgain, nowTurn, onThen, onFill }: {
  t: Turn; idx: number; selected: string; onSelect: (k: string) => void; priorDisputes: Set<string>; onAskAgain: (q: string) => void;
  nowTurn?: Turn; onThen: (asOf: number) => void; onFill: (q: string, caret?: number) => void;
}) {
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
  // M14: the longest cited path of an ownership, impact or expertise answer, one click from the answer
  const connectPath = ["ownership", "impact", "expertise"].includes(String(plan?.intent || ""))
    ? Array.from(claims.values()).map((c) => (c.path_id ? pathIndex.get(c.path_id) : undefined))
      .filter((p): p is Path => !!p && p.steps.length > 1).sort((a, b) => b.steps.length - a.steps.length)[0]
    : undefined;
  const toolCalls = t.stages.filter((e) => e.event === "tool_call");
  const verification = t.stages.find((e) => e.event === "verification");
  const me = s.people.find((p) => p.id === t.actor);

  // group lines by intent (DESIGN.md §4.2)
  // The chip carries the status; in an As-of turn it also tells "Current then" from "Historical" (M11).
  const lines = useMemo(() => (t.answer?.assembled.lines || []).map((l) => {
    const text = l.text.replace(/\s*\(disputed\)/gi, "");
    return { ...l, text: t.asOf ? text.replace(/\s*\(historical\)/gi, "") : text };
  }), [t.answer, t.asOf]);
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
      const d = r.c?.decision;
      if (d) return `Why ${d.name}${d.status ? ` (${d.status})` : ""}`;
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

  const answerLead = t.answer?.assembled.lead;
  const leadSpans = useMemo(() => [...new Set((t.answer?.assembled.lead_claims || []).flatMap((id) => claims.get(id)?.span_ids || []))]
    .map((id) => spanIndex.get(id)).filter((sp): sp is SpanItem => sp !== undefined).slice(0, 3), [t.answer, claims, spanIndex]);
  const leadFact = useMemo(() => (t.answer?.assembled.lead_claims || []).map((id) => claims.get(id)?.assertion_ids?.[0])
    .map((a) => (a ? factIndex.get(a) : undefined)).find((f) => !!f), [t.answer, claims, factIndex]);
  // entity names in the answer, coloured by kind: systems and projects teal, teams and people violet, records grey
  const entities = useMemo(() => {
    const m = new Map<string, string>();
    packs.forEach((p) => p.items.forEach((it) => it.path?.steps.forEach((st) => m.set(st.node.name, nodeTone(st.node.labels)))));
    s.people.forEach((p) => m.has(p.name) || m.set(p.name, "per"));
    return m;
  }, [packs, s.people]);
  const proofPath = connectPath || (t.answer?.assembled.lead_claims || []).map((id) => claims.get(id)?.path_id).map((pid) => (pid ? pathIndex.get(pid) : undefined)).find((p) => !!p && p.steps.length > 1);
  const allSpans = useMemo(() => [...new Set((t.answer?.claims || []).flatMap((c) => c.span_ids))], [t.answer]);
  const openProof = (tab?: string) => t.turnId && s.openInspector({ kind: "trace", turnId: t.turnId, path: proofPath || null, spans: leadSpans.length ? leadSpans : allSpans.map((id) => spanIndex.get(id)).filter((sp): sp is SpanItem => !!sp).slice(0, 6), tab });
  const pastAt = leadFact && leadFact.valid_from > 86_400_000 && !t.asOf && t.thenOf === undefined ? leadFact.valid_from - 86_400_000 : null;
  const disputable = leadFact && /^(.+?) (owns|leads) (.+)$/.exec(leadFact.statement);
  const limited = !!t.error && /429|rate limited/i.test(t.error);
  const lead = useMemo(() => {
    if (answerLead) return answerLead;   // a lead that states every claim leaves no lines (item 20 contract)
    if (!lines.length) return "";
    const intent = String(plan?.intent || "");
    if (intent === "impact") {
      const breaks = groups.find(([k]) => k === "What breaks")?.[1].length || 0;
      const tell = groups.find(([k]) => k === "Who to tell")?.[1].map((r) => r.l.text).filter((x) => /leads/.test(x)).map((x) => x.replace(/ leads .*/, "")) || [];
      return `${plural(breaks, "dependency", "dependencies")} would be affected${tell.length ? `. Tell ${uniq(tell).join(", ")}` : ""}.`;
    }
    return lines.slice(0, 2).map((l) => l.text.replace(/\.$/, "")).join(". ") + ".";
  }, [lines, groups, plan, answerLead]);

  return (
    <PackContext.Provider value={{ packs, fromTurn: true }}>
      <div className="turn">
        <div className="turn-user">
          <div className="q">{t.text}</div>
          <div className="meta">
            <span>{me?.name || "You"}</span><span>·</span><span className="tnum">{fmtDateTime(t.at)}</span>
            {t.asOf && <Chip tone="warning">As of {fmtDate(t.asOf)}</Chip>}
          </div>
        </div>

        {t.answer?.help ? <span className="nodus-tag">Nodus</span> : <StatusLine t={t} plan={plan} toolCalls={toolCalls} verification={verification} onProof={() => openProof("cypher")} />}

        {limited ? (
          <Notice tone="info" title="That's this hour's questions">This public demo limits how many questions each visitor can ask per hour. Wait a few minutes and ask again; nothing you asked is lost.</Notice>
        ) : t.error && <Notice tone={t.error === "Stopped." ? "info" : "error"} title={t.error === "Stopped." ? "Stopped" : "The turn failed"}>{t.error !== "Stopped." ? t.error : null}</Notice>}

        {t.answer && t.done && s.lastWrite && s.lastWrite.seq > t.writeSeq && (
          <Notice tone="info" title="Updated since this answer" actions={<Button size="sm" onClick={() => onAskAgain(t.text)}>Ask again</Button>}>
            {s.lastWrite.text}.
          </Notice>
        )}
        {t.answer && (
          <div className="answer">
            {t.answer.abstained ? (
              <div className="stack-3">
                {t.answer.help ? (
                  <div className="stack-3">
                    <div className="stack reply-text">{(t.answer.missing || []).map((m) => <p key={m}>{m}</p>)}</div>
                    <div className="row-wrap">
                      {SUGGEST_Q.map((q) => <button key={q.text} type="button" className="composer-chip" onClick={() => onFill(q.text)}>{q.text}</button>)}
                    </div>
                  </div>
                ) : (
                  <Notice tone="info" title="No verified answer">{t.answer.missing?.length ? t.answer.missing.join(" ") : "Nothing in the graph supported a claim the verifier would keep."}</Notice>
                )}
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
                {t.thenOf !== undefined && nowTurn?.answer?.assembled.lead && t.asOf ? (
                  <div className="thennow">
                    <div className="then"><span className="tag">THEN · AS OF {fmtDate(t.asOf).toUpperCase()}</span><span>{displayText(lead || "Nothing in the graph for that date.")}</span></div>
                    <div className="now"><span className="tag">NOW</span><span>{displayText(nowTurn.answer.assembled.lead)}</span></div>
                  </div>
                ) : lead && (
                  <p className="answer-lead">
                    <Entities text={displayText(lead)} names={entities} />
                    {leadSpans.map((sp, i) => (
                      <button key={sp.span_id} type="button" className="cite" title={`${sp.title || "Source"}. Open the source.`}
                        onClick={() => s.openEvidence({ tab: "source", spanId: sp.span_id, sourceId: sp.source_id, quote: { start: sp.quote_start, end: sp.quote_end }, title: sp.title, packs, fromTurn: true })}>[{i + 1}]</button>
                    ))}
                  </p>
                )}
                {t.done && t.turnId && (
                  <button type="button" className="evidence-line" onClick={() => openProof()} aria-label="Show proof for this answer">
                    {proofPath ? proofPath.steps.map((st, i) => (
                      <span key={`${st.node.id}-${i}`} className="row" style={{ gap: 8 }}>
                        {st.edge && <span className="rel">{st.edge.dir === "backward" ? "←" : "→"} {st.edge.type.replace(/_/g, " ")} {st.edge.dir === "backward" ? "←" : "→"}</span>}
                        <span className={`e-${nodeTone(st.node.labels)}`}>{st.node.name}</span>
                      </span>
                    )) : <span>How I answered</span>}
                    <span className="meta">
                      {proofPath ? `${plural(proofPath.steps.length - 1, "hop")} · ` : ""}{plural(allSpans.length, "source")}
                    </span>
                  </button>
                )}
                {t.done && (
                  <div className="row-wrap">
                    {pastAt && <Button size="sm" onClick={() => onThen(pastAt)}>See it as of {fmtDate(pastAt)}</Button>}
                    {disputable && (
                      <Button size="sm" disabled={!!s.session?.anonymous} title={s.session?.anonymous ? "Writes need a token" : "Write who it really is, then send"}
                        onClick={() => onFill(` ${disputable[2]} ${disputable[3]} now`, 0)}>Dispute this</Button>
                    )}
                    <Button size="sm" onClick={() => { void navigator.clipboard?.writeText([lead, ...lines.map((l) => l.text)].filter(Boolean).join("\n")); s.toast({ tone: "info", title: "Copied" }); }}>Copy</Button>
                  </div>
                )}
                {t.answer.assembled.status && (
                  <div className="row t-small" style={{ gap: 6 }}>
                    <Chip tone={t.answer.assembled.status.kind === "disputed" ? "warning" : "neutral"}>{t.answer.assembled.status.kind === "disputed" ? "Disputed" : t.answer.assembled.status.kind === "pending" ? "Pending" : "As of"}</Chip>
                    <span className="text-2">{displayText(t.answer.assembled.status.text.replace(/^(Disputed|Pending): /, ""))}</span>
                  </div>
                )}
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
                            asOf={t.asOf}
                            showInterval={!!f}
                            selected={selected === key}
                            onSelect={() => {
                              onSelect(key);
                              if (span) s.openEvidence({ tab: "source", spanId: span.span_id, sourceId: span.source_id, quote: { start: span.quote_start, end: span.quote_end }, path, timeline: f ? timelineKeyOf(f) : null, title: span.title, packs, fromTurn: true });
                              else if (path) s.openEvidence({ tab: "path", path, packs, fromTurn: true, title: l.text });
                            }}
                            extra={<>
                              {(c?.action_ids || []).map((a) => <ActionChip key={a} actionId={a} label="Proposed by action" />)}
                              {c?.expert && <span title={`Ranking score ${c.expert.score} (relative strength: ${c.expert.strength})`}><Info className="icon-sm text-3" /></span>}
                            </>}
                          />
                        );
                      })}
                    </div>
                  </div>
                ))}
                {(t.answer.assembled.next || !!t.answer.assembled.more) && (
                  <div className="t-small text-2">
                    {t.answer.assembled.next && <><strong>Next:</strong> {displayText(t.answer.assembled.next)} </>}
                    {!!t.answer.assembled.more && <span className="text-3">{plural(t.answer.assembled.more, "more supporting fact")} in the evidence.</span>}
                  </div>
                )}
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

/** The answer's text with each known entity name as a chip coloured by its kind. */
function Entities({ text, names }: { text: string; names: Map<string, string> }) {
  const keys = [...names.keys()].filter((k) => k.length > 2).sort((a, b) => b.length - a.length);
  if (!keys.length) return <>{text}</>;
  const re = new RegExp(`\\b(${keys.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})\\b`, "g");
  return <>{text.split(re).map((part, i) => (i % 2 ? <span key={i} className={`ent ${names.get(part)}`}>{part}</span> : part))}</>;
}
function timelineKeyOf(f: Fact) {
  const ent = ["OWNS", "LEADS", "AFFECTS"].includes(f.predicate) && f.object_id ? f.object_id : f.subject_id;
  return { entityId: ent, predicate: f.predicate };
}

const TOOL_LABEL: Record<string, string> = {
  link_entities: "Linking entities", get_owner: "Reading owners", find_experts: "Finding experts", find_paths: "Tracing dependencies",
  trace_decision: "Tracing decisions", get_history: "Reading history", query_graph: "Querying the graph", get_pending: "Checking pending items",
};

/** Replaces the raw trace: a human status while streaming, a summary line with a Trace button when done. */
function StatusLine({ t, plan, toolCalls, verification, onProof }: { t: Turn; plan?: StreamEvent; toolCalls: StreamEvent[]; verification?: StreamEvent; onProof: () => void }) {
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
  const sources = new Set((t.answer?.claims || []).flatMap((c) => c.span_ids)).size;
  return (
    <div className="statusline">
      <span className="t-strong">{intentLabel(String(plan?.intent || ""))}</span>
      {plan?.wants_action && plan.wants_action !== "none" ? <Chip tone="accent" icon={Zap}>{actionKindLabel(String(plan.wants_action))}</Chip> : null}
      {kept !== undefined && <><span className="sep">·</span><span>checked {plural(kept, "fact")} against {plural(sources, "source")}</span></>}
      {dropped !== undefined && dropped > 0 && <><span className="sep">·</span><span className="text-warning">{dropped} dropped</span></>}
      {t.turnId && <Button size="sm" variant="ghost" icon={ListTree} className="right" onClick={onProof}>How I answered</Button>}
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
  // B1: the draft's proposed facts (status, replacement, affects), from the action's own pack
  const proposals = new Set((res.proposals || []) as string[]);
  const drafted = ((e.pack as Pack | undefined)?.items || []).flatMap((it) => it.facts).filter((f) => proposals.has(f.assertion_id));
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
          <Notice tone="warning" title="Noted from chat">The recorded fact stays current until someone who can settle it confirms the change.</Notice>
        )}
        {kind === "draft_adr_supersession" && drafted.length > 0 && (
          <div className="facts facts-host">{drafted.map((f) => <FactRow key={f.assertion_id} fact={f} />)}</div>
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
