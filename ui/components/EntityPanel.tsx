"use client";

import { ArrowUpRight, Flag, MessageSquare, Quote } from "lucide-react";
import { useRouter } from "next/navigation";
import { qs } from "@/lib/api";
import { fmtDate, labelOf } from "@/lib/format";
import { KIND_LABEL, predicateLabel } from "@/lib/labels";
import { useApi, useNames, useOpenMode, useStore } from "@/lib/store";
import type { EntityPanel as EntityPanelData, NameMap, Pack, Path } from "@/lib/types";
import { FactRow, PackContext } from "./Chips";
import { collectDisputes, DisputeBlock, type DisputeGroup } from "./Dispute";
import { HistoryTimeline } from "./Timeline";
import { Button, Chip, Empty, EntityLink, ErrorState, Placeholder, Skeleton, Tabs } from "./ui";

export function useEntity(id: string) {
  const { asOf } = useStore();
  return useApi<EntityPanelData>(`/entities/${encodeURIComponent(id)}${qs({ as_of: asOf })}`);
}

export function packsOf(data: EntityPanelData | null): Pack[] {
  return data ? ([data.owner, data.depended_on_by, data.decisions, ...Object.values(data.history || {})].filter(Boolean) as Pack[]) : [];
}

/** B2: disputes about this entity only; the impact and decision packs also carry its neighbours' disputes. */
export function disputesOf(data: EntityPanelData | null, id: string): DisputeGroup[] {
  return collectDisputes(packsOf(data)).filter((g) => {
    const f = g.recorded || g.challengers[0]?.fact;
    return !!f && (f.subject_id === id || f.object_id === id);
  });
}

/** Entity header actions shared by the inspector peek and the page. */
export function EntityActions({ data, id, inPage }: { data: EntityPanelData | null; id: string; inPage?: boolean }) {
  const router = useRouter();
  const { closeInspector } = useStore();
  const name = data?.name || id;
  return (
    <div className="row">
      <Button size="sm" icon={MessageSquare} onClick={() => router.push(`/ask${qs({ q: `Tell me about ${name}`, send: "1" })}`)}>Ask about this</Button>
      {!inPage && <Button size="sm" variant="ghost" icon={ArrowUpRight} onClick={() => { closeInspector(); router.push(`/e/${encodeURIComponent(id)}`); }}>Open page</Button>}
    </div>
  );
}

