"use client";

import { FileText, Flag, GitBranch, History, Quote } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { qs } from "@/lib/api";
import { useApi, useNames, useOpenMode, useStore, type EvidenceTarget } from "@/lib/store";
import { fmtDate, fmtDateTime, fmtInterval, labelOf } from "@/lib/format";
import { edgeVerb, KIND_LABEL, predicateLabel } from "@/lib/labels";
import type { Fact, Pack, Path, PathStep, SourceView, SpanItem, SpanView } from "@/lib/types";
import { CitationChip } from "./Chips";
import GraphCanvas from "./GraphCanvas";
import { EvidenceText } from "./EvidenceText";
import { SourceLinks } from "./SourceLinks";
import { HistoryTimeline } from "./Timeline";
import { Button, Chip, Details, Empty, ErrorState, Notice, Placeholder, Skeleton, Tabs } from "./ui";

/** Evidence: three tabs, Source / Path / Timeline (04 §2.3). Lives in the inspector. */
export default function EvidencePanel({ target, packs }: { target: EvidenceTarget; packs?: Pack[] }) {
  const { openInspector } = useStore();
  const set = (tab: EvidenceTarget["tab"]) => openInspector({ kind: "evidence", target: { ...target, tab } }, "replace");
  const canSource = !!(target.spanId || target.sourceId);
  const canPath = !!(target.path || target.pathId);
  const canTimeline = !!target.timeline;
  return (
    <div className="inspector-body flush">
      <Tabs
        value={target.tab}
        onChange={(t) => set(t as EvidenceTarget["tab"])}
        tabs={[
          { id: "source", label: <><FileText className="icon-sm" />Source</>, disabled: !canSource, reason: "No source span for this item" },
          { id: "path", label: <><GitBranch className="icon-sm" />Path</>, disabled: !canPath, reason: "No graph path for this citation (text-only evidence)" },
          { id: "timeline", label: <><History className="icon-sm" />Timeline</>, disabled: !canTimeline, reason: "No fact chain for this item" },
        ]}
      />
      <div style={{ padding: 16 }} className="stack-4">
        {target.tab === "source" && target.spanId && <SourceTab spanId={target.spanId} sourceId={target.sourceId} quote={target.quote} />}
        {target.tab === "source" && !target.spanId && target.sourceId && <WholeSource sourceId={target.sourceId} />}
        {target.tab === "path" && <PathTab target={target} packs={packs?.length ? packs : target.packs || []} />}
        {target.tab === "timeline" && target.timeline && <TimelineTab {...target.timeline} />}
      </div>
    </div>
  );
}

// Source

