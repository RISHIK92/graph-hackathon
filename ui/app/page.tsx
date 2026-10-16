"use client";

import { Flag, MessageSquare } from "lucide-react";
import { useRouter } from "next/navigation";
import { PageHeader } from "@/components/PageHeader";
import { CitationChip } from "@/components/Chips";
import { Chip, DisputeFlag, EntityLink, ErrorState, SkeletonRows, Status } from "@/components/ui";
import { qs } from "@/lib/api";
import { fmtDate, plural } from "@/lib/format";
import { useApi, useStore } from "@/lib/store";
import type { Directory, Pack } from "@/lib/types";

const EXAMPLES = ["Who owns Ledger?", "Why is Ledger on Aurora?", "What breaks if Ledger goes down, and who do I tell?"];

/** Overview (M15): what this is, three questions to try, who owns what, recent decisions and open disputes,
 * all from the Directory's own call. */
export default function OverviewPage() {
  const s = useStore();
  const router = useRouter();
  const { data, error, loading, reload } = useApi<Directory>(`/directory${qs({ as_of: s.asOf })}`);
  const gaps = useApi<Pack>(`/gaps${qs({ as_of: s.asOf })}`);
  const gapItems = (gaps.data?.items || []).filter((it) => it.aggregate);
  const disputed = (data?.systems || []).filter((x) => x.disputed);
  const recent = [...(data?.decisions || [])].filter((d) => d.decided_at).sort((a, b) => (b.decided_at || 0) - (a.decided_at || 0)).slice(0, 4);
  return (
    <div className="page">
      <PageHeader title="Overview" description="Ask who owns what, why a decision was made, or what breaks if something goes down. Every answer shows where it came from." />
      <div className="page-body stack-6">
        <section className="stack-3">
          <span className="t-label">Try asking</span>
          <div className="row-wrap">
            {EXAMPLES.map((q) => (
              <button key={q} className="suggest" onClick={() => router.push(`/ask${qs({ q, send: "1" })}`)}><MessageSquare />{q}</button>
            ))}
          </div>
        </section>
        {error ? <ErrorState message={error} onRetry={reload} /> : loading && !data ? <SkeletonRows n={6} /> : data && (
          <>
            <section className="stack-3">
              <span className="t-label">Teams and what they own</span>
              <div className="overview-grid">
                {data.teams.map((t) => (
                  <div key={t.id} className="card-tight stack">
                    <EntityLink id={t.id} name={t.name} className="t-strong" />
                    <span className="t-small text-2">{t.leads.length ? <>Led by {t.leads.map((l) => <EntityLink key={l.id} id={l.id} name={l.name} />)}</> : "No current lead"}</span>
                    <div className="row-wrap">
                      {t.owns.length ? t.owns.map((x) => (
                        <span key={x.id} className="row" style={{ gap: 4 }}><EntityLink id={x.id} name={x.name} />{x.disputed && <DisputeFlag title="Ownership is disputed" />}</span>
                      )) : <span className="t-small text-3">Owns nothing yet</span>}
                    </div>
                  </div>
                ))}
              </div>
            </section>
            <section className="stack-3">
              <span className="t-label">Open disputes ({disputed.length})</span>
              {disputed.length ? (
                <div className="stack">
                  {disputed.map((x) => (
                    <div key={x.id} className="row" style={{ gap: 8 }}>
                      <Flag className="icon-sm text-warning" /><EntityLink id={x.id} name={x.name} />
                      <span className="t-small text-2">{x.owner ? `recorded owner ${x.owner.name}; another source disagrees` : "another source disagrees"}</span>
                    </div>
                  ))}
                </div>
              ) : <span className="t-small text-2">No open disputes.</span>}
            </section>
            <section className="stack-3">
              <span className="t-label">Knowledge gaps</span>
              {gaps.error ? <span className="t-small text-2">Couldn&apos;t check for gaps.</span> : !gaps.data ? <SkeletonRows n={2} /> : gapItems.some((it) => it.aggregate?.count) ? (
                <div className="stack">
                  {gapItems.filter((it) => it.aggregate?.count).map((it) => (
                    <div key={it.item_id} className="row-wrap">
                      <span>{it.aggregate?.text.split(":")[0]}:</span>
                      {it.aggregate?.members.map((m) => <EntityLink key={m.id} id={m.id} name={m.name} />)}
                      {it.spans.slice(0, 3).map((sp) => <CitationChip key={sp.span_id} span={sp} />)}
                    </div>
                  ))}
                </div>
              ) : <span className="t-small text-2">Every system has an owner with a lead, and every team has a lead.</span>}
            </section>
            <section className="stack-3">
              <span className="t-label">Recent decisions</span>
              <div className="stack">
                {recent.map((d) => (
                  <div key={d.id} className="row-wrap">
                    <EntityLink id={d.id} name={d.name} /><span>{d.title}</span>
                    <span className="t-small text-2 tnum">{fmtDate(d.decided_at)}</span>
                    {d.status && <Status status={d.status} />}
                    {d.replaces.length > 0 && <Chip tone="neutral">replaces {d.replaces.map((r) => r.name).join(", ")}</Chip>}
                  </div>
                ))}
              </div>
              <span className="t-small text-3">{plural(data.decisions.length, "decision")} in all; see the Directory for every team, system and person.</span>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
