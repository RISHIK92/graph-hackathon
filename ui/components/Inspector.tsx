"use client";

import { ChevronLeft, ChevronRight, Flag, PanelRightClose, Quote } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { qs } from "@/lib/api";
import { labelOf } from "@/lib/format";
import { actionKindLabel, edgeVerb } from "@/lib/labels";
import { InInspector, useApi, useNames, useStore, type InspectorView } from "@/lib/store";
import type { ActionView, Fact, SpanItem } from "@/lib/types";
import { ActionRecord, useAction } from "./ActionRecord";
import { FactRow, PackContext } from "./Chips";
import { ConfirmControl, UndoFetch } from "./ConfirmControl";
import { EntityActions, EntityPeek, useEntity } from "./EntityPanel";
import EvidencePanel from "./EvidencePanel";
import { TraceView } from "./TraceView";
import { Button, Chip, ErrorState, Notice, Skeleton } from "./ui";

function viewTitle(v: InspectorView, names: Record<string, { name: string }>): string {
  switch (v.kind) {
    case "entity": return v.name || names[v.id]?.name || v.id.split(":").slice(1).join(":");
    case "evidence": return v.target.title ? `Evidence: ${v.target.title}` : "Evidence";
    case "action": return "Action";
    case "edge": return `${names[v.source]?.name || v.source} ${edgeVerb(v.type)} ${names[v.target]?.name || v.target}`;
    case "trace": return "How I answered";
    case "inbox": return v.summary;
  }
}

/** The single right panel (DESIGN.md §2.3): one level, breadcrumb inside, Escape closes, focus moves in and back. */
export default function Inspector() {
  const s = useStore();
  const stack = s.inspector;
  const top = stack[stack.length - 1];
  const panel = useRef<HTMLElement>(null);
  const [entityTab, setEntityTab] = useState("overview");
  const ids = stack.flatMap((v) => (v.kind === "entity" ? [v.id] : v.kind === "edge" ? [v.source, v.target] : []));
  const names = useNames(ids);

  useEffect(() => { setEntityTab(top && top.kind === "entity" && top.tab ? top.tab : "overview"); }, [top && top.kind === "entity" ? `${top.id}|${top.tab || ""}` : null]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!top) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !document.querySelector(".modal-overlay")) {
        const tag = (document.activeElement as HTMLElement)?.tagName;
        if (tag === "TEXTAREA" || tag === "INPUT") return;
        s.closeInspector();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [top, s]);

  if (!top) return null;
  const crumbs = stack.slice(0, -1);
  return (
    <InInspector.Provider value={true}>
    <aside className="inspector" role="complementary" aria-label="Inspector" ref={panel}>
      <div className="inspector-header">
        <div className="inspector-crumb">
          {crumbs.length ? (
            crumbs.map((v, i) => (
              <span key={i} className="row" style={{ gap: 4 }}>
                <button onClick={() => { for (let k = stack.length - 1; k > i; k--) s.popInspector(); }}>{viewTitle(v, names)}</button>
                <ChevronRight />
              </span>
            ))
          ) : (
            <span>{top.kind === "entity" ? "Entity" : top.kind === "evidence" ? "Evidence" : top.kind === "action" ? "Action record" : top.kind === "trace" ? "Proof" : top.kind === "edge" ? "Edge" : "Inbox item"}</span>
          )}
        </div>
        <div className="inspector-title-row">
          {crumbs.length > 0 && <Button variant="ghost" size="sm" icon={ChevronLeft} aria-label="Back" onClick={s.popInspector} />}
          <h2 className="t-heading truncate">{top.kind === "action" ? <ActionTitle id={top.id} /> : viewTitle(top, names)}</h2>
          {top.kind === "entity" && <EntityHeaderExtras id={top.id} />}
          <Button variant="ghost" size="sm" icon={PanelRightClose} aria-label="Close" onClick={s.closeInspector} />
        </div>
      </div>
      {top.kind === "entity" && <EntityPeek id={top.id} tab={entityTab} setTab={setEntityTab} />}
      {top.kind === "evidence" && <EvidencePanel target={top.target} />}
      {top.kind === "action" && <div className="inspector-body flush"><ActionRecord id={top.id} /></div>}
      {top.kind === "trace" && <TraceView turnId={top.turnId} path={top.path} spans={top.spans} tab={top.tab} />}
      {top.kind === "edge" && <EdgeView v={top} />}
      {top.kind === "inbox" && <InboxItemView v={top} />}
    </aside>
    </InInspector.Provider>
  );
}

