"use client";

import { get } from "@/lib/api";
import { useStore } from "@/lib/store";
import { useEffect, useState } from "react";
import type { Trace } from "@/lib/types";
import { Chip, Details, ErrorState, Skeleton } from "./ui";

/** "How I answered": each step as a sentence, the query behind it under "Show query", the verifier; raw
 * tool names, arguments and packs only with ?debug=1 (M17). */
export function TraceView({ turnId }: { turnId: string }) {
  const { debug } = useStore();
  const [trace, setTrace] = useState<Trace | null>(null);
  const [err, setErr] = useState("");
  const [tick, setTick] = useState(0);
  useEffect(() => {
    setErr("");
    get<Trace>(`/turns/${encodeURIComponent(turnId)}/trace`).then(setTrace).catch((e) => setErr(String(e.message || e)));
  }, [turnId, tick]);
  if (err) return <div style={{ padding: 16 }}><ErrorState message={err} onRetry={() => setTick((t) => t + 1)} /></div>;
  if (!trace) return <div style={{ padding: 16 }} className="stack-3"><Skeleton w="40%" /><Skeleton h={80} /><Skeleton h={80} /></div>;
  const v = trace.verification;
  return (
    <div className="inspector-body">
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
                      <span>·</span>
                      <span className="tnum">{q.ms.toFixed ? q.ms.toFixed(1) : q.ms} ms</span>
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
      {v && (
        <section className="inspector-section">
          <span className="t-label">Checks</span>
          <div className="row-wrap t-small">
            <Chip tone="success">{v.kept} {v.kept === 1 ? "claim" : "claims"} checked against the graph</Chip>
            {v.dropped.length > 0 && <Chip tone="warning">{v.dropped.length} dropped</Chip>}
            {v.rewritten?.length ? <Chip tone="neutral">Rewritten {v.rewritten.length}</Chip> : null}
          </div>
          {debug && v.dropped.length > 0 && <Details summary="Dropped claims"><pre className="code">{JSON.stringify(v.dropped, null, 1)}</pre></Details>}
        </section>
      )}
      {debug && trace.packs && <Details summary="Raw packs (debug)"><pre className="debug">{JSON.stringify(trace.packs, null, 1)}</pre></Details>}
    </div>
  );
}
