"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import GraphCanvas, { type CanvasEdge } from "@/components/GraphCanvas";
import { ErrorState, SkeletonRows } from "@/components/ui";
import { get, qs } from "@/lib/api";
import { edgeVerb } from "@/lib/labels";
import { useApi, useStore } from "@/lib/store";
import type { Directory } from "@/lib/types";

export default function ExplorePage() {
  return <Suspense fallback={null}><Explore /></Suspense>;
}

type Kind = "systems" | "people" | "decisions" | "tickets";
interface Row { id: string; name: string; kind: Kind; meta: string; disputed: boolean }
interface Hood { nodes: { id: string; name: string; labels: string[] }[]; edges: { source: string; target: string; type: string; aid: string }[] }

const PILLS: [Kind | "all", string][] = [["all", "All"], ["systems", "Systems"], ["people", "Teams & people"], ["decisions", "Decisions"], ["tickets", "Tickets"]];
const TONE: Record<Kind, string> = { systems: "sys", people: "per", decisions: "rec", tickets: "rec" };

/** Explore (design brief step 6): find anything on the left, the graph around it in the middle (depth 1-3),
 * and what it is on the right. One page for what Directory and Graph showed apart; both stay as they were. */
function Explore() {
  const s = useStore();
  const router = useRouter();
  const params = useSearchParams();
  const dir = useApi<Directory>(`/directory${qs({ as_of: s.asOf })}`);
  const [q, setQ] = useState("");
  const [kind, setKind] = useState<Kind | "all">("all");
  const [depth, setDepth] = useState(1);
  const [to, setTo] = useState("");
  const rows = useMemo<Row[]>(() => {
    const d = dir.data;
    if (!d) return [];
    return [
      ...d.systems.map((x): Row => ({ id: x.id, name: x.name, kind: "systems", meta: x.owner ? `Owned by ${x.owner.name}` : "No owner", disputed: x.disputed })),
      ...d.projects.map((x): Row => ({ id: x.id, name: x.name, kind: "systems", meta: x.owner ? `Project · owned by ${x.owner.name}` : "Project", disputed: x.disputed })),
      ...d.teams.map((x): Row => ({ id: x.id, name: x.name, kind: "people", meta: x.leads.length ? `Led by ${x.leads.map((l) => l.name).join(", ")}` : "No current lead", disputed: false })),
      ...d.people.map((x): Row => ({ id: x.id, name: x.name, kind: "people", meta: x.leads.length ? `Leads ${x.leads.map((l) => l.name).join(", ")}` : x.team ? x.team.name : x.title || "Person", disputed: x.disputed })),
      ...d.decisions.map((x): Row => ({ id: x.id, name: x.name, kind: "decisions", meta: [x.title, x.status].filter(Boolean).join(" · "), disputed: x.disputed })),
      ...d.tickets.map((x): Row => ({ id: x.id, name: x.name, kind: "tickets", meta: [x.state, x.assignee?.name].filter(Boolean).join(" · "), disputed: x.disputed })),
    ];
  }, [dir.data]);
  const counts = useMemo(() => Object.fromEntries(PILLS.map(([k]) => [k, k === "all" ? rows.length : rows.filter((r) => r.kind === k).length])), [rows]);
  const shown = rows.filter((r) => (kind === "all" || r.kind === kind) && (!q || r.name.toLowerCase().includes(q.toLowerCase())));
  const sel = params.get("id") || shown[0]?.id || "";
  const pick = (id: string) => router.replace(`/explore${qs({ id })}`);
  const current = rows.find((r) => r.id === sel);

  // the neighbourhood endpoint walks at most 2 hops; depth 3 adds one more hop from what depth 2 found
  const [hood, setHood] = useState<Hood | null>(null);
  useEffect(() => {
    if (!sel) return;
    let live = true;
    (async () => {
      const first = await get<Hood>(`/graph/neighbourhood${qs({ ids: sel, hops: Math.min(depth, 2), as_of: s.asOf })}`);
      let out = first;
      if (depth > 2 && first.nodes.length) {
        const more = await get<Hood>(`/graph/neighbourhood${qs({ ids: first.nodes.map((n) => n.id).join(","), hops: 1, as_of: s.asOf })}`);
        out = { nodes: [...new Map([...first.nodes, ...more.nodes].map((n) => [n.id, n])).values()],
                edges: [...new Map([...first.edges, ...more.edges].map((e) => [e.aid, e])).values()] };
      }
      if (live) setHood(out);
    })().catch(() => live && setHood({ nodes: [], edges: [] }));
    return () => { live = false; };
  }, [sel, depth, s.asOf]);
  const edges = useMemo<CanvasEdge[]>(() => (hood?.edges || []).map((e) => ({ ...e, kind: "normal" })), [hood]);
  const names = useMemo(() => new Map((hood?.nodes || []).map((n) => [n.id, n.name])), [hood]);
  const facts = (hood?.edges || []).filter((e) => e.source === sel || e.target === sel).slice(0, 8);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || e.metaKey || e.ctrlKey) return;
      const i = shown.findIndex((r) => r.id === sel);
      if (e.key === "j" && shown[i + 1]) pick(shown[i + 1].id);
      if (e.key === "k" && i > 0) pick(shown[i - 1].id);
      if (e.key === "Enter" && sel) router.push(`/e/${encodeURIComponent(sel)}`);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  if (dir.error) return <div className="page-body"><ErrorState message={dir.error} onRetry={dir.reload} /></div>;
  return (
    <div className="explore">
      <section className="explore-find" aria-label="Find">
        <div className="explore-search">
          <label htmlFor="find" className="sr-only">Find anything</label>
          <input id="find" type="search" placeholder="Find a system, team or person" value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="row-wrap" style={{ gap: 6 }}>
            {PILLS.map(([k, label]) => (
              <button key={k} type="button" className={`explore-pill ${kind === k ? "on" : ""}`} aria-pressed={kind === k} onClick={() => setKind(k)}>
                {label} <span className="n">{counts[k] ?? 0}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="explore-rows" role="listbox" aria-label="Results">
          {!dir.data ? <div style={{ padding: 16 }}><SkeletonRows n={6} /></div> : shown.map((r) => (
            <button key={r.id} type="button" role="option" aria-selected={r.id === sel} className={`explore-row ${r.id === sel ? "sel" : ""}`} onClick={() => pick(r.id)}>
              <i className={TONE[r.kind]} />
              <span className="stack" style={{ gap: 0, minWidth: 0, flex: "1 1 auto" }}><span className="t-strong truncate">{r.name}</span><span className="t-small text-3 truncate">{r.meta}</span></span>
              {r.disputed && <span className="explore-disp">disputed</span>}
            </button>
          ))}
        </div>
        <div className="inbox-keys"><kbd>j</kbd> <kbd>k</kbd> move · <kbd>Enter</kbd> open page</div>
      </section>

      <section className="explore-graph" aria-label="Graph">
        <div className="explore-bar">
          <span className="t-small text-label">Around <span className="t-strong" style={{ color: "var(--text)" }}>{current?.name || "…"}</span></span>
          <span className="grow" />
          <span className="t-small text-3">Depth</span>
          <div className="seg" role="group" aria-label="Depth">
            {[1, 2, 3].map((n) => <button key={n} type="button" className={depth === n ? "on" : ""} onClick={() => setDepth(n)}>{n}</button>)}
          </div>
          <form className="row" style={{ gap: 6 }} onSubmit={(e) => { e.preventDefault(); if (current && to.trim()) router.push(`/ask${qs({ q: `How is ${current.name} connected to ${to.trim()}?`, send: "1" })}`); }}>
            <input className="input sm" placeholder="Find a path to…" value={to} onChange={(e) => setTo(e.target.value)} list="explore-names" style={{ width: 180 }} />
            <datalist id="explore-names">{rows.slice(0, 200).map((r) => <option key={r.id} value={r.name} />)}</datalist>
          </form>
        </div>
        <div className="explore-canvas">
          {hood && <GraphCanvas nodes={hood.nodes} edges={edges} selected={sel ? [sel] : []} onNode={(id) => pick(id)} layout="cose" maxZoom={2} />}
        </div>
      </section>

      <aside className="explore-panel" aria-label="Selected">
        {current && (
          <div className="stack nx-rise" key={current.id} style={{ gap: 18 }}>
            <div className="stack" style={{ gap: 6 }}>
              <span className={`entity-kind ${TONE[current.kind]}`}>{current.id.split(":")[0].toUpperCase()}</span>
              <span style={{ fontSize: 24, fontWeight: 600, letterSpacing: "-0.02em" }}>{current.name}</span>
              <span className="t-small text-2">{current.meta}</span>
            </div>
            {current.disputed && <Link href="/inbox" className="entity-dispute"><i /><span>Something here is disputed.</span><span className="go">Settle →</span></Link>}
            <div className="stack" style={{ gap: 0 }}>
              {facts.map((e) => {
                const out = e.source === sel;
                return (
                  <div key={e.aid} className="explore-fact">
                    <span className="rel">{out ? `${edgeVerb(e.type).toUpperCase()} →` : `← ${edgeVerb(e.type).toUpperCase()}`}</span>
                    <button type="button" className="link-btn" onClick={() => pick(out ? e.target : e.source)}>{names.get(out ? e.target : e.source) || (out ? e.target : e.source)}</button>
                  </div>
                );
              })}
              {hood && !facts.length && <span className="t-small text-3">Nothing connects to it at this date.</span>}
            </div>
            <div className="row-wrap" style={{ gap: 8 }}>
              <Link href={`/ask${qs({ q: current.kind === "systems" ? `Who owns ${current.name}?` : `Tell me about ${current.name}`, send: "1" })}`} className="composer-send">Ask about {current.name}</Link>
              <Link href={`/e/${encodeURIComponent(current.id)}`} className="composer-chip">Open full page</Link>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
