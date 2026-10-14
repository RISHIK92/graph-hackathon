"use client";

import { get } from "@/lib/api";
import { useEffect, useState } from "react";
import type { Trace } from "@/lib/types";
import { Chip, Details, ErrorState, Skeleton } from "./ui";

/** "How I answered": tools in order, the query behind each (template + Cypher + params), rows and time, verifier. */
export function TraceView({ turnId }: { turnId: string }) {
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
      <div className="t-small text-2">Each tool the planner called, in order, with the query it ran. Generated queries are marked unverified.</div>
      {trace.tool_calls.map((c, i) => (
        <section key={i} className="inspector-section">
          <div className="row-wrap">
            <span className="count-badge">{i + 1}</span>
            <span className="t-strong">{c.name}</span>
            <code className="text-2 truncate">{JSON.stringify(c.args)}</code>
          </div>
          {c.queries.map((q, j) => (
            <div key={j} className="stack" style={{ marginLeft: 26 }}>
              <div className="row-wrap t-small text-2">
                <Chip tone="neutral">{q.template}</Chip>
                {q.unverified && <Chip tone="warning">Generated, unverified</Chip>}
                <span className="tnum">{q.rows} {q.rows === 1 ? "row" : "rows"}</span>
                <span>·</span>
                <span className="tnum">{q.ms.toFixed ? q.ms.toFixed(1) : q.ms} ms</span>
              </div>
              <Details summary="Cypher">
                <pre className="code">{q.cypher}</pre>
                <div className="t-small text-3" style={{ marginTop: 6 }}><code>{JSON.stringify(q.params)}</code></div>
              </Details>
            </div>
          ))}
        </section>
      ))}
      {v && (
        <section className="inspector-section">
          <span className="t-label">Verifier</span>
          <div className="row-wrap t-small">
            <Chip tone="success">Kept {v.kept}</Chip>
            <Chip tone={v.dropped.length ? "warning" : "neutral"}>Dropped {v.dropped.length}</Chip>
            {v.rewritten?.length ? <Chip tone="neutral">Rewritten {v.rewritten.length}</Chip> : null}
          </div>
          {v.dropped.length > 0 && <Details summary="Dropped claims"><pre className="code">{JSON.stringify(v.dropped, null, 1)}</pre></Details>}
        </section>
      )}
      {trace.packs && <Details summary="Raw packs (debug)"><pre className="debug">{JSON.stringify(trace.packs, null, 1)}</pre></Details>}
    </div>
  );
}
