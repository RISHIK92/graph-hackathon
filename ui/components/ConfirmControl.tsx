"use client";

import { Check, GitBranch, Undo2, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { get, qs, send } from "@/lib/api";
import { eligibilityLabel } from "@/lib/format";
import { useNames, useOpenMode, useStore } from "@/lib/store";
import type { ConfirmPreview, Eligible, Refusal, UndoPreview, WriteResult } from "@/lib/types";
import { EligibilityBadge } from "./Chips";
import { Button, Chip, Modal, Notice, Placeholder, Skeleton } from "./ui";

/** "Who can …" list: each with an eligibility rule, a "Why" (opens the Path tab) and a "Switch to" shortcut. */
export function WhoCan({ people, verb, compact }: { people: Eligible[]; verb: string; compact?: boolean }) {
  const { setActingAs, actingAs, openEvidence, toast } = useStore();
  const mode = useOpenMode();
  const ids = people.flatMap((p) => p.path.split(/\s+/).filter((t) => /^[a-z0-9-]+$/.test(t)));
  const names = useNames(ids);
  if (!people.length) return null;
  return (
    <div className="who">
      {!compact && <div className="t-label">Who can {verb}</div>}
      {people.map((p) => (
        <div key={`${p.person_id}-${p.rule}`} className="who-row">
          <UserRound className="icon-sm text-3" />
          <span className="name">{p.name}</span>
          <Chip tone="neutral">{eligibilityLabel(p.rule)}</Chip>
          {p.path && (
            <Button
              variant="link" size="sm" icon={GitBranch}
              onClick={() => openEvidence({ tab: "path", path: pathFromEligibility(p, names), title: `Why ${p.name} may ${verb}` }, mode)}
            >
              Why
            </Button>
          )}
          {p.person_id !== actingAs && (
            <Button size="sm" variant="ghost" className="right" onClick={async () => { await setActingAs(p.person_id); toast({ tone: "info", title: `Now acting as ${p.name}` }); }}>
              Switch to {p.name.split(" ")[0]}
            </Button>
          )}
        </div>
      ))}
    </div>
  );
}

/** The eligibility path string ("a −LEADS→ b …") as Path steps for the Path tab, with ids resolved to names. */
function pathFromEligibility(p: Eligible, names: Record<string, { id?: string; name: string; label: string }>) {
  const parts = p.path.split(/\s+(?=[a-z0-9-]+ −)/).filter(Boolean);
  const steps: { node: { id: string; labels: string[]; name: string }; edge: { type: string; aid: string; valid_from: null; valid_to: null } | null }[] = [];
  const node = (bare: string) => {
    const n = names[bare];
    return { id: n?.id || bare, labels: n ? [n.label] : [], name: n?.name || bare };
  };
  parts.forEach((seg, i) => {
    const m = seg.match(/^(\S+)\s+−(\w+)→\s+(\S+)/);
    if (!m) return;
    const aid = p.aids?.[i] || "";
    if (!steps.length || steps[steps.length - 1].node.name !== node(m[1]).name) {
      steps.push({ node: node(m[1]), edge: null });
    }
    steps.push({ node: node(m[3]), edge: { type: m[2], aid, valid_from: null, valid_to: null } });
  });
  return { path_id: p.path_id || `elig-${p.person_id}`, steps };
}

export function RefusalCard({ r }: { r: Refusal }) {
  const { openAction } = useStore();
  const m = r.reason.match(/\b(ac_[a-f0-9]+)\b/);
  return (
    <Notice
      tone="error"
      title="Refused"
      actions={m ? <Button size="sm" variant="link" onClick={() => openAction(m[1])}>Open that action</Button> : undefined}
    >
      <div>{r.reason}</div>
      {r.eligible?.length ? <div style={{ marginTop: 8 }}><WhoCan people={r.eligible} verb="do this" /></div> : null}
      {r.fallback_available && <div className="t-small" style={{ marginTop: 4 }}>Any team lead may confirm.</div>}
    </Notice>
  );
}

/** Undo an action straight from a toast or a success card (M7): one click, no preview step; the guard decides. */
export function useUndoNow() {
  const { session, actingAs, noteWrite, personName, toast } = useStore();
  return async (actionId: string, what?: string): Promise<boolean> => {
    if (!session) return false;
    try {
      const r = await send<WriteResult>("POST", `/actions/${encodeURIComponent(actionId)}/undo`, { session_id: session.id, request_id: crypto.randomUUID() });
      if (r.refusal) {
        toast({ tone: "error", title: "Undo refused", body: r.refusal.reason });
        return false;
      }
      noteWrite(`${personName(actingAs)} undid ${what || "an action"}`);
      toast({ tone: "success", title: "Undone", body: what });
      return true;
    } catch (e) {
      toast({ tone: "error", title: "Undo failed", body: String((e as Error).message || e) });
      return false;
    }
  };
}

function ResultCard({ res, verb, onUndo, onDismiss }: { res: WriteResult; verb: string; onUndo?: () => void; onDismiss?: () => void }) {
  const { openAction } = useStore();
  const ac = res.pack?.items?.[0]?.actions?.[0];
  return (
    <Notice
      tone="success"
      title={`${verb}${ac?.summary ? `: ${ac.summary}` : ""}`}
      actions={
        <>
          {ac?.eligibility && <EligibilityBadge e={ac.eligibility} />}
          {res.action_id && <Button size="sm" variant="link" onClick={() => openAction(res.action_id as string)}>View action</Button>}
          {onUndo && <Button size="sm" onClick={onUndo}>Undo</Button>}
          {onDismiss && <Button size="sm" variant="ghost" onClick={onDismiss}>Dismiss</Button>}
        </>
      }
    />
  );
}

/**
 * Confirm button, shown only when the read-only preview says admissible && actor_eligible (04 §2.1).
 * Otherwise the place shows who can confirm, the missing fact, or the admissibility reason.
 * Clicking opens a confirmation modal naming the consequence; success ends in a toast.
 */
export function ConfirmControl({ assertionId, actionId, label = "Confirm", what, compact, hideWho }: {
  assertionId?: string; actionId?: string; label?: string; what?: string; compact?: boolean; hideWho?: boolean;
}) {
  const { session, actingAs, version, noteWrite, personName, toast, openAction, setSessionSheetOpen } = useStore();
  const [pv, setPv] = useState<ConfirmPreview | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState<WriteResult | null>(null);
  const undoNow = useUndoNow();
  // The success card stays about 10 s, with Undo beside it, then gives way to the live state (M7)
  useEffect(() => {
    if (!result || result.refusal) return;
    const t = setTimeout(() => setResult(null), 10_000);
    return () => clearTimeout(t);
  }, [result]);
  const target = assertionId ? `/assertions/${encodeURIComponent(assertionId)}` : `/actions/${encodeURIComponent(actionId || "")}`;

  useEffect(() => {
    if (!session) return;
    let live = true;
    setErr("");
    get<ConfirmPreview>(`${target}/confirmers${qs({ session_id: session.id })}`)
      .then((p) => live && setPv(p))
      .catch((e) => live && setErr(String(e.message || e)));
    return () => { live = false; };
  }, [target, session, actingAs, version]);

  if (result) {
    if (result.refusal) return <RefusalCard r={result.refusal} />;
    const undoId = result.action_id;
    return <ResultCard res={result} verb="Confirmed" onDismiss={() => setResult(null)}
      onUndo={undoId ? async () => { if (await undoNow(undoId, what)) setResult(null); } : undefined} />;
  }
  if (err) return <Notice tone="error" title="Could not check who may confirm">{err}</Notice>;
  if (!pv || !session) return <Skeleton w={220} h={28} />;

  const click = async () => {
    setBusy(true);
    try {
      const r = await send<WriteResult>("POST", `${target}/confirm`, { session_id: session.id, request_id: pv.request_id });
      setResult(r);
      setOpen(false);
      if (!r.refusal) {
        noteWrite(`${personName(actingAs)} confirmed ${what || "a fact"}`);
        const undoId = r.action_id;
        toast({ tone: "success", title: "Confirmed", body: what, action: undoId ? { label: "Undo", onClick: () => { void undoNow(undoId, what).then((ok) => ok && setResult(null)); } } : undefined });
      } else {
        toast({ tone: "error", title: "The write guard refused", body: r.refusal.reason });
      }
    } catch (e) {
      const msg = String((e as Error).message || e);
      setResult({ refusal: { refused: true, reason: msg, eligible: [], fallback_available: false, action_id: "" } });
      setOpen(false);
      toast({ tone: "error", title: "Confirm failed", body: msg });
    } finally {
      setBusy(false);
    }
  };

  if (!pv.admissible) {
    const m = (pv.refusal || "").match(/\b(ac_[a-f0-9]+)\b/);
    return (
      <div className="row-wrap t-small text-2">
        <span>Not confirmable: {pv.refusal}</span>
        {m && <Button size="sm" variant="link" onClick={() => openAction(m[1])}>Open that action</Button>}
      </div>
    );
  }
  if (pv.actor_eligible) {
    return (
      <div className="row-wrap">
        {session.anonymous ? (
          <>
            <Button size="sm" variant="primary" icon={Check} disabled title="Writes are off in demo mode">{label}</Button>
            {!compact && <span className="t-small text-2">Writes are off in demo mode. <button className="link-btn" onClick={() => setSessionSheetOpen(true)}>Enable writes</button></span>}
          </>
        ) : (
          <Button size="sm" variant="primary" icon={Check} onClick={() => setOpen(true)}>{label}</Button>
        )}
        {pv.fallback && !compact && <EligibilityBadge e="fallback" />}
        {open && (
          <Modal
            title={label}
            onClose={() => setOpen(false)}
            busy={busy}
            footer={
              <>
                <Button onClick={() => setOpen(false)} disabled={busy}>Cancel</Button>
                <Button variant="primary" icon={Check} onClick={click} busy={busy}>{label}</Button>
              </>
            }
          >
            <div className="stack-3">
              {what && <div className="t-strong">{what}</div>}
              <div className="t-small text-2">
                This records a confirmation as the acting person. The confirmed statement becomes current from now, and any
                competing statement on the same subject is superseded or overruled. You can undo your own confirmation later.
              </div>
              <div className="row-wrap t-small">
                <span className="text-2">Eligibility:</span>
                <EligibilityBadge e={pv.fallback ? "fallback" : (pv.eligible.find((e) => e.person_id === actingAs)?.rule || "holder")} />
              </div>
            </div>
          </Modal>
        )}
      </div>
    );
  }
  if (pv.self_proposed) {
    const others = pv.eligible.filter((e) => e.person_id !== actingAs);
    return (
      <div className="stack">
        <div className="t-small text-2">You proposed this. Ask another decider to approve.</div>
        {!hideWho && others.length > 0 && <WhoCan people={others} verb="approve" compact />}
      </div>
    );
  }
  if (hideWho) return null;
  return (
    <div className="stack">
      {pv.fallback ? (
        <>
          <div className="t-small text-2">
            Nobody holds the confirmer rule{pv.missing_fact ? <> (missing fact: <em>{pv.missing_fact}</em>)</> : null}. <strong>Any team lead may confirm.</strong>
          </div>
          <details className="details">
            <summary>Team leads ({pv.eligible.length})</summary>
            <div className="details-body"><WhoCan people={pv.eligible} verb="confirm" compact /></div>
          </details>
        </>
      ) : (
        <WhoCan people={pv.eligible} verb="confirm" compact={compact} />
      )}
    </div>
  );
}

/** Undo button, shown only when the undo preview allows the acting person; otherwise names who can undo. */
export function UndoControl({ actionId, preview, requestId, onDone, what }: {
  actionId: string; preview: UndoPreview; requestId: string; onDone?: () => void; what?: string;
}) {
  const { session, actingAs, noteWrite, personName, toast, openAction, setSessionSheetOpen } = useStore();
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState<WriteResult | null>(null);
  if (result) return result.refusal ? <RefusalCard r={result.refusal} /> : <ResultCard res={result} verb="Undone" />;
  if (!preview.allowed) {
    return preview.reason && preview.undoers.length === 0 ? (
      <Placeholder>Undo unavailable: {preview.reason}</Placeholder>
    ) : (
      <WhoCan people={preview.undoers} verb="undo" />
    );
  }
  const click = async () => {
    if (!session) return;
    setBusy(true);
    try {
      const r = await send<WriteResult>("POST", `/actions/${encodeURIComponent(actionId)}/undo`, { session_id: session.id, request_id: requestId });
      setResult(r);
      setOpen(false);
      if (!r.refusal) {
        noteWrite(`${personName(actingAs)} undid ${what || "an action"}`);
        onDone?.();
        toast({ tone: "success", title: "Undone", body: what, action: r.action_id ? { label: "View undo action", onClick: () => openAction(r.action_id as string) } : undefined });
      } else {
        toast({ tone: "error", title: "The write guard refused", body: r.refusal.reason });
      }
    } catch (e) {
      const msg = String((e as Error).message || e);
      setResult({ refusal: { refused: true, reason: msg, eligible: [], fallback_available: false, action_id: "" } });
      setOpen(false);
      toast({ tone: "error", title: "Undo failed", body: msg });
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="row-wrap">
      {session?.anonymous ? (
        <>
          <Button size="sm" variant="danger" icon={Undo2} disabled>Undo</Button>
          <span className="t-small text-2">Writes are off in demo mode. <button className="link-btn" onClick={() => setSessionSheetOpen(true)}>Enable writes</button></span>
        </>
      ) : (
        <Button size="sm" variant="danger" icon={Undo2} onClick={() => setOpen(true)}>Undo</Button>
      )}
      {open && (
        <Modal
          title="Undo this action"
          onClose={() => setOpen(false)}
          busy={busy}
          footer={
            <>
              <Button onClick={() => setOpen(false)} disabled={busy}>Cancel</Button>
              <Button variant="danger-solid" icon={Undo2} onClick={click} busy={busy}>Undo</Button>
            </>
          }
        >
          <div className="stack-3">
            {what && <div className="t-strong">{what}</div>}
            <div className="t-small text-2">
              Undo retracts what this action produced and records an undo action with your name. Nothing is deleted: the
              history keeps both the action and its undo, and a withdrawn proposal stays visible as withdrawn.
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

/** Undo with its own preview fetch (inbox rows, action cards). */
export function UndoFetch({ actionId, what }: { actionId: string; what?: string }) {
  const { session, version } = useStore();
  const [d, setD] = useState<{ undo: UndoPreview; request_id: string } | null>(null);
  useEffect(() => {
    if (!session) return;
    get<{ undo: UndoPreview; request_id: string }>(`/actions/${encodeURIComponent(actionId)}${qs({ session_id: session.id })}`)
      .then(setD)
      .catch(() => setD(null));
  }, [actionId, session, version]);
  if (!d) return null;
  return <UndoControl actionId={actionId} preview={d.undo} requestId={d.request_id} what={what} />;
}
