"use client";

import { useState } from "react";
import { structuredEvidence } from "@/lib/evidence";

/** A cited passage: a catalogue entry or roster row as a readable card (raw text one click away), prose as is. */
export function EvidenceText({ text, kind, children }: { text: string; kind?: string; children?: React.ReactNode }) {
  const [raw, setRaw] = useState(false);
  const card = structuredEvidence(text, kind);
  if (!card) return <>{children ?? text}</>;
  return (
    <span className="ev-card">
      {raw ? <pre className="ev-raw">{text.trim()}</pre> : card.line ? <span className="ev-line">{card.line}</span> : (
        <>
          <span className="t-strong">{card.title}</span>
          {card.rows.length > 0 && <dl className="ev-rows">{card.rows.map(([k, v]) => <span key={k}><dt>{k}</dt><dd>{v}</dd></span>)}</dl>}
        </>
      )}
      <button type="button" className="ev-toggle" onClick={(e) => { e.stopPropagation(); setRaw(!raw); }} aria-pressed={raw}>{raw ? "Readable" : "Raw"}</button>
    </span>
  );
}
