"use client";

import { Building2, FileText, Upload } from "lucide-react";
import Link from "next/link";
import { useRef } from "react";
import { JobProgress, useJob } from "@/components/JobProgress";
import { qs, send, upload } from "@/lib/api";
import { useApi, useStore } from "@/lib/store";
import type { Directory } from "@/lib/types";

/** "Bring your company's context" (item 24 step 3): an empty workspace's two paths, the ingest's live
 * progress, then first questions built from what was ingested. */
export default function StartPage() {
  const s = useStore();
  const [job, track] = useJob();
  const fileRef = useRef<HTMLInputElement>(null);

  const run = async (p: Promise<{ job_id: string }>, kind: string) => {
    try {
      track((await p).job_id, kind);
    } catch (e) {
      s.toast({ tone: "error", title: "Couldn't start", body: String((e as Error).message || e) });
    }
  };
  const done = job?.state === "done" || (!job && s.workspace && !s.workspace.empty);

  return (
    <div className="ask-start">
      <div className="ask-start-inner">
        <div className="stack nx-rise" style={{ gap: 10 }}>
          <span className="eyebrow">YOUR WORKSPACE{s.account?.demo ? " · SHARED DEMO" : ""}</span>
          <h1 className="ask-start-title">Bring your company&apos;s context</h1>
          <p className="text-2" style={{ margin: 0, fontSize: 16 }}>Nodus turns your messages, tickets and docs into one graph of dated, cited facts. Start with a source, or load the demo company to look around.</p>
        </div>

        {job && <JobProgress job={job} />}
        {done && <FirstQuestions />}

        {!job || job.state !== "running" ? (
          <div className="start-grid nx-rise nx-d1">
            <button type="button" className="start-card" onClick={() => run(send("POST", "/workspace/demo", {}), "demo")}>
              <span className="kind now"><i />LOAD THE DEMO COMPANY</span>
              <span className="text"><Building2 className="icon-sm" /> A fintech with 6 teams, 15 systems and a reorganisation</span>
              <span className="returns">its Slack, docs, ADRs, tickets and roster · ready in seconds</span>
            </button>
            <button type="button" className="start-card" onClick={() => fileRef.current?.click()}>
              <span className="kind sys"><i />UPLOAD DOCS OR A SLACK EXPORT</span>
              <span className="text"><Upload className="icon-sm" /> Markdown, text, a channel .json or the export .zip</span>
              <span className="returns">one file at a time · up to 20 MB</span>
            </button>
            <Link href="/sources" className="start-card">
              <span className="kind per"><i />CONNECT A SOURCE</span>
              <span className="text"><FileText className="icon-sm" /> Slack, Linear, GitHub, Jira</span>
              <span className="returns">each one shows what it needs to connect</span>
            </Link>
          </div>
        ) : null}
        <input ref={fileRef} type="file" hidden accept=".md,.markdown,.txt,.json,.zip"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) void run(upload(`/workspace/ingest${qs({ filename: f.name })}`, f), "ingest"); e.target.value = ""; }} />
      </div>
    </div>
  );
}

/** First questions from what the workspace holds: a system with an owner, a decision, the most critical. */
function FirstQuestions() {
  const s = useStore();
  const dir = useApi<Directory>(`/directory${qs({ as_of: s.asOf })}`);
  const d = dir.data;
  const owned = d?.systems.find((x) => x.owner);
  const dec = d?.decisions.find((x) => x.status === "accepted") || d?.decisions[0];
  const qsList = [
    owned && `Who owns ${owned.name}?`,
    owned && `What breaks if ${owned.name} goes down, and who do I tell?`,
    dec && `Why was ${dec.name} accepted?`,
    d?.systems.length ? "Which systems are most critical?" : "",
    d?.people.length ? "Where are our knowledge gaps?" : "",
  ].filter((x): x is string => !!x);
  return (
    <div className="stack-3 nx-rise">
      <span className="eyebrow">ASK YOUR FIRST QUESTION</span>
      {qsList.length ? (
        <div className="row-wrap">
          {qsList.map((q) => <Link key={q} href={`/ask${qs({ q, send: "1" })}`} className="composer-chip">{q}</Link>)}
        </div>
      ) : <span className="t-small text-2">Nothing to ask about yet: this source named no systems, teams or people. Try another source.</span>}
    </div>
  );
}
