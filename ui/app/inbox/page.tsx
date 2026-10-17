"use client";

import { Check, ChevronRight, Flag, Inbox, Zap } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ConfirmControl, UndoControl } from "@/components/ConfirmControl";
import { PageHeader } from "@/components/PageHeader";
import { Button, Chip, Empty, ErrorState, Notice, SkeletonRows, Status, Tabs } from "@/components/ui";
import { qs } from "@/lib/api";
import { fmtDateTime, plural } from "@/lib/format";
import { actionKindLabel } from "@/lib/labels";
import { useApi, useNames, useStore } from "@/lib/store";
import type { ConfirmPreview, Directory, PendingData, PendingItem, UndoPreview } from "@/lib/types";

export default function InboxPage() {
  return <Suspense fallback={null}><InboxInner /></Suspense>;
}

function InboxInner() {
  const s = useStore();
  const router = useRouter();
  const params = useSearchParams();
  const tab = params.get("tab") || "awaiting";
  const setTab = (t: string) => router.replace(`/inbox${qs({ tab: t === "awaiting" ? "" : t })}`);
  const { data, error, reload } = useApi<PendingData>(s.actingAs ? `/people/${encodeURIComponent(s.actingAs)}/pending` : null);
  // Every open disagreement, not only the ones this person can settle, from the Directory's own call
  const dir = useApi<Directory>(tab === "disputes" ? `/directory${qs({ as_of: s.asOf })}` : null);
  const allDisputes = dir.data ? [...dir.data.systems, ...dir.data.projects, ...dir.data.people, ...dir.data.tickets, ...dir.data.decisions].filter((x) => x.disputed) : [];
  const me = s.personName(s.actingAs);
  const anon = s.session?.anonymous;
  const selected = s.inspector[s.inspector.length - 1];
  const selKey = selected?.kind === "inbox" ? selected.actionId || selected.assertionId : selected?.kind === "action" ? selected.id : undefined;

  return (
    <div className="page">
      <PageHeader
        title="Inbox"
        description={`What ${me} can settle. The graph decides who is eligible, and every decision can be undone.`}
        asOf={false}
        tabs={<Tabs value={tab} onChange={setTab} tabs={[
          { id: "awaiting", label: "Awaiting you", count: data?.awaiting.length },
          { id: "mine", label: "Your proposals", count: data?.mine.length },
          { id: "activity", label: "Activity", count: data?.log.length },
          { id: "disputes", label: "All open disputes", count: dir.data ? allDisputes.length : undefined },
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
          data.awaiting.length ? <Awaiting items={data.awaiting} /> : (
            <div className="table-wrap"><Empty icon={Check} title="You're all caught up">Approvals and disagreements that need {me} will appear here.</Empty></div>
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
        {tab === "disputes" && (
          dir.error ? <ErrorState message={dir.error} onRetry={dir.reload} /> : !dir.data ? <SkeletonRows n={4} /> : allDisputes.length ? (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Disputed</th><th>Settle it from</th></tr></thead>
                <tbody>
                  {allDisputes.map((x) => (
                    <tr key={x.id} className="clickable" onClick={() => s.openEntity(x.id, x.name)}>
                      <td className="cell-primary"><span className="row" style={{ gap: 8 }}><Flag className="icon-sm text-warning" />{x.name}</span></td>
                      <td className="t-small text-2">Its panel shows both sides and who can settle it</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <div className="table-wrap"><Empty icon={Check} title="No open disputes">Every recorded fact is unchallenged.</Empty></div>
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

/** Awaiting you (design brief step 4): a list, and the selected item beside it with the record and the
 * challenger, why this person can settle it (their path in the graph), and what confirming changes. */
function Awaiting({ items }: { items: PendingItem[] }) {
  const [sel, setSel] = useState(0);
  const i = Math.min(sel, items.length - 1);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || e.metaKey || e.ctrlKey) return;
      if (e.key === "j") setSel((x) => Math.min(x + 1, items.length - 1));
      if (e.key === "k") setSel((x) => Math.max(x - 1, 0));
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [items.length]);
  return (
    <div className="inbox-split">
      <div className="inbox-list" role="listbox" aria-label="Awaiting you">
        {items.map((a, k) => (
          <button key={a.action_id || a.assertion_id || a.summary} type="button" role="option" aria-selected={k === i}
            className={`inbox-item ${k === i ? "sel" : ""}`} onClick={() => setSel(k)}>
            <span className={`inbox-tag ${a.type === "dispute" ? "disp" : ""}`}>{a.type === "dispute" ? "DISPUTE" : actionKindLabel(a.kind).toUpperCase()}</span>
            <span className="t-strong">{a.type === "dispute" && a.challenger ? `${a.challenger}?` : a.summary}</span>
            {a.fallback && a.missing_fact ? <span className="t-small text-3">{a.missing_fact}, so any team lead may settle it.</span> : null}
          </button>
        ))}
        <div className="inbox-keys"><kbd>j</kbd> <kbd>k</kbd> move</div>
      </div>
      <InboxDetail key={items[i].action_id || items[i].assertion_id} a={items[i]} />
    </div>
  );
}

function InboxDetail({ a }: { a: PendingItem }) {
  const { session, actingAs } = useStore();
  const target = a.action_id ? `/actions/${encodeURIComponent(a.action_id)}` : `/assertions/${encodeURIComponent(a.assertion_id || "")}`;
  const { data: pv } = useApi<ConfirmPreview>(session ? `${target}/confirmers${qs({ session_id: session.id })}` : null);
  const mine = pv?.eligible.find((e) => e.person_id === actingAs);
  const dispute = a.type === "dispute";
  const changes = dispute
    ? [{ t: `+ ${a.challenger || "the challenger"}, from now`, c: "add" }, { t: `~ ${a.recorded || "the recorded fact"}, closed now`, c: "close" }]
    : [{ t: `+ ${a.summary}`, c: "add" }];
  return (
    <section className="inbox-detail nx-rise">
      <div className="stack" style={{ gap: 6 }}>
        <span className={`inbox-tag ${dispute ? "disp" : ""}`}>{dispute ? "DISPUTE" : actionKindLabel(a.kind).toUpperCase()}</span>
        <h2>{dispute && a.challenger ? `${a.challenger}?` : a.summary}</h2>
      </div>
      {dispute ? (
        <div className="inbox-sides">
          <div><span className="lab">CURRENT RECORD</span><span>{a.recorded}</span></div>
          <div className="challenger"><span className="lab">CHALLENGER</span><span>{a.challenger}</span></div>
        </div>
      ) : null}
      <div className="stack" style={{ gap: 8 }}>
        <span className="t-strong t-small">Why you can settle this</span>
        <div className="inbox-why">
          {mine ? <EligibilityPath path={mine.path} /> : <span className="text-3">Checking…</span>}
          {mine && <span className="rule">{mine.rule.startsWith("fallback") ? "Any team lead (no owner with a lead)" : "The graph's rule for this fact"}</span>}
        </div>
      </div>
      <div className="stack" style={{ gap: 8 }}>
        <span className="t-strong t-small">What confirming changes</span>
        <div className="inbox-changes">{changes.map((x) => <span key={x.t} className={x.c}>{x.t}</span>)}</div>
      </div>
      <div className="row-wrap" style={{ gap: 10 }}>
        <ConfirmControl actionId={a.action_id} assertionId={a.assertion_id} label={dispute ? "Confirm the challenger" : "Confirm proposal"} what={a.summary} hideWho />
        <span className="t-small text-3">You can undo it from the toast or from Activity.</span>
      </div>
    </section>
  );
}

/** "bob-lindqvist −LEADS→ infra" as names and relations. */
function EligibilityPath({ path }: { path: string }) {
  const tokens = path.split(/\s+/).filter(Boolean);
  const ids = tokens.filter((x) => /^[a-z0-9-]+$/.test(x));
  const names = useNames(ids);
  return (
    <span className="row-wrap" style={{ gap: 8 }}>
      {tokens.map((x, k) => /^[a-z0-9-]+$/.test(x)
        ? <span key={k} className="e-per">{names[x]?.name || x.replace(/-/g, " ")}</span>
        : <span key={k} className="rel">{x.replace(/[−→]/g, "")}</span>)}
    </span>
  );
}

function MineUndo({ actionId, what }: { actionId: string; what: string }) {
  const { session } = useStore();
  const { data: d } = useApi<{ undo: UndoPreview; request_id: string }>(session ? `/actions/${encodeURIComponent(actionId)}${qs({ session_id: session.id })}` : null);
  if (!d) return <span className="t-small text-3">Checking…</span>;
  return <UndoControl actionId={actionId} preview={d.undo} requestId={d.request_id} what={what} />;
}
