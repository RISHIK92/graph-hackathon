"use client";

import { ChevronDown, Filter, Flag, Loader2, Maximize2, MessageSquare, Minus, Plus, RefreshCw, Search, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import GraphCanvas, { NODE_STYLE, type CanvasEdge, type GraphHandle } from "@/components/GraphCanvas";
import { PageHeader } from "@/components/PageHeader";
import { Button, Chip, Empty, ErrorState, Popover } from "@/components/ui";
import { qs } from "@/lib/api";
import { ENTITY_LABELS, fmtDate, plural, SOURCE_KINDS } from "@/lib/format";
import { KIND_LABEL } from "@/lib/labels";
import { useApi, useStore } from "@/lib/store";
import type { GraphData } from "@/lib/types";

export default function GraphPage() {
  return <Suspense fallback={null}><GraphInner /></Suspense>;
}

/** Graph (04 §2.4): subgraph at the As-of date, filters, inspect, ask about the selection,
 * time scrubber over valid time, disputed and stale highlights (current belief). */
function GraphInner() {
  const s = useStore();
  const router = useRouter();
  const params = useSearchParams();
  const [labels, setLabels] = useState<string[]>([]);
  const [kinds, setKinds] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>(() => (params.get("select") || "").split(",").filter(Boolean));
  const [showDisputed, setShowDisputed] = useState(true);
  // The clock is read after mount: Date.now() during render differs between server and client (B4).
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => setNow(Date.now()), []);
  const [showStale, setShowStale] = useState(true);
  const [hideTickets, setHideTickets] = useState(true);
  const [layout, setLayout] = useState<"cose" | "concentric" | "breadthfirst">("cose");
  const [q, setQ] = useState("");
  const [laying, setLaying] = useState(true);
  const [preview, setPreview] = useState<number | null>(null);
  const canvas = useRef<GraphHandle>(null);
  const { data, error, loading, reload } = useApi<GraphData>(`/graph${qs({ as_of: s.asOf, labels: labels.join(","), source_kinds: kinds.join(",") })}`);

  const nodes = useMemo(() => (data?.nodes || []).filter((n) => !hideTickets || !n.labels.includes("Ticket")), [data, hideTickets]);
  // M10: after the date moves, edges that appeared flash green and edges that went away linger faded briefly
  const prevEdges = useRef<Map<string, CanvasEdge> | null>(null);
  const prevAsOf = useRef(s.asOf);
  const [flash, setFlash] = useState<{ added: Set<string>; removed: CanvasEdge[] } | null>(null);
  useEffect(() => {
    if (!data) return;
    const now = new Map(data.edges.map((e): [string, CanvasEdge] => [e.aid, { source: e.source, target: e.target, type: e.type, aid: e.aid, kind: "normal" }]));
    const before = prevEdges.current;
    const moved = before && prevAsOf.current !== s.asOf;
    prevEdges.current = now;
    prevAsOf.current = s.asOf;
    if (!moved) return;
    const added = new Set([...now.keys()].filter((k) => !before.has(k)));
    const removed = [...before.values()].filter((e) => !now.has(e.aid)).map((e): CanvasEdge => ({ ...e, kind: "removed", id: `r-${e.aid}` }));
    if (!added.size && !removed.length) return;
    setFlash({ added, removed });
    const t = setTimeout(() => setFlash(null), 3000);
    return () => clearTimeout(t);
  }, [data, s.asOf]);
  const edges: CanvasEdge[] = useMemo(() => {
    if (!data) return [];
    const ids = new Set(nodes.map((n) => n.id));
    const out: CanvasEdge[] = data.edges.filter((e) => ids.has(e.source) && ids.has(e.target)).map((e) => ({ source: e.source, target: e.target, type: e.type, aid: e.aid, kind: flash?.added.has(e.aid) ? "added" : "normal" }));
    flash?.removed.forEach((e) => ids.has(e.source) && ids.has(e.target) && out.push(e));
    if (showDisputed) data.disputed.forEach((d) => ids.has(d.source) && ids.has(d.target) && out.push({ source: d.source, target: d.target, type: "challenger", aid: d.assertion_id, kind: "disputed", label: "disputed", id: `d-${d.assertion_id}` }));
    if (showStale) data.stale.forEach((st, i) => ids.has(st.source) && ids.has(st.target) && out.push({ source: st.source, target: st.target, type: "stale", aid: st.span, kind: "stale", label: st.doc, id: `s-${i}` }));
    return out;
  }, [data, nodes, showDisputed, showStale, flash]);

  useEffect(() => { setLaying(true); }, [nodes, edges, layout]);

  const names = useMemo(() => new Map((data?.nodes || []).map((n) => [n.id, n.name])), [data]);
  const ticks = useMemo(() => data?.ticks || [], [data]);
  const hi = now ?? ticks[ticks.length - 1] ?? 0;
  const lo = ticks.length ? ticks[0] : hi - 365 * 86400000;
  // M10: the busiest days on the scrubber get a marker, e.g. "12 changes · 1 Apr 2026" for a reorganisation
  const markers = useMemo(() => {
    const byDay = new Map<number, number>();
    ticks.forEach((t) => { const d = Math.floor(t / 86400000) * 86400000; byDay.set(d, (byDay.get(d) || 0) + 1); });
    return [...byDay].filter(([, n]) => n >= 3).sort((a, b) => b[1] - a[1]).slice(0, 3);
  }, [ticks]);
  const cur = preview ?? (s.asOf || hi);
  const toggle = (xs: string[], x: string, set: (v: string[]) => void) => set(xs.includes(x) ? xs.filter((y) => y !== x) : [...xs, x]);
  const applied = labels.length + kinds.length + (hideTickets ? 0 : 1) + (showDisputed ? 0 : 1) + (showStale ? 0 : 1);
  const matches = q.trim() ? nodes.filter((n) => n.name.toLowerCase().includes(q.trim().toLowerCase())).slice(0, 8) : [];

  const askAbout = () => {
    const ns = selected.map((id) => names.get(id) || id);
    const qq = ns.length >= 2 ? `How are ${ns[0]} and ${ns[1]} connected?` : `Tell me about ${ns[0]}`;
    router.push(`/ask${qs({ q: qq, send: "1" })}`);
  };
  const commitAsOf = (v: number) => {
    const next = v >= hi - 86400000 ? null : v;
    const prev = s.asOf;
    setPreview(null);
    if (next === prev) return;
    s.setAsOf(next);
    s.toast({ tone: "info", title: next ? `Viewing as of ${fmtDate(next)}` : "Viewing today", body: "Every page follows this date.", action: { label: "Undo", onClick: () => s.setAsOf(prev) } });
  };
  const dark = typeof document !== "undefined" && document.documentElement.getAttribute("data-theme") === "dark";

  return (
    <div className="graph">
      <PageHeader
        title="Graph"
        description="Everything the brain knows, as of the chosen date. Red lines are disagreements; orange dashed lines are outdated documents."
        actions={
          <>
            <select className="select" style={{ width: "auto" }} value={layout} onChange={(e) => setLayout(e.target.value as typeof layout)} aria-label="Layout">
              <option value="cose">Force layout</option>
              <option value="concentric">Concentric</option>
              <option value="breadthfirst">Hierarchy</option>
            </select>
            <Button icon={RefreshCw} onClick={() => canvas.current?.relayout()}>Reset layout</Button>
            <Button icon={Maximize2} onClick={() => canvas.current?.fit()}>Fit</Button>
          </>
        }
      />
      <div className="graph-toolbar">
        <Popover
          trigger={({ toggle: t, open }) => (
            <div className="input-wrap" style={{ width: 260 }}>
              <Search />
              <input className="input" placeholder="Find a node…" value={q} onChange={(e) => { setQ(e.target.value); if (!open) t(); }} onFocus={() => !open && q && t()} aria-label="Find a node" />
            </div>
          )}
          open={!!q.trim() && matches.length > 0}
          onOpenChange={() => undefined}
        >
          {(close) => (
            <div style={{ width: 300 }}>
              {matches.map((n) => (
                <button key={n.id} className="menu-item" onClick={() => { setSelected([n.id]); canvas.current?.center(n.id); s.openEntity(n.id, n.name); setQ(""); close(); }}>
                  <span className="truncate">{n.name}</span><span className="meta">{n.labels.find((l) => l !== "Entity")}</span>
                </button>
              ))}
            </div>
          )}
        </Popover>
        <FilterPopover label="Entity type" count={labels.length}>
          {ENTITY_LABELS.map((l) => (
            <label key={l} className="checkbox menu-item"><input type="checkbox" checked={labels.includes(l)} onChange={() => toggle(labels, l, setLabels)} />{l}</label>
          ))}
          <div className="t-small text-3" style={{ padding: "4px 10px" }}>None selected shows all types.</div>
        </FilterPopover>
        <FilterPopover label="Source kind" count={kinds.length}>
          {SOURCE_KINDS.map((k) => (
            <label key={k} className="checkbox menu-item"><input type="checkbox" checked={kinds.includes(k)} onChange={() => toggle(kinds, k, setKinds)} />{KIND_LABEL[k] || k}</label>
          ))}
          <div className="t-small text-3" style={{ padding: "4px 10px" }}>Show only facts that come from these sources.</div>
        </FilterPopover>
        <FilterPopover label="Highlights" count={(showDisputed ? 0 : 1) + (showStale ? 0 : 1) + (hideTickets ? 0 : 1)}>
          <label className="checkbox menu-item"><input type="checkbox" checked={showDisputed} onChange={() => setShowDisputed((v) => !v)} />Disputed <span className="meta">{data?.disputed.length ?? 0}</span></label>
          <label className="checkbox menu-item"><input type="checkbox" checked={showStale} onChange={() => setShowStale((v) => !v)} />Stale documents <span className="meta">{data?.stale.length ?? 0}</span></label>
          <label className="checkbox menu-item"><input type="checkbox" checked={hideTickets} onChange={() => setHideTickets((v) => !v)} />Hide tickets</label>
          <div className="t-small text-3" style={{ padding: "4px 10px" }}>Highlights always show today&apos;s view. The slider changes the date shown.</div>
        </FilterPopover>
        {labels.map((l) => <Chip key={l} tone="accent" onClick={() => toggle(labels, l, setLabels)} title="Remove">{l} <X /></Chip>)}
        {kinds.map((k) => <Chip key={k} tone="accent" onClick={() => toggle(kinds, k, setKinds)} title="Remove">{KIND_LABEL[k] || k} <X /></Chip>)}
        {!hideTickets && <Chip tone="accent" onClick={() => setHideTickets(true)}>Tickets shown <X /></Chip>}
        {applied > 0 && <Button size="sm" variant="ghost" onClick={() => { setLabels([]); setKinds([]); setHideTickets(true); setShowDisputed(true); setShowStale(true); }}>Clear all</Button>}
        <span className="result-count">{loading ? <span className="row"><Loader2 className="icon-sm spin" />Loading…</span> : data ? `${plural(nodes.length, "node")} · ${plural(edges.length, "edge")}` : ""}</span>
      </div>
      <div className="scrubber">
        <span className="date tnum">{fmtDate(lo)}</span>
        <div className="track">
          <input
            type="range" min={lo} max={hi} step={86400000} value={cur}
            aria-label="As-of date" aria-valuetext={fmtDate(cur)}
            onChange={(e) => setPreview(Number(e.target.value))}
            onMouseUp={(e) => commitAsOf(Number((e.target as HTMLInputElement).value))}
            onTouchEnd={(e) => commitAsOf(Number((e.target as HTMLInputElement).value))}
            onKeyUp={(e) => { if (["ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown"].includes(e.key)) commitAsOf(Number((e.target as HTMLInputElement).value)); }}
          />
          <div className="ticks" aria-hidden>
            {ticks.map((t) => <i key={t} style={{ left: `${((t - lo) / (hi - lo)) * 100}%` }} title={fmtDate(t)} />)}
          </div>
          <div className="markers">
            {markers.map(([d, n]) => (
              <button key={d} className="marker" style={{ left: `${((d - lo) / (hi - lo)) * 100}%` }} onClick={() => commitAsOf(d + 86400000)} title={`Jump to just after ${fmtDate(d)}`}>
                {n} changes · {fmtDate(d)}
              </button>
            ))}
          </div>
        </div>
        <span className="date cur tnum">{cur >= hi - 86400000 ? "Today" : fmtDate(cur)}</span>
        {s.asOf && <Button size="sm" onClick={() => commitAsOf(hi)}>Today</Button>}
      </div>
      <div className="graph-stage">
        {error && <div style={{ padding: 24 }}><ErrorState message={error} onRetry={reload} /></div>}
        {data && nodes.length > 0 && (
          <GraphCanvas
            ref={canvas}
            nodes={nodes}
            edges={edges}
            selected={selected}
            layout={layout}
            onReady={() => setLaying(false)}
            onNode={(id, additive) => {
              setSelected((cur) => (additive ? (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]) : [id]));
              if (!additive) s.openEntity(id, names.get(id));
            }}
            onEdge={(e) => s.openInspector({ kind: "edge", aid: e.aid, source: e.source, target: e.target, type: e.type, edgeKind: e.kind === "added" || e.kind === "removed" ? "normal" : e.kind, label: e.label })}
            onBackground={() => undefined}
          />
        )}
        {(loading || (data && nodes.length > 0 && laying)) && !error && (
          <div className="graph-overlay"><div className="row text-2"><Loader2 className="icon spin" />{loading ? "Loading the graph…" : `Laying out ${plural(nodes.length, "node")}…`}</div></div>
        )}
        {data && nodes.length === 0 && !loading && (
          <div className="graph-overlay"><Empty icon={Filter} title="No nodes match these filters" action={<Button size="sm" onClick={() => { setLabels([]); setKinds([]); setHideTickets(true); }}>Clear filters</Button>} /></div>
        )}
        {selected.length > 0 && (
          <div className="selbar">
            <span className="t-small">{plural(selected.length, "node")} selected</span>
            <Button size="sm" variant="primary" icon={MessageSquare} onClick={askAbout}>Ask about {selected.length > 1 ? "the selection" : "it"}</Button>
            <Button size="sm" variant="ghost" icon={X} aria-label="Clear selection" onClick={() => setSelected([])} />
          </div>
        )}
        <div className="legend" aria-label="Legend">
          {ENTITY_LABELS.filter((l) => !hideTickets || l !== "Ticket").map((l) => {
            const st = NODE_STYLE[l];
            const colour = dark ? st.dark : st.colour;
            const shape = st.shape === "diamond" ? "rotate(45deg) scale(0.8)" : undefined;
            return <span key={l} className="item"><i className="sw" style={{ background: colour, borderRadius: st.shape === "ellipse" ? "50%" : 2, transform: shape, clipPath: st.shape === "triangle" ? "polygon(50% 0, 100% 100%, 0 100%)" : undefined }} />{l}</span>;
          })}
          <span className="item"><i className="ln" style={{ borderColor: "var(--border-strong)" }} />Fact valid at the date</span>
          <span className="item"><i className="ln" style={{ borderColor: "var(--error-600)" }} /><Flag className="icon-sm text-error" />Open dispute</span>
          <span className="item"><i className="ln" style={{ borderColor: "var(--warning-600)", borderTopStyle: "dashed" }} />Stale document</span>
        </div>
        <div className="zoomctl">
          <button onClick={() => canvas.current?.zoomIn()} aria-label="Zoom in"><Plus className="icon-sm" /></button>
          <button onClick={() => canvas.current?.zoomOut()} aria-label="Zoom out"><Minus className="icon-sm" /></button>
          <button onClick={() => canvas.current?.fit()} aria-label="Fit to screen"><Maximize2 className="icon-sm" /></button>
        </div>
      </div>
    </div>
  );
}

function FilterPopover({ label, count, children }: { label: string; count: number; children: React.ReactNode }) {
  return (
    <Popover trigger={({ toggle, open }) => (
      <Button size="sm" variant={count ? "primary" : "secondary"} onClick={toggle} aria-expanded={open}>
        <Filter className="icon-sm" />{label}{count ? ` · ${count}` : ""}<ChevronDown className="icon-sm" />
      </Button>
    )}>
      <div style={{ width: 260 }}>{children}</div>
    </Popover>
  );
}
