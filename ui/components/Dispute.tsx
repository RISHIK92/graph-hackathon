"use client";

import { Flag } from "lucide-react";
import { useEffect, useState } from "react";
import { get, qs } from "@/lib/api";
import { predicateLabel } from "@/lib/labels";
import { useStore } from "@/lib/store";
import type { ConfirmPreview, Fact, Pack, SpanItem } from "@/lib/types";
import { FactRow } from "./Chips";
import { ConfirmControl, WhoCan } from "./ConfirmControl";
import { Notice } from "./ui";

export interface DisputeGroup {
  recorded: Fact | null;
  recordedSpans: SpanItem[];
  challengers: { fact: Fact; spans: SpanItem[] }[];
}

/** Open disputes (D5) found in packs: the recorded side (current with open_disputes) and each challenger. */
export function collectDisputes(packs: Pack[], onlyAssertions?: Set<string>): DisputeGroup[] {
  const facts = new Map<string, { fact: Fact; spans: SpanItem[] }>();
  for (const p of packs) {
    for (const it of p.items || []) {
      for (const f of it.facts || []) {
        const prev = facts.get(f.assertion_id);
        const spans = (it.spans || []).filter((s) => s.cites?.includes(f.assertion_id));
        if (!prev || (!prev.spans.length && spans.length)) facts.set(f.assertion_id, { fact: f, spans });
      }
    }
  }
  const groups: DisputeGroup[] = [];
  const used = new Set<string>();
  for (const { fact, spans } of facts.values()) {
    if (fact.status !== "current" || !fact.open_disputes?.length) continue;
    if (onlyAssertions && !onlyAssertions.has(fact.assertion_id) && !fact.open_disputes.some((d) => onlyAssertions.has(d))) continue;
    if (used.has(fact.run_id)) continue;
    used.add(fact.run_id);
    groups.push({
      recorded: fact,
      recordedSpans: spans,
      challengers: fact.open_disputes.map((d) => facts.get(d)).filter(Boolean) as { fact: Fact; spans: SpanItem[] }[],
    });
    fact.open_disputes.forEach((d) => used.add(d));
  }
  // disputed facts whose recorded side is not in these packs (e.g. a history pack)
  for (const { fact, spans } of facts.values()) {
    if (fact.status !== "disputed" || fact.overruled_by || used.has(fact.assertion_id)) continue;
    if (onlyAssertions && !onlyAssertions.has(fact.assertion_id)) continue;
    used.add(fact.assertion_id);
    groups.push({ recorded: null, recordedSpans: [], challengers: [{ fact, spans }] });
  }
  return groups;
}

export function disputeTitle(g: DisputeGroup): string {
  const f = g.recorded || g.challengers[0]?.fact;
  return f ? `Dispute on ${predicateLabel(f.predicate).toLowerCase()}` : "Open dispute";
}

/** Full dispute block: recorded vs challenger, sources on each side, one who-can list, Confirm on each side. */
export function DisputeBlock({ g }: { g: DisputeGroup }) {
  const { session, actingAs, version } = useStore();
  const [pv, setPv] = useState<ConfirmPreview | null>(null);
  const anchor = g.recorded?.assertion_id || g.challengers[0]?.fact.assertion_id;
  useEffect(() => {
    if (!session || !anchor) return;
    let live = true;
    get<ConfirmPreview>(`/assertions/${encodeURIComponent(anchor)}/confirmers${qs({ session_id: session.id })}`)
      .then((p) => live && setPv(p)).catch(() => undefined);
    return () => { live = false; };
  }, [anchor, session, actingAs, version]);
  const eligibleMe = !!pv?.admissible && !!pv?.actor_eligible;
  return (
    <div className="action-card">
      <div className="head">
        <Flag className="text-warning" />
        <span className="t-strong">{disputeTitle(g)}</span>
        <span className="hint">A lower-ranked source challenges the recorded fact. Whoever holds it may settle it.</span>
      </div>
      <div className="body">
        {g.recorded && (
          <div className="stack">
            <span className="t-label">Recorded</span>
            <div className="facts facts-host"><FactRow fact={g.recorded} spans={g.recordedSpans} /></div>
            <ConfirmControl assertionId={g.recorded.assertion_id} label="Confirm the recorded side" what={g.recorded.statement} hideWho />
          </div>
        )}
        {g.challengers.map((c) => (
          <div key={c.fact.assertion_id} className="stack">
            <span className="t-label">Challenger</span>
            <div className="facts facts-host"><FactRow fact={c.fact} spans={c.spans} /></div>
            <ConfirmControl assertionId={c.fact.assertion_id} label="Confirm the challenger" what={c.fact.statement} hideWho />
          </div>
        ))}
        {pv && !eligibleMe && (
          pv.admissible ? (
            pv.fallback ? (
              <Notice tone="warning" title="Nobody holds the confirmer rule">
                {pv.missing_fact ? <>Missing fact: <em>{pv.missing_fact}</em>. </> : null}Any team lead may confirm.
                <div style={{ marginTop: 8 }}><WhoCan people={pv.eligible} verb="settle" compact /></div>
              </Notice>
            ) : (
              <WhoCan people={pv.eligible} verb="settle this dispute" />
            )
          ) : (
            <div className="t-small text-2">Not confirmable: {pv.refusal}</div>
          )
        )}
      </div>
    </div>
  );
}

/** Collapsed one-line dispute notice for conversation turns: opens the full block in the inspector. */
export function DisputeLine({ g, onOpen }: { g: DisputeGroup; onOpen: () => void }) {
  const f = g.recorded || g.challengers[0]?.fact;
  return (
    <Notice tone="warning" title={`Needs review · ${disputeTitle(g)}`} actions={<button className="link-btn t-small" onClick={onOpen}>View and settle</button>}>
      {f ? <span className="t-small">{g.recorded ? `Recorded: ${g.recorded.statement}` : f.statement}{g.challengers[0] && g.recorded ? ` · Challenger: ${g.challengers[0].fact.statement}` : ""}</span> : null}
    </Notice>
  );
}
