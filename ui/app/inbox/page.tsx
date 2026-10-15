"use client";

import { Check, ChevronRight, Flag, Inbox, Zap } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { EligibilityBadge } from "@/components/Chips";
import { ConfirmControl, UndoControl } from "@/components/ConfirmControl";
import { PageHeader } from "@/components/PageHeader";
import { Button, Chip, Empty, ErrorState, Notice, SkeletonRows, Status, Tabs } from "@/components/ui";
import { qs } from "@/lib/api";
import { fmtDateTime, plural } from "@/lib/format";
import { actionKindLabel } from "@/lib/labels";
import { useApi, useStore } from "@/lib/store";
import type { PendingData, UndoPreview } from "@/lib/types";

export default function InboxPage() {
  return <Suspense fallback={null}><InboxInner /></Suspense>;
}

function InboxInner() {
  const s = useStore();
  const router = useRouter();
  const params = useSearchParams();
  const tab = params.get("tab") || "awaiting";
  const setTab = (t: string) => router.replace(`/inbox${qs({ tab: t === "awaiting" ? "" : t })}`);
  const { data, error, loading, reload } = useApi<PendingData>(s.actingAs ? `/people/${encodeURIComponent(s.actingAs)}/pending` : null);
  const me = s.personName(s.actingAs);
  const anon = s.session?.anonymous;
  const selected = s.inspector[s.inspector.length - 1];
  const selKey = selected?.kind === "inbox" ? selected.actionId || selected.assertionId : selected?.kind === "action" ? selected.id : undefined;

  return (
    <div className="page">
      <PageHeader
        title="Inbox"
        description={`Items for ${me}: what awaits their confirmation, their open proposals, and their activity.`}
        asOf={false}
        tabs={<Tabs value={tab} onChange={setTab} tabs={[
          { id: "awaiting", label: "Awaiting you", count: data?.awaiting.length },
          { id: "mine", label: "Your proposals", count: data?.mine.length },
          { id: "activity", label: "Activity", count: data?.log.length },
        ]} />}
      />
      <div className="page-body">
        {anon && (
          <Notice tone="warning" title="Writes are off in demo mode" actions={<Button size="sm" onClick={() => s.setSessionSheetOpen(true)}>Enable writes</Button>}>
            You can review every item. Confirm and Undo need the write token.
          </Notice>
        )}
        {error && <ErrorState message={error} onRetry={reload} />}
        {!data && !error && <div className="table-wrap"><SkeletonRows n={4} cols={[50, 15, 15]} /></div>}
        {data && tab === "awaiting" && (
          data.awaiting.length ? (
            <div className="table-wrap" aria-busy={loading}>
              <table className="table">
                <thead><tr><th>Item</th><th>Type</th><th>Eligibility</th><th style={{ width: 240 }}>Decision</th><th style={{ width: 32 }} /></tr></thead>
                <tbody>
                  {data.awaiting.map((a) => {
                    const key = a.action_id || a.assertion_id || a.summary;
                    return (
                      <tr key={key} className={`clickable ${selKey === (a.action_id || a.assertion_id) ? "selected" : ""}`} onClick={() => s.openInspector({ kind: "inbox", actionId: a.action_id, assertionId: a.assertion_id, summary: a.summary })}>
                        <td className="wrap"><span className="row" style={{ gap: 8 }}>{a.type === "dispute" ? <Flag className="icon-sm text-warning" /> : <Zap className="icon-sm text-2" />}<span className="cell-primary">{a.summary}</span></span>
                          {a.fallback && a.missing_fact && <div className="t-small text-3">{a.missing_fact}, so any team lead may settle it.</div>}</td>
                        <td><Chip tone={a.type === "dispute" ? "error" : "accent"}>{a.type === "dispute" ? "Dispute" : actionKindLabel(a.kind)}</Chip></td>
                        <td><EligibilityBadge e={a.fallback ? "fallback" : "holder"} /></td>
                        <td onClick={(e) => e.stopPropagation()}>
                          <ConfirmControl actionId={a.action_id} assertionId={a.assertion_id} label={a.type === "dispute" ? "Confirm the challenger" : "Confirm proposal"} what={a.summary} hideWho compact />
                        </td>
                        <td><ChevronRight className="icon-sm chev" /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="table-wrap"><Empty icon={Check} title="You're all caught up">Approvals and disagreements that need you will appear here.</Empty></div>
          )
        )}
        {data && tab === "mine" && (
          data.mine.length ? (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Proposal</th><th>Kind</th><th style={{ width: 200 }}>Withdraw</th><th style={{ width: 32 }} /></tr></thead>
                <tbody>
                  {data.mine.map((m) => (
                    <tr key={m.action_id} className={`clickable ${selKey === m.action_id ? "selected" : ""}`} onClick={() => s.openAction(m.action_id)}>
                      <td className="wrap cell-primary">{m.summary}</td>
                      <td><Chip tone="neutral">{actionKindLabel(m.kind)}</Chip></td>
                      <td onClick={(e) => e.stopPropagation()}><MineUndo actionId={m.action_id} what={m.summary} /></td>
                      <td><ChevronRight className="icon-sm chev" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="t-small text-3" style={{ padding: "8px 16px" }}>A lead cannot decline a proposal; only the requester can withdraw it.</div>
            </div>
          ) : (
            <div className="table-wrap"><Empty icon={Inbox} title="No open proposals">Routing a ticket or drafting an ADR from Ask creates a proposal here.</Empty></div>
          )
        )}
        {data && tab === "activity" && (
          data.log.length ? (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Action</th><th>Kind</th><th>Status</th><th className="num">When</th><th style={{ width: 32 }} /></tr></thead>
                <tbody>
                  {data.log.map((l) => (
                    <tr key={l.id} className={`clickable ${selKey === l.id ? "selected" : ""}`} onClick={() => s.openAction(l.id)}>
                      <td className="wrap cell-primary">{l.summary}</td>
                      <td><Chip tone="neutral">{actionKindLabel(l.kind)}</Chip></td>
                      <td><Status status={l.status === "undone" ? "withdrawn" : l.status === "refused" ? "refused" : "done"} /></td>
                      <td className="num cell-mono">{fmtDateTime(l.at)}</td>
                      <td><ChevronRight className="icon-sm chev" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="table-wrap"><Empty icon={Zap} title="No activity yet">{me} has not confirmed, routed, recorded or undone anything.</Empty></div>
          )
        )}
        {data && <div className="t-small text-3">{plural(data.awaiting.length, "item")} awaiting · {plural(data.mine.length, "open proposal")} · {plural(data.log.length, "action")} logged</div>}
      </div>
    </div>
  );
}

function MineUndo({ actionId, what }: { actionId: string; what: string }) {
  const { session } = useStore();
  const { data: d } = useApi<{ undo: UndoPreview; request_id: string }>(session ? `/actions/${encodeURIComponent(actionId)}${qs({ session_id: session.id })}` : null);
  if (!d) return <span className="t-small text-3">Checking…</span>;
  return <UndoControl actionId={actionId} preview={d.undo} requestId={d.request_id} what={what} />;
}
