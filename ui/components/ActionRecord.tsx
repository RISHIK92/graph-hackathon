"use client";

import { ArrowUpRight, FileText, Zap } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { qs } from "@/lib/api";
import { approvedText, fmtDateTime } from "@/lib/format";
import { actionKindLabel } from "@/lib/labels";
import { useApi, useOpenMode, useStore } from "@/lib/store";
import type { ActionSummary, ActionView, Fact, Pack } from "@/lib/types";
import { EligibilityBadge, FactRow, PackContext } from "./Chips";
import { ConfirmControl, UndoControl, WhoCan } from "./ConfirmControl";
import { Button, Chip, Details, ErrorState, Notice, Placeholder, Segmented, Skeleton, StatusChip } from "./ui";

export function useAction(id: string) {
  const { session } = useStore();
  return useApi<ActionView>(`/actions/${encodeURIComponent(id)}${qs({ session_id: session?.id })}`);
}

export function actionTitle(me?: ActionSummary): string {
  if (!me) return "Action";
  const k = actionKindLabel(me.kind);
  return me.summary ? `${k}: ${me.summary}` : k;
}

/** Action record (04 §2.6): relied-on and produced facts, who asked and who confirmed, the draft,
 * one Then / Now switch that flips the whole view, and Undo when the preview allows it. */
