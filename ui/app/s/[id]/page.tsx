"use client";

import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import { EvidenceText } from "@/components/EvidenceText";
import { SourceLinks } from "@/components/SourceLinks";
import { ErrorState, SkeletonRows } from "@/components/ui";
import { fmtDateTime, initials } from "@/lib/format";
import { KIND_LABEL, SYSTEM_LABEL } from "@/lib/labels";
import { useApi, useStore } from "@/lib/store";
import type { SourceView } from "@/lib/types";

export default function SourcePage() {
  return <Suspense fallback={null}><Source /></Suspense>;
}

const STYLE: Record<string, string> = { chat: "chat", ticket: "issue", wiki: "doc", meeting: "doc", adr: "doc", catalog: "code", roster: "code" };

/** A source as it looked where it was written (item 24 step 5): a Slack-style message, a Jira, Linear or
 * GitHub-style issue, a doc page, or a catalogue entry, with the cited span highlighted. */
function Source() {
  const { id } = useParams<{ id: string }>();
  const span = useSearchParams().get("span") || "";
  const s = useStore();
  const { data, error, loading, reload } = useApi<SourceView>(`/sources/${encodeURIComponent(decodeURIComponent(id))}`);
  const src = data?.source;
  const author = String(src?.author_id || "");
  useEffect(() => { if (author) s.resolveNames([author]); }, [author, s]);
  useEffect(() => { document.getElementById(`span-${span}`)?.scrollIntoView({ block: "center" }); }, [data, span]);
  if (error) return <div className="page-body"><ErrorState message={error} onRetry={reload} /></div>;
  if (loading || !data || !src) return <div className="page-body"><SkeletonRows n={6} /></div>;
  const kind = String(src.kind || "");
  const style = STYLE[kind] || "doc";
  const system = String(src.system || "");
  const who = author ? s.names[author]?.name || author.replace(/^person:/, "").replace(/-/g, " ") : "";
  const when = Number(src.updated_at || src.created_at || 0);
  return (
    <div className="ask-start">
      <div className="ask-start-inner" style={{ gap: 18 }}>
        <div className="row-wrap" style={{ justifyContent: "space-between" }}>
          <span className="eyebrow">{(SYSTEM_LABEL[system] || system || "Source").toUpperCase()} · {(KIND_LABEL[kind] || kind).toUpperCase()}</span>
          <SourceLinks sourceId={src.id} url={data.link?.url} system={system} demo={data.link?.demo} />
        </div>
        <article className={`origin ${style} ${system}`}>
          {style === "chat" && (
            <div className="origin-chat">
              <span className="avatar lg">{initials(who || "?")}</span>
              <div className="stack" style={{ gap: 4 }}>
                <div className="row-wrap"><span className="t-strong">{who || "Someone"}</span><span className="t-small text-3">{String(src.title || "")} · {when ? fmtDateTime(when) : ""}</span></div>
                {data.spans.map((x) => <p key={x.span} id={`span-${x.span}`} className={x.span === span ? "hl" : ""}>{x.text}</p>)}
              </div>
            </div>
          )}
          {style === "issue" && (
            <div className="origin-issue">
              <div className="stack" style={{ gap: 4 }}>
                <span className="home-mono t-small text-3">{String(src.external_id || "")}</span>
                <h1>{String(src.title || "").replace(/^[A-Z]+-\d+:\s*/, "")}</h1>
                {who && <span className="t-small text-3">Opened by {who}{when ? ` · ${fmtDateTime(when)}` : ""}</span>}
              </div>
              {data.spans.map((x) => <div key={x.span} id={`span-${x.span}`} className={`issue-row ${x.span === span ? "hl" : ""}`}>{x.text}</div>)}
            </div>
          )}
          {style === "doc" && (
            <div className="origin-doc">
              <h1>{String(src.title || "")}</h1>
              {when ? <span className="t-small text-3">{who ? `${who} · ` : ""}{fmtDateTime(when)}</span> : null}
              {data.spans.map((x) => <p key={x.span} id={`span-${x.span}`} className={x.span === span ? "hl" : ""}>{x.text}</p>)}
            </div>
          )}
          {style === "code" && (
            <div className="origin-code">
              <span className="t-strong">{String(src.title || "")}</span>
              {data.spans.map((x) => <div key={x.span} id={`span-${x.span}`} className={`code-row ${x.span === span ? "hl" : ""}`}><EvidenceText text={x.text} kind={kind}><pre>{x.text}</pre></EvidenceText></div>)}
            </div>
          )}
        </article>
        {data.banner && <span className="t-small text-3">{data.banner}</span>}
      </div>
    </div>
  );
}
