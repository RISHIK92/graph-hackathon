"use client";

import { Clock, ExternalLink, FileText, Flag, GitBranch, History, Key, MoreHorizontal, Quote, Zap } from "lucide-react";
import { createContext, useContext, useState } from "react";
import { factStatus, fmtInterval, spansFor } from "@/lib/format";
import { displayText, eligibilityLabel, KIND_LABEL, sourceSuffix } from "@/lib/labels";
import { useOpenMode, useStore } from "@/lib/store";
import type { Fact, Pack, Path, SpanItem } from "@/lib/types";
import { Chip, Popover, Status } from "./ui";

/** The packs a citation sits in, so the evidence panel can show edge status and evidence. */
export const PackContext = createContext<{ packs: Pack[]; fromTurn: boolean }>({ packs: [], fromTurn: false });

export function EligibilityBadge({ e }: { e?: string | null }) {
  if (!e) return null;
  const fallback = e.startsWith("fallback");
  return (
    <Chip tone={fallback ? "warning" : "neutral"} icon={Key} title="Eligibility rule recorded on the confirmation">
      {eligibilityLabel(e)}
    </Chip>
  );
}

export function ActionChip({ actionId, label }: { actionId: string; label?: string }) {
  const { openAction } = useStore();
  const mode = useOpenMode();
  return (
    <Chip icon={Zap} onClick={() => openAction(actionId, mode)} title="Open the action record">
      {label || "Action"}
    </Chip>
  );
}

/** A citation chip keyed by span_id: quote icon + source kind, neutral. Class is a suffix, not a colour. */
export function CitationChip({ span, spanId, label = "graph", path, timeline }: {
  span?: SpanItem | null; spanId?: string; label?: string; path?: Path | null;
  timeline?: { entityId: string; predicate: string } | null;
}) {
  const { openEvidence } = useStore();
  const mode = useOpenMode();
  const pc = useContext(PackContext);
  const id = span?.span_id || spanId;
  if (!id) return <Chip dashed title="The verifier could not resolve this citation">Unresolved</Chip>;
  const kind = span?.kind ? KIND_LABEL[span.kind] || span.kind : "Source";
  const old = !!span && !span.live;
  return (
    <Chip
      icon={Quote}
      dashed={label !== "graph" && label !== "text_only"}
      title={`${span?.title || id}${old ? " (not in the latest revision)" : ""}. Open the source.`}
      onClick={() =>
        openEvidence({
          tab: "source", spanId: id, sourceId: span?.source_id,
          quote: { start: span?.quote_start, end: span?.quote_end },
          path: path || null, timeline: timeline || null, title: span?.title, packs: pc.packs, fromTurn: pc.fromTurn,
        }, mode)
      }
    >
      {kind}{sourceSuffix(label, !old)}
    </Chip>
  );
}

export function timelineKey(f: Fact): { entityId: string; predicate: string } {
  // chains are keyed on the object for OWNS/LEADS and on the subject otherwise; history accepts either end
  const ent = ["OWNS", "LEADS", "AFFECTS"].includes(f.predicate) && f.object_id ? f.object_id : f.subject_id;
  return { entityId: ent, predicate: f.predicate };
}

/** Strip a leading negation the statement already carries, then render one "Not:" marker. */
function statementParts(f: Fact): { negated: boolean; text: string } {
  const m = f.statement.match(/^\s*NOT[:\s]+(.*)$/i);
  if (m) return { negated: true, text: m[1] };
  return { negated: !!f.negated, text: f.statement };
}

/**
 * The atom of the product (DESIGN.md §3.6): fixed columns, never flex-wrap.
 * statement | status | interval | citations | overflow
 */
