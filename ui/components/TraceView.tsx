"use client";

import { get } from "@/lib/api";
import { Check } from "lucide-react";
import { useStore } from "@/lib/store";
import { useEffect, useState } from "react";
import { fmtDate } from "@/lib/format";
import { KIND_LABEL } from "@/lib/labels";
import type { Path, SpanItem, Trace } from "@/lib/types";
import { EvidenceText } from "./EvidenceText";
import { SourceLinks } from "./SourceLinks";
import { Chip, Details, ErrorState, Skeleton } from "./ui";

const ROLE: Record<string, string> = { planner: "Understood the question", drafter: "Wrote the answer", checker: "Checked the answer",
  escalation: "Rewrote after a failed check" };
const TABS = [["path", "Path"], ["sources", "Sources"], ["cypher", "Cypher"], ["checks", "Checks"]] as const;

export function nodeTone(labels: string[]): string {
  return labels.some((l) => l === "System" || l === "Project") ? "sys" : labels.some((l) => l === "Team" || l === "Person") ? "per" : "rec";
}

/** "How I answered", the proof rail (item 19 design brief step 3): the answer's path with each edge's source,
 * the cited sources, every query with its Cypher and time, and the checks and models. Raw tool names,
 * arguments and packs only with ?debug=1 (M17). */