function SourceTab({ spanId, sourceId, quote }: { spanId: string; sourceId?: string; quote?: { start?: number | null; end?: number | null } }) {
  const span = useApi<SpanView>(`/spans/${encodeURIComponent(spanId)}`);
  const [chosen, setChosen] = useState<string>("");
  const revs = span.data?.revisions || [];
  const latestLive = revs.find((r) => r.latest && r.live);
  const latestAny = revs.find((r) => r.latest);
  const rev = revs.find((r) => r.source === chosen) || latestLive || revs.find((r) => r.source === sourceId) || revs[revs.length - 1];
  const src = useApi<SourceView>(rev ? `/sources/${encodeURIComponent(rev.source)}` : null);
  const names = useNames(span.data?.author ? [span.data.author] : []);

  useEffect(() => setChosen(""), [spanId]);
  useEffect(() => {
    const el = document.getElementById(`span-${spanId}`);
    el?.scrollIntoView({ block: "center" });
  }, [src.data, spanId]);

  if (span.error) return <ErrorState message={span.error} onRetry={span.reload} />;
  if (!span.data) return <div className="stack"><Skeleton w="60%" /><Skeleton h={200} /></div>;
  const revIndex = revs.findIndex((r) => r.source === rev?.source);
  return (
    <div className="stack-3">
      <div className="row-wrap">
        <Chip icon={Quote}>{KIND_LABEL[span.data.kind] || span.data.kind}</Chip>
        <span className="t-small text-2">{fmtDate(span.data.ts)}</span>
        <span className="t-small text-2">·</span>
        <span className="t-small t-strong truncate">{rev?.title}</span>
        {rev && <span className="right"><SourceLinks sourceId={rev.source} spanId={spanId} url={src.data?.link?.url} system={String(src.data?.source.system || "")} demo={src.data?.link?.demo} /></span>}
      </div>
      {!latestLive && (
        <Notice
          tone="warning"
          title="Not in the latest revision"
          actions={latestAny ? <Button size="sm" variant="link" onClick={() => setChosen(latestAny.source)}>Open the latest revision</Button> : undefined}
        >
          {latestAny ? "This text was changed or removed in a later revision of the document." : "This text was removed from the document."}
        </Notice>
      )}
      {revs.length > 1 && (
        <label className="row t-small text-2">
          Revision
          <select className="select sm" style={{ width: "auto", height: 28 }} value={rev?.source} onChange={(e) => setChosen(e.target.value)}>
            {revs.map((r, i) => (
              <option key={r.source} value={r.source} title={r.source}>
                Revision {i + 1}{r.latest ? " · latest" : ""}{r.live ? "" : " · span removed"}
              </option>
            ))}
          </select>
        </label>
      )}
      {src.data?.banner && <Notice tone="warning">{src.data.banner}</Notice>}
      {span.data.kind === "chat_session" ? (
        // m13: a message from this app's chat is shown alone, with who said it and when, not the whole transcript
        <div className="src-doc">
          <div className="t-small text-2" style={{ padding: "8px 12px 0" }}>
            {span.data.role === "agent" ? "Nodus" : names[span.data.author || ""]?.name || "Someone in this chat"} · {fmtDateTime(span.data.ts)}
          </div>
          <div className="src-span hit"><Quoted text={span.data.text} start={quote?.start} end={quote?.end} /></div>
        </div>
      ) : <div className="src-doc">
        {src.loading && !src.data && <div style={{ padding: 12 }} className="stack"><Skeleton /><Skeleton w="80%" /><Skeleton w="90%" /></div>}
        {src.data &&
          src.data.spans.map((s) =>
            s.span === spanId ? (
              <div key={s.span} id={`span-${s.span}`} className="src-span hit">
                <EvidenceText text={s.text} kind={span.data?.kind}><Quoted text={s.text} start={quote?.start} end={quote?.end} /></EvidenceText>
              </div>
            ) : (
              <div key={s.span} className="src-span"><EvidenceText text={s.text} kind={span.data?.kind} /></div>
            ),
          )}
        {src.data && !src.data.spans.some((s) => s.span === spanId) && (
          <div className="src-span hit"><Quoted text={span.data.text} start={quote?.start} end={quote?.end} /></div>
        )}
      </div>}
      <Details summary="Details">
        <dl className="kv narrow t-small">
          <dt>Span</dt><dd className="mono">{spanId}</dd>
          <dt>Source</dt><dd className="mono">{rev?.source}</dd>
          <dt>Revision</dt><dd>{revIndex >= 0 ? revIndex + 1 : "?"} of {revs.length}</dd>
          <dt>Offsets</dt><dd className="mono">{rev ? `${rev.cs}..${rev.ce}` : "?"}</dd>
        </dl>
      </Details>
    </div>
  );
}

function WholeSource({ sourceId }: { sourceId: string }) {
  const src = useApi<SourceView>(`/sources/${encodeURIComponent(sourceId)}`);
  if (src.error) return <ErrorState message={src.error} onRetry={src.reload} />;
  if (!src.data) return <div className="stack"><Skeleton w="60%" /><Skeleton h={200} /></div>;
  const kind = String(src.data.source.kind || "");
  return (
    <div className="stack-3">
      <div className="row-wrap">
        <Chip icon={Quote}>{KIND_LABEL[kind] || kind}</Chip>
        <span className="t-small t-strong truncate">{String(src.data.source.title || sourceId)}</span>
        <span className="right"><SourceLinks sourceId={sourceId} url={src.data.link?.url} system={String(src.data.source.system || "")} demo={src.data.link?.demo} /></span>
      </div>
      {kind === "draft" && <Notice tone="warning" title="Agent draft">Display only. Drafts are never evidence.</Notice>}
      {src.data.banner && <Notice tone="warning">{src.data.banner}</Notice>}
      <div className="src-doc">
        {src.data.spans.map((s) => <div key={s.span} className="src-span">{s.text}</div>)}
      </div>
    </div>
  );
}