export function ActionRecord({ id, inPage }: { id: string; inPage?: boolean }) {
  const s = useStore();
  const mode = useOpenMode();
  const router = useRouter();
  const { data, error, reload } = useAction(id);
  const [when, setWhen] = useState<"then" | "now">("then");
  const item = data?.pack.items[0];
  const actions = (item?.actions || []) as ActionSummary[];
  const me = actions[0];
  const confirmers = actions.slice(1);
  const tn = item?.then_now;
  const changed = (item?.changed_since || []);
  const changedIds = changed.map((c) => c.assertion_id);
  const view = tn?.[when];
  const packs: Pack[] = data ? [data.pack] : [];
  const withdrawn = me?.status === "undone";
  // M20: a proposal is waiting until someone approves it; an undone action is "Undone"
  const nowProduced = tn?.now.produced || [];
  const proposal = me?.kind === "route_to_owner" || me?.kind === "draft_adr_supersession";
  const status = withdrawn ? "undone"
    : proposal && nowProduced.some((f) => f.confirmed_by) ? "approved"
      : proposal && nowProduced.some((f) => f.status === "proposed") ? "waiting" : me?.status || "done";
  const outcome = item?.confirmed;

  if (error) return <div style={{ padding: 16 }}><ErrorState message={error} onRetry={reload} /></div>;
  if (!data || !me) return <div style={{ padding: 16 }} className="stack-3"><Skeleton w="50%" h={16} /><Skeleton h={80} /><Skeleton h={36} /></div>;

  const produced = view?.produced || [];
  const basedOn = view?.based_on || [];
  const canConfirm = me.kind !== "confirm_fact" && produced.some((f) => f.status === "proposed" && !f.confirmed_by) && !withdrawn;

  return (
    <PackContext.Provider value={{ packs, fromTurn: false }}>
      <div className="stack-6" style={{ padding: inPage ? 0 : 16 }}>
        <div className="stack-3">
          <div className="row-wrap">
            <StatusChip status={status} />
            <Chip icon={Zap} tone="neutral">{actionKindLabel(me.kind)}</Chip>
            {!inPage && (
              <Button size="sm" variant="ghost" icon={ArrowUpRight} className="right" onClick={() => { s.closeInspector(); router.push(`/a/${encodeURIComponent(id)}`); }}>Open page</Button>
            )}
          </div>
          <dl className="kv">
            <dt>Summary</dt><dd>{me.summary}</dd>
            <dt>{me.kind === "confirm_fact" ? "Confirmed by" : "Requested by"}</dt>
            <dd className="row-wrap">{me.actor?.name}<EligibilityBadge e={me.eligibility} /></dd>
            <dt>When</dt><dd className="tnum">{fmtDateTime(me.recorded_at)}</dd>
            {confirmers.length > 0 && (
              <>
                <dt>Confirmations</dt>
                <dd className="stack">
                  {confirmers.map((c) => (
                    <span key={c.action_id} className="row-wrap">
                      {c.actor?.name} · <span className="tnum text-2">{fmtDateTime(c.recorded_at)}</span>
                      <EligibilityBadge e={c.eligibility} />
                      {c.status === "undone" && <StatusChip status="undone" />}
                      <Button size="sm" variant="link" onClick={() => s.openAction(c.action_id, mode)}>View</Button>
                    </span>
                  ))}
                </dd>
              </>
            )}
            {withdrawn && <><dt>Undone</dt><dd className="tnum">{fmtDateTime(me.undone_at)}</dd></>}
          </dl>
        </div>

        <div className="stack">
          <div className="row-wrap">
            <Segmented options={[{ id: "then", label: "Then" }, { id: "now", label: "Now" }]} value={when} onChange={setWhen} />
            <span className="t-small text-2">
              {when === "then" ? `What the brain believed when it acted, ${fmtDateTime(me.recorded_at)}.` : "What the brain believes now."}
            </span>
          </div>
          {when === "now" && changed.length > 0 && (
            <Notice tone="warning" title={`${changed.length} relied-on ${changed.length === 1 ? "fact has" : "facts have"} changed since`}>
              {changed.map((c) => <div key={c.assertion_id} className="t-small">{c.statement}: then <em>{c.then}</em>, now <em>{c.now}</em></div>)}
            </Notice>
          )}
        </div>

        {outcome ? (
          <section className="inspector-section">
            <span className="t-label">Made current</span>
            <div className="facts facts-host">{outcome.made_current.map((f) => <FactRow key={f.assertion_id} fact={f} spans={item?.spans} />)}</div>
            {outcome.replaced.length > 0 && <>
              <span className="t-label">Replaced</span>
              <div className="facts facts-host">{outcome.replaced.map((f) => <FactRow key={f.assertion_id} fact={f} spans={item?.spans} />)}</div>
            </>}
            {outcome.overruled.length > 0 && <>
              <span className="t-label">Overruled</span>
              <div className="facts facts-host">{outcome.overruled.map((f) => <FactRow key={f.assertion_id} fact={f} spans={item?.spans} />)}</div>
            </>}
          </section>
        ) : (
          <>
          <section className="inspector-section">
            <span className="t-label">Relied on</span>
            {basedOn.length ? (
              <div className="facts facts-host">
                {basedOn.map((f: Fact) => (
                  <FactRow key={f.assertion_id} fact={f} spans={item?.spans}
                    extra={changedIds.includes(f.assertion_id) && when === "now" ? <Chip tone="warning">Changed since</Chip> : undefined} />
                ))}
              </div>
            ) : <Placeholder>Nothing. {me.kind === "learn_fact" ? "The fact was learned from chat." : ""}</Placeholder>}
          </section>

          <section className="inspector-section">
            <span className="t-label">Produced</span>
            {produced.length ? (
              <div className="facts facts-host">{produced.map((f: Fact) => (
                <div key={f.assertion_id}>
                  <FactRow fact={f} spans={item?.spans} />
                  {f.confirmed_by && <div className="sub">{approvedText(f.confirmed_by)}</div>}
                </div>
              ))}</div>
            ) : <Placeholder>No new facts.</Placeholder>}
            {canConfirm && <ConfirmControl actionId={id} label="Confirm proposal" what={me.summary} />}
          </section>
          </>
        )}

        {data.draft_source && (
          <section className="inspector-section">
            <span className="t-label">Draft</span>
            <Notice tone="warning" title={`Agent draft${withdrawn ? " (undone)" : ""}`} actions={
              <Button size="sm" variant="link" icon={FileText} onClick={() => s.openEvidence({ tab: "source", sourceId: data.draft_source!, title: "Agent draft" }, mode)}>View the draft text</Button>
            }>Display only. A draft is never evidence and can never be cited.</Notice>
          </section>
        )}

        <section className="inspector-section">
          <span className="t-label">Undo</span>
          {withdrawn ? (
            <Placeholder>Undone {fmtDateTime(me.undone_at)}.</Placeholder>
          ) : data.undo.allowed ? (
            <UndoControl actionId={id} preview={data.undo} requestId={data.request_id} onDone={s.bump} what={me.summary} />
          ) : (
            <div className="stack">
              <Placeholder>{data.undo.reason || "You can't undo this action."}</Placeholder>
              {data.undo.undoers.length > 0 && <WhoCan people={data.undo.undoers} verb="undo" />}
            </div>
          )}
        </section>

        {s.debug && <Details summary="Raw pack (debug)"><pre className="debug">{JSON.stringify(data.pack, null, 1)}</pre></Details>}
      </div>
    </PackContext.Provider>
  );
}