function ActionTitle({ id }: { id: string }) {
  const { data } = useAction(id);
  const me = data?.pack.items[0]?.actions?.[0];
  return <>{me ? actionKindLabel(me.kind) : "Action"}</>;
}

function EntityHeaderExtras({ id }: { id: string }) {
  const { data } = useEntity(id);
  return (
    <>
      <Chip tone="neutral">{labelOf(data?.labels, id)}</Chip>
      <EntityActions data={data} id={id} />
    </>
  );
}

function EdgeView({ v }: { v: Extract<InspectorView, { kind: "edge" }> }) {
  const { asOf } = useStore();
  const path = v.edgeKind === "normal" ? `/edges/${encodeURIComponent(v.aid)}${qs({ as_of: asOf })}` : null;
  const { data, error, reload } = useApi<{ aid: string; facts: Fact[]; spans: SpanItem[] }>(path);
  return (
    <div className="inspector-body">
      {v.edgeKind === "stale" && (
        <Notice tone="warning" title="Stale document" >
          <span className="row" style={{ gap: 4 }}><Quote className="icon-sm" />“{v.label}”</span> still states this fact, but a later source replaced it. The graph shows the replacement; the document has not been updated.
        </Notice>
      )}
      {v.edgeKind === "disputed" && (
        <Notice tone="error" title="Open dispute">
          <span className="row" style={{ gap: 4 }}><Flag className="icon-sm" />A less reliable source disagrees with the recorded fact here.</span> Open either entity to see both sides and settle it.
        </Notice>
      )}
      {error && <ErrorState message={error} onRetry={reload} />}
      {path && !data && !error && <div className="stack"><Skeleton h={36} /><Skeleton h={36} /></div>}
      {data && (
        <PackContext.Provider value={{ packs: [], fromTurn: false }}>
          <section className="inspector-section">
            <span className="t-label">Facts on this edge</span>
            <div className="facts facts-host">{data.facts.map((f) => <FactRow key={f.assertion_id} fact={f} spans={data.spans} />)}</div>
          </section>
        </PackContext.Provider>
      )}
    </div>
  );
}

/** An inbox item opened for review: the proposal's record, or the disputed fact, with Confirm. */
function InboxItemView({ v }: { v: Extract<InspectorView, { kind: "inbox" }> }) {
  const { session } = useStore();
  const act = useApi<ActionView>(v.actionId ? `/actions/${encodeURIComponent(v.actionId)}${qs({ session_id: session?.id })}` : null);
  if (v.actionId) {
    return (
      <div className="inspector-body flush">
        <ActionRecord id={v.actionId} />
        {act.data && act.data.pack.items[0]?.actions?.[0]?.status !== "undone" && (
          <div style={{ padding: "0 16px 16px" }}><UndoFetch actionId={v.actionId} what={v.summary} /></div>
        )}
      </div>
    );
  }
  return (
    <div className="inspector-body">
      <Notice tone="error" title="Disputed fact">{v.summary}</Notice>
      {v.assertionId && <DisputedAssertion assertionId={v.assertionId} summary={v.summary} />}
    </div>
  );
}

function DisputedAssertion({ assertionId, summary }: { assertionId: string; summary: string }) {
  const { data, error, reload } = useApi<{ aid: string; facts: Fact[]; spans: SpanItem[] }>(`/edges/${encodeURIComponent(assertionId)}`);
  return (
    <div className="stack-4">
      {error && <ErrorState message={error} onRetry={reload} />}
      {!data && !error && <Skeleton h={36} />}
      {data && (
        <PackContext.Provider value={{ packs: [], fromTurn: false }}>
          <div className="facts facts-host">{data.facts.map((f) => <FactRow key={f.assertion_id} fact={f} spans={data.spans} />)}</div>
        </PackContext.Provider>
      )}
      <ConfirmControl assertionId={assertionId} label="Confirm this side" what={summary} />
    </div>
  );
}