function Quoted({ text, start, end }: { text: string; start?: number | null; end?: number | null }) {
  if (start === null || start === undefined || !end || end <= start || end > text.length || (start === 0 && end === text.length)) {
    return <>{text}</>;
  }
  return (
    <>
      {text.slice(0, start)}
      <mark>{text.slice(start, end)}</mark>
      {text.slice(end)}
    </>
  );
}

// Path

function PathTab({ target, packs }: { target: EvidenceTarget; packs: Pack[] }) {
  const router = useRouter();
  const { asOf, closeInspector } = useStore();
  const [expand, setExpand] = useState(false);
  const path = useMemo<Path | null>(() => {
    if (target.path) return target.path;
    for (const p of packs) for (const it of p.items) if (it.path?.path_id === target.pathId) return it.path;
    return null;
  }, [target, packs]);
  const packId = useMemo(() => {
    if (target.packId) return target.packId;
    for (const p of packs) for (const it of p.items) if (it.path?.path_id === path?.path_id) return p.pack_id;
    return null;
  }, [target, packs, path]);
  const impact = useMemo(() => {
    if (target.impactPaths?.length) return target.impactPaths;
    const pk = packs.find((p) => p.pack_id === packId);
    if (pk && pk.tool === "find_paths" && !pk.args?.to_id) return pk.items.map((i) => i.path).filter(Boolean) as Path[];
    return [];
  }, [target, packs, packId]);
  const remote = useApi<{ steps: PathStep[] }>(path && packId && target.fromTurn ? `/paths/${encodeURIComponent(path.path_id)}${qs({ pack: packId })}` : null);
  const { facts, spans } = useMemo(() => {
    const fs: Fact[] = [];
    const ss: SpanItem[] = [];
    for (const p of packs) for (const it of p.items) { fs.push(...(it.facts || [])); ss.push(...(it.spans || [])); }
    return { facts: fs, spans: ss };
  }, [packs]);

  if (!path) return <Empty icon={GitBranch} title="No path for this citation">Text-only evidence has no graph path.</Empty>;
  const steps = remote.data?.steps || path.steps;
  const ids = Array.from(new Set(path.steps.map((s) => s.node.id).filter((x) => x.includes(":"))));
  return (
    <div className="stack-4">
      <PathSteps steps={steps} facts={facts} spans={spans} />
      <div className="row-wrap">
        <Button size="sm" onClick={() => setExpand((v) => !v)} disabled={!ids.length && !impact.length}>
          {expand ? (impact.length > 1 ? "Hide affected paths" : "Hide neighbourhood") : impact.length > 1 ? `Show all ${impact.length} affected paths` : "Show neighbourhood"}
        </Button>
        <Button size="sm" icon={GitBranch} disabled={!ids.length} onClick={() => { closeInspector(); router.push(`/graph?select=${encodeURIComponent(ids.join(","))}`); }}>
          Open in Graph
        </Button>
      </div>
      {expand &&
        (impact.length > 1 ? (
          <div className="stack-3">
            {impact.map((p) => (
              <div key={p.path_id} className="card-tight">
                <PathSteps steps={p.steps} facts={facts} spans={spans} compact />
              </div>
            ))}
          </div>
        ) : (
          <Neighbourhood ids={ids} asOf={asOf} />
        ))}
    </div>
  );
}