export function FactRow({ fact, spans, label = "graph", path, showInterval = true, selected, onSelect, extra, asOf }: {
  fact: Fact; spans?: SpanItem[]; label?: string; path?: Path | null; showInterval?: boolean;
  selected?: boolean; onSelect?: () => void; extra?: React.ReactNode; asOf?: number | null;
}) {
  const store = useStore();
  const { openEvidence, openAction } = useStore();
  const mode = useOpenMode();
  const pc = useContext(PackContext);
  const st = factStatus(fact, asOf === undefined ? store.asOf : asOf);
  const mine = spansFor(spans, fact.assertion_id);
  const tl = timelineKey(fact);
  const { negated, text } = statementParts(fact);
  const disputed = !!fact.open_disputes?.length;
  const first = mine[0];
  return (
    <div
      className={`fact ${onSelect ? "clickable" : ""} ${selected ? "selected" : ""}`}
      onClick={onSelect}
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
      onKeyDown={onSelect ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(); } } : undefined}
    >
      <div className="stmt">
        {negated && <span className="neg">Not:</span>}
        <span>{displayText(text)}</span>
        {disputed && (
          <Chip tone="warning" icon={Flag} title="This fact has an open dispute">Disputed</Chip>
        )}
        {extra}
      </div>
      <div className="status-col"><Status status={st} /></div>
      {showInterval ? <span className="when">{fmtInterval(fact.valid_from, fact.valid_to)}</span> : <span />}
      <div className="cites">
        {mine.slice(0, 2).map((s) => (
          <CitationChip key={s.span_id} span={s} label={label} path={path} timeline={tl} />
        ))}
        {mine.length > 2 && <Chip title={`${mine.length - 2} more sources`}>+{mine.length - 2}</Chip>}
        {!mine.length && st !== "proposed" && st !== "withdrawn" && st !== "confirmed" && (
          <Chip dashed title="No citable span survived the evidence filter">No source</Chip>
        )}
      </div>
      <Popover
        align="right"
        trigger={({ toggle }) => (
          <button type="button" className="more" aria-label="More" onClick={(e) => { e.stopPropagation(); toggle(); }}>
            <MoreHorizontal className="icon-sm" />
          </button>
        )}
      >
        {(close) => (
          <div onClick={(e) => e.stopPropagation()}>
            <button className="menu-item" disabled={!first} onClick={() => { close(); if (first) openEvidence({ tab: "source", spanId: first.span_id, sourceId: first.source_id, quote: { start: first.quote_start, end: first.quote_end }, path, timeline: tl, title: first.title, packs: pc.packs, fromTurn: pc.fromTurn }, mode); }}>
              <FileText className="icon-sm" /> Open source
            </button>
            <button className="menu-item" disabled={!path} onClick={() => { close(); if (path) openEvidence({ tab: "path", path, packs: pc.packs, fromTurn: pc.fromTurn, timeline: tl, spanId: first?.span_id, sourceId: first?.source_id }, mode); }}>
              <GitBranch className="icon-sm" /> Show path
            </button>
            <button className="menu-item" onClick={() => { close(); openEvidence({ tab: "timeline", timeline: tl, path, packs: pc.packs, fromTurn: pc.fromTurn, spanId: first?.span_id, sourceId: first?.source_id, title: text }, mode); }}>
              <History className="icon-sm" /> Show timeline
            </button>
            {fact.action_id && (
              <button className="menu-item" onClick={() => { close(); openAction(fact.action_id!, mode); }}>
                <Zap className="icon-sm" /> Open action
              </button>
            )}
            <div className="divider" />
            <CopyItem text={fact.assertion_id} onDone={close} />
          </div>
        )}
      </Popover>
    </div>
  );
}

function CopyItem({ text, onDone }: { text: string; onDone: () => void }) {
  const [done, setDone] = useState(false);
  return (
    <button className="menu-item" onClick={() => { navigator.clipboard?.writeText(text); setDone(true); setTimeout(onDone, 500); }}>
      <ExternalLink className="icon-sm" /> {done ? "Copied" : "Copy assertion id"}
    </button>
  );
}

export function IntervalChip({ from, to }: { from: number | null | undefined; to: number | null | undefined }) {
  return <Chip icon={Clock}>{fmtInterval(from, to)}</Chip>;
}