export function TraceView({ turnId, path, spans, tab: first }: { turnId: string; path?: Path | null; spans?: SpanItem[]; tab?: string }) {
  const { debug, openEvidence } = useStore();
  const [trace, setTrace] = useState<Trace | null>(null);
  const [err, setErr] = useState("");
  const [tick, setTick] = useState(0);
  const [tab, setTab] = useState(first || (path ? "path" : "cypher"));
  useEffect(() => { setTab(first || (path ? "path" : "cypher")); }, [turnId, first, path]);
  useEffect(() => {
    setErr("");
    get<Trace>(`/turns/${encodeURIComponent(turnId)}/trace`).then(setTrace).catch((e) => setErr(String(e.message || e)));
  }, [turnId, tick]);
  if (err) return <div style={{ padding: 16 }}><ErrorState message={err} onRetry={() => setTick((t) => t + 1)} /></div>;
  if (!trace) return <div style={{ padding: 16 }} className="stack-3"><Skeleton w="40%" /><Skeleton h={80} /><Skeleton h={80} /></div>;
  const v = trace.verification;
  const queries = trace.tool_calls.flatMap((c) => c.queries);
  const cited = spans || [];
  const openSpan = (sp: SpanItem) => openEvidence({ tab: "source", spanId: sp.span_id, sourceId: sp.source_id, quote: { start: sp.quote_start, end: sp.quote_end }, title: sp.title, path: path || null }, "push");
  return (
    <div className="proof">
      <div className="proof-tabs" role="tablist" aria-label="Proof views">
        {TABS.map(([id, label]) => (
          <button key={id} type="button" role="tab" data-testid={`proof-tab-${id}`} aria-selected={tab === id} className={`proof-tab ${tab === id ? "on" : ""}`} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>
      <div className="inspector-body proof-pane" key={tab}>
        {tab === "path" && (path && path.steps.length ? (
          <ol className="proof-path">
            {path.steps.map((st, i) => {
              const e = st.edge;
              const rel = e ? `${e.dir === "backward" ? "←" : "→"} ${e.type.replace(/_/g, " ")}${e.valid_from ? ` · since ${fmtDate(e.valid_from)}` : ""}` : "start";
              return (
                <li key={`${st.node.id}-${i}`} className={`proof-step ${nodeTone(st.node.labels)}`}>
                  <span className="dot" aria-hidden />
                  <div className="stack" style={{ gap: 4 }}>
                    <span className="name">{st.node.name}</span>
                    <span className="rel">{rel}</span>
                    {(st.evidence?.length ? st.evidence : cited.filter((sp) => !!e?.aid && (sp.cites || []).includes(e.aid))).slice(0, 2).map((sp) => (
                      <button key={sp.span_id} type="button" className="proof-src" data-testid="proof-source" onClick={() => openSpan(sp)}>
                        Source: {sp.title || KIND_LABEL[sp.kind || ""] || "document"}{sp.ts ? ` · ${fmtDate(sp.ts)}` : ""}
                      </button>
                    ))}
                  </div>
                </li>
              );
            })}
          </ol>
        ) : <span className="t-small text-2">This answer isn&apos;t a single path through the graph. Its facts and their sources are under Sources.</span>)}

        {tab === "sources" && (cited.length ? (
          <div className="stack-3">
            {cited.map((sp, i) => (
              <div key={sp.span_id} className="proof-quote" data-testid={`proof-quote-${i + 1}`}>
                <button type="button" className="stack" style={{ gap: 6, textAlign: "left" }} onClick={() => openSpan(sp)}>
                  <span className="n">[{i + 1}]</span>
                  <span className="q"><EvidenceText text={sp.text} kind={sp.kind}>“{sp.text.trim()}”</EvidenceText></span>
                  <span className="meta">{KIND_LABEL[sp.kind || ""] || sp.kind || "Source"}{sp.title ? ` · ${sp.title}` : ""}{sp.ts ? ` · ${fmtDate(sp.ts)}` : ""}{sp.live ? "" : " · not in the latest revision"}</span>
                </button>
                <SourceLinks sourceId={sp.source_id} spanId={sp.span_id} url={sp.url} system={sp.system} demo={sp.demo} />
              </div>
            ))}
          </div>
        ) : <span className="t-small text-2">No source is cited in the answer&apos;s first sentence.</span>)}

        {tab === "cypher" && (
          <>
            <div className="proof-meta">{queries.length} {queries.length === 1 ? "query" : "queries"}</div>
            <div className="t-small text-2">What I looked up, in order. Each step shows the graph query it ran; a generated query is marked unverified.</div>
            {trace.tool_calls.map((c, i) => (
              <section key={i} className="inspector-section">
                <div className="row-wrap">
                  <span className="count-badge">{i + 1}</span>
                  <span className="t-strong">{c.sentence || c.name}</span>
                  {c.queries.some((q) => q.unverified) && <Chip tone="warning">Generated, unverified</Chip>}
                </div>
                {debug && <code className="t-small text-3" style={{ marginLeft: 26 }}>{c.name} {JSON.stringify(c.args)}</code>}
                {c.queries.length > 0 && (
                  <div style={{ marginLeft: 26 }}>
                    <Details summary={c.queries.length > 1 ? `Show queries (${c.queries.length})` : "Show query"}>
                      {c.queries.map((q, j) => (
                        <div key={j} className="stack">
                          <div className="row-wrap t-small text-2">
                            <Chip tone="neutral">{q.template}</Chip>
                            <span className="tnum">{q.rows} {q.rows === 1 ? "row" : "rows"}</span>
                          </div>
                          <pre className="code">{q.cypher}</pre>
                          {debug && <div className="t-small text-3"><code>{JSON.stringify(q.params)}</code></div>}
                        </div>
                      ))}
                    </Details>
                  </div>
                )}
              </section>
            ))}
            <span className="t-small text-3">Queries are fixed templates, not generated Cypher, unless marked unverified.</span>
          </>
        )}

        {tab === "checks" && (
          <>
            {v && (
              <section className="inspector-section">
                <span className="t-label">Checks</span>
                <div className="row-wrap t-small">
                  <Chip tone="success">{v.kept} {v.kept === 1 ? "claim" : "claims"} checked against the graph</Chip>
                  {v.dropped.length > 0 && <Chip tone="warning">{v.dropped.length} dropped</Chip>}
                  {v.rewritten?.length ? <Chip tone="neutral">Rewritten {v.rewritten.length}</Chip> : null}
                </div>
                {v.checks && Object.keys(v.checks).length > 0 && (
                  <div className="stack t-small">
                    {Object.entries(v.checks).map(([name, n]) => (
                      <span key={name} className="row" style={{ gap: 6 }}><Check className="icon-sm text-success" />{name}{n > 1 ? ` (${n} claims)` : ""}</span>
                    ))}
                  </div>
                )}
                {debug && v.dropped.length > 0 && <Details summary="Dropped claims"><pre className="code">{JSON.stringify(v.dropped, null, 1)}</pre></Details>}
              </section>
            )}
            <section className="inspector-section">
              <span className="t-label">Models</span>
              {trace.models?.length ? (
                <div className="stack t-small">
                  {trace.models.map((m, i) => (
                    <span key={i} className="row-wrap" style={{ gap: 6 }}>
                      <Chip tone="neutral">{ROLE[m.role] || m.role}</Chip><code>{m.model || "unknown"}</code>
                      {m.result && <span className="text-2">{m.result === "pass" ? "passed" : "failed"}</span>}
                    </span>
                  ))}
                </div>
              ) : <span className="t-small text-2">No model was used: the answer comes straight from the graph. This happens when models are off for this demo or today&apos;s model allowance is used up; the answer is the same verified draft either way.</span>}
              {trace.check && <span className="t-small text-2">Answer check: {trace.check.result}{trace.check.reason ? ` (${trace.check.reason})` : ""}.</span>}
            </section>
          </>
        )}
        {debug && trace.packs && <Details summary="Raw packs (debug)"><pre className="debug">{JSON.stringify(trace.packs, null, 1)}</pre></Details>}
      </div>
    </div>
  );
}
