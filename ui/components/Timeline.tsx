"use client";

import { approvedText, factStatus, fmtDate, statusTone } from "@/lib/format";
import { chainLabel } from "@/lib/labels";
import { useOpenMode, useStore } from "@/lib/store";
import type { Pack } from "@/lib/types";
import { ActionChip, FactRow } from "./Chips";
import { Placeholder } from "./ui";

/** History timeline: a vertical rail with status dots, one fact row per statement, actions underneath. */
export function HistoryTimeline({ pack }: { pack: Pack }) {
  const { openAction } = useStore();
  const mode = useOpenMode();
  if (!pack.items.length) return <Placeholder>No history recorded.</Placeholder>;
  return (
    <div className="stack-3">
      {pack.items.map((it) => (
        <div key={it.item_id} className="stack">
          {pack.items.length > 1 && <span className="t-small t-strong text-2">{chainLabel(it.note)}</span>}
          <div className="timeline facts-host">
            {it.facts.map((f) => {
              const st = factStatus(f);
              const t = statusTone(st);
              return (
                <div key={f.assertion_id} className="tl-item">
                  <div className="rail">
                    <i className={t.dot} aria-hidden />
                    <div className="line" />
                  </div>
                  <div>
                    <FactRow fact={f} spans={it.spans} />
                    {f.overruled_by && <div className="sub">Overruled: the other side was confirmed {fmtDate(f.overruled_by.confirmed_at)}.</div>}
                    {f.confirmed_by && <div className="sub">{approvedText(f.confirmed_by)}{f.confirmed_by.action_id && <> <button className="link-btn" onClick={() => f.confirmed_by?.action_id && openAction(f.confirmed_by.action_id, mode)}>View confirmation</button></>}</div>}
                  </div>
                </div>
              );
            })}
          </div>
          {it.actions?.length ? (
            <div className="row-wrap t-small">
              <span className="text-3">Actions:</span>
              {it.actions.map((a) => (
                <ActionChip key={a.action_id} actionId={a.action_id} label={`${a.summary || a.action_id}${a.status === "undone" ? " (withdrawn)" : ""}`} />
              ))}
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}