/** Summary section (Overview tab / peek): owner or lead, dependencies, decisions, recent history. */
export function EntitySummary({ data, id, full }: { data: EntityPanelData; id: string; full?: boolean }) {
  const { asOf } = useStore();
  const packs = packsOf(data);
  const disputes = disputesOf(data, id);
  const label = labelOf(data.labels, id);
  const ownerFacts = (data.owner?.items || []).filter((it) => it.note !== "open dispute");
  const historyEntries = Object.entries(data.history || {}).filter(([, p]) => p.items.length);
  return (
    <PackContext.Provider value={{ packs, fromTurn: false }}>
      <div className="stack-6">
        {disputes.length > 0 && (
          <section className="inspector-section">
            <div className="section-title"><Flag className="icon-sm text-warning" /><span className="t-heading">Open disputes</span><Chip tone="warning">{disputes.length}</Chip></div>
            {disputes.map((g, i) => <DisputeBlock key={i} g={g} />)}
          </section>
        )}
        <section className="inspector-section">
          <span className="t-label">Summary</span>
          <dl className="kv">
            <dt>Type</dt><dd><Chip tone="neutral">{label}</Chip></dd>
            {data.d && <><dt>Description</dt><dd>{data.d}</dd></>}
            {data.lead && <><dt>Lead</dt><dd>{data.lead.length ? <div className="row-wrap">{data.lead.map((l) => <EntityLink key={l.id} id={l.id} name={l.name} />)}</div> : <Placeholder>No current lead</Placeholder>}</dd></>}
            {data.depends_on && <><dt>Depends on</dt><dd>{data.depends_on.length ? <div className="row-wrap">{data.depends_on.map((d) => <EntityLink key={d.id} id={d.id} name={d.name} />)}</div> : <Placeholder>Nothing</Placeholder>}</dd></>}
            <dt>As of</dt><dd>{asOf ? fmtDate(asOf) : "Today"}</dd>
          </dl>
        </section>
        {data.owner && (
          <section className="inspector-section">
            <span className="t-label">Owner</span>
            {ownerFacts.length ? (
              <div className="facts facts-host">
                {ownerFacts.map((it) => it.facts.map((f) => <FactRow key={f.assertion_id} fact={f} spans={it.spans} path={it.path} />))}
              </div>
            ) : <Placeholder>No owner recorded at this date.</Placeholder>}
          </section>
        )}
        {data.depended_on_by && (
          <section className="inspector-section">
            <span className="t-label">Depended on by</span>
            {(() => {
              const items = (data.depended_on_by?.items || []).filter((it): it is typeof it & { path: Path } => it.note !== "the system itself" && it.note !== "open dispute" && it.path !== null);
              if (!items.length) return <Placeholder>Nothing depends on it.</Placeholder>;
              return (
                <div className="facts">
                  {items.map((it) => (
                    <div key={it.item_id} className="fact" style={{ gridTemplateColumns: "minmax(0,1fr) auto" }}>
                      <div className="stmt" style={{ fontWeight: 400 }}>
                        {it.path.steps.map((st, i) => (
                          <span key={i} className="row" style={{ gap: 4 }}>
                            {i > 0 && <span className="text-3">←</span>}
                            {st.node.id.includes(":") ? <EntityLink id={st.node.id} name={st.node.name} /> : st.node.name}
                          </span>
                        ))}
                      </div>
                      <Chip tone="neutral">{it.path.steps.length - 1} {it.path.steps.length - 1 === 1 ? "hop" : "hops"}</Chip>
                    </div>
                  ))}
                </div>
              );
            })()}
          </section>
        )}
        {data.decisions && (
          <section className="inspector-section">
            <span className="t-label">Decisions</span>
            {data.decisions.items.length ? (
              <div className="stack-3">
                {data.decisions.items.map((it) => (
                  <div key={it.item_id} className="card-tight stack">
                    <div className="t-strong">{it.note}</div>
                    <div className="facts bare facts-host">
                      {it.facts.filter((f, i, arr) => arr.findIndex((x) => x.statement === f.statement) === i).map((f) => (
                        <FactRow key={f.assertion_id} fact={f} spans={it.spans} />
                      ))}
                    </div>
                    {it.spans.filter((sp) => sp.section).slice(0, 1).map((sp) => (
                      <div key={sp.span_id} className="t-small text-2 row" style={{ alignItems: "flex-start" }}>
                        <Quote className="icon-sm text-3" style={{ marginTop: 2 }} />
                        <span>{sp.text.slice(0, 200)}{sp.text.length > 200 ? "…" : ""}</span>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            ) : <Placeholder>No decisions affect it.</Placeholder>}
          </section>
        )}
        {!full && (
          <section className="inspector-section">
            <span className="t-label">Recent history</span>
            {historyEntries.length ? (
              <div className="facts facts-host">
                {historyEntries.flatMap(([pred, pack]) => pack.items.flatMap((it) => it.facts.map((f) => ({ pred, f, it }))))
                  .sort((a, b) => (b.f.recorded_at || b.f.valid_from) - (a.f.recorded_at || a.f.valid_from)).slice(0, 5)
                  .map(({ f, it, pred }) => <FactRow key={f.assertion_id} fact={f} spans={it.spans} extra={<Chip tone="neutral">{predicateLabel(pred)}</Chip>} />)}
              </div>
            ) : <Placeholder>No history recorded.</Placeholder>}
          </section>
        )}
      </div>
    </PackContext.Provider>
  );
}

export function EntityHistory({ data }: { data: EntityPanelData }) {
  const packs = packsOf(data);
  const entries = Object.entries(data.history || {});
  if (!entries.some(([, p]) => p.items.length)) return <Empty title="No history recorded">Nothing has been asserted about this entity yet.</Empty>;
  return (
    <PackContext.Provider value={{ packs, fromTurn: false }}>
      <div className="stack-6">
        {entries.map(([pred, pack]) => (
          <section key={pred} className="inspector-section">
            <span className="t-label">{predicateLabel(pred)}</span>
            {pack.items.length ? <HistoryTimeline pack={pack} /> : <Placeholder>Nothing recorded.</Placeholder>}
          </section>
        ))}
      </div>
    </PackContext.Provider>
  );
}

/** m11: a chat message reads "#ledger · Jonah Feld · 2 Oct 2026" rather than "#ledger message". */
function sourceTitle(kind: string, src: { id: string; title?: string; author?: string | null; at?: number | null }, names: NameMap): string {
  if (kind !== "chat" || !src.title) return src.title || src.id;
  const who = src.author ? names[src.author]?.name || src.author : "";
  return [src.title.replace(/ message$/, ""), who, src.at ? fmtDate(src.at) : ""].filter(Boolean).join(" · ");
}

export function EntitySources({ data }: { data: EntityPanelData }) {
  const { openEvidence } = useStore();
  const mode = useOpenMode();
  const names = useNames((data.sources || []).flatMap((g) => g.sources.map((x) => x.author || "")).filter(Boolean));
  if (!data.sources?.length) return <Empty title="No sources mention it" />;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead><tr><th>Title</th><th>Kind</th></tr></thead>
        <tbody>
          {data.sources.flatMap((g) => g.sources.map((src) => (
            <tr key={src.id} className="clickable" onClick={() => openEvidence({ tab: "source", sourceId: src.id, title: src.title }, mode)}>
              <td className="cell-primary wrap">{sourceTitle(g.kind, src, names)}</td>
              <td><Chip tone="neutral">{KIND_LABEL[g.kind] || g.kind}</Chip></td>
            </tr>
          )))}
        </tbody>
      </table>
    </div>
  );
}

export function EntityDisputes({ data, id }: { data: EntityPanelData; id: string }) {
  const packs = packsOf(data);
  const disputes = disputesOf(data, id);
  if (!disputes.length) return <Empty icon={Flag} title="No open disputes">Every recorded fact about this entity is unchallenged.</Empty>;
  return (
    <PackContext.Provider value={{ packs, fromTurn: false }}>
      <div className="stack-4">{disputes.map((g, i) => <DisputeBlock key={i} g={g} />)}</div>
    </PackContext.Provider>
  );
}

/** Inspector peek: summary with the tab row (DESIGN.md §4.4). */
export function EntityPeek({ id, tab, setTab }: { id: string; tab: string; setTab: (t: string) => void }) {
  const { data, error, reload } = useEntity(id);
  const disputes = disputesOf(data, id).length;
  return (
    <div className="inspector-body flush">
      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "overview", label: "Overview" },
          { id: "history", label: "History" },
          { id: "sources", label: "Sources", count: data?.sources?.reduce((n, g) => n + g.sources.length, 0) },
          { id: "disputes", label: "Disputes", count: disputes || undefined },
        ]}
      />
      <div style={{ padding: 16 }}>
        {error && <ErrorState message={error} onRetry={reload} />}
        {!data && !error && <div className="stack-3"><Skeleton w="40%" h={16} /><Skeleton h={36} /><Skeleton h={36} /><Skeleton h={36} /></div>}
        {data && tab === "overview" && <EntitySummary data={data} id={id} />}
        {data && tab === "history" && <EntityHistory data={data} />}
        {data && tab === "sources" && <EntitySources data={data} />}
        {data && tab === "disputes" && <EntityDisputes data={data} id={id} />}
      </div>
    </div>
  );
}
