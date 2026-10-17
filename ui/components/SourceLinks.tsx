"use client";

import { ExternalLink, FileText } from "lucide-react";
import Link from "next/link";
import { qs } from "@/lib/api";
import { SYSTEM_LABEL } from "@/lib/labels";

/** "Open in Slack / Linear / GitHub / Jira" when there's a real link, "Demo data" when it's the demo company,
 * and always "View in Nodus": the full source with the span highlighted (item 24 step 5). */
export function SourceLinks({ sourceId, spanId, url, system, demo }: { sourceId: string; spanId?: string; url?: string; system?: string; demo?: boolean }) {
  const where = SYSTEM_LABEL[system || ""] || "the source";
  return (
    <span className="source-links">
      {url ? <a href={url} target="_blank" rel="noopener noreferrer"><ExternalLink className="icon-sm" />Open in {where}</a> : null}
      {demo && <span className="demo-tag" title="The demo company is invented: its sources exist only in Nodus">Demo data</span>}
      <Link href={`/s/${encodeURIComponent(sourceId)}${qs({ span: spanId })}`}><FileText className="icon-sm" />View in Nodus</Link>
    </span>
  );
}