export function PathSteps({ steps, facts, spans, compact }: { steps: PathStep[]; facts: Fact[]; spans: SpanItem[]; compact?: boolean }) {
  const { openEntity } = useStore();
  const mode = useOpenMode();
  return (
    <div className="path">
      {steps.map((st, i) => {
        const e = st.edge;
        const runFacts = e ? facts.filter((f) => f.run_id === e.aid || f.assertion_id === e.aid) : [];
        const status = runFacts.find((f) => f.status === "superseded") && !runFacts.find((f) => f.status === "current") ? "superseded" : "";
        const disputes = Array.from(new Set(runFacts.flatMap((f) => f.open_disputes || [])));
        const ev = st.evidence || spans.filter((s) => runFacts.some((f) => s.cites?.includes(f.assertion_id)));
        const lab = st.node.labels?.[0] || labelOf(undefined, st.node.id);
        return (
          <div key={i} className="stack" style={{ gap: 0 }}>
            {e && (
              <>
                <div className={`path-edge ${status} ${disputes.length ? "disputed" : ""}`}>
                  <div className="rel">
                    <b>{edgeVerb(e.type, e.dir)}</b>
                    {(e.valid_from !== null || e.valid_to !== null) && <span className="mono">{fmtInterval(e.valid_from, e.valid_to)}</span>}
                    {status === "superseded" && <Chip tone="neutral">Superseded</Chip>}
                    {!compact && (
                      ev.length ? (
                        <Details summary={`Evidence (${ev.length})`}>
                          <div className="row-wrap">{ev.map((s) => <CitationChip key={s.span_id} span={s} />)}</div>
                        </Details>
                      ) : <span className="text-3">No evidence loaded</span>
                    )}
                  </div>
                </div>
                {disputes.map((d) => {
                  const df = facts.find((f) => f.assertion_id === d);
                  return <div key={d} className="path-side"><Flag className="icon-sm" />Disputed by: {df?.statement || d}</div>;
                })}
              </>
            )}
            <div className="path-node">
              {st.node.id.includes(":") ? (
                <button className="entity-link" onClick={() => openEntity(st.node.id, st.node.name, mode)}>{st.node.name}</button>
              ) : (
                <span>{st.node.name}</span>
              )}
              <Chip tone="neutral">{lab}</Chip>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Neighbourhood({ ids, asOf }: { ids: string[]; asOf: number | null }) {
  const { openEntity } = useStore();
  const mode = useOpenMode();
  const [hops, setHops] = useState(1);
  const n = useApi<{ nodes: { id: string; name: string; labels: string[] }[]; edges: { source: string; target: string; type: string; aid: string }[] }>(
    ids.length ? `/graph/neighbourhood${qs({ ids: ids.join(","), as_of: asOf, hops })}` : null,
  );
  return (
    <div className="stack">
      <div className="row t-small">
        <span className="text-2">Neighbourhood</span>
        <select className="select" style={{ width: "auto", height: 28 }} value={hops} onChange={(e) => setHops(Number(e.target.value))}>
          <option value={1}>1 hop</option>
          <option value={2}>2 hops</option>
        </select>
        {n.data && <span className="text-3">{n.data.nodes.length} nodes · {n.data.edges.length} edges</span>}
      </div>
      {n.error && <ErrorState message={n.error} onRetry={n.reload} inline />}
      {!n.data && !n.error && <Skeleton h={320} />}
      {n.data && (
        <div style={{ height: 320, position: "relative", border: "1px solid var(--border)", borderRadius: 6, overflow: "hidden" }}>
          <GraphCanvas nodes={n.data.nodes} edges={n.data.edges.map((e) => ({ ...e, kind: "normal" as const }))} selected={ids} onNode={(id) => openEntity(id, undefined, mode)} layout="cose" />
        </div>
      )}
    </div>
  );
}

// Timeline

function TimelineTab({ entityId, predicate }: { entityId: string; predicate: string }) {
  const { names, resolveNames } = useStore();
  useEffect(() => { resolveNames([entityId]); }, [entityId, resolveNames]);
  const h = useApi<Pack>(`/entities/${encodeURIComponent(entityId)}/history${qs({ predicate })}`);
  if (h.error) return <ErrorState message={h.error} onRetry={h.reload} />;
  if (!h.data) return <div className="stack"><Skeleton w="50%" /><Skeleton h={36} /><Skeleton h={36} /></div>;
  return (
    <div className="stack-3">
      <div className="t-strong">History of {predicateLabel(predicate).toLowerCase()} · {names[entityId]?.name || entityId}</div>
      {h.data.items.length ? <HistoryTimeline pack={h.data} /> : <Placeholder>No history recorded.</Placeholder>}
    </div>
  );
}
