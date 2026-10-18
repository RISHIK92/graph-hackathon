"use client";

import { Building2, FileText, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { JobProgress, useJob } from "@/components/JobProgress";
import { Button, Modal } from "@/components/ui";
import { qs, send, upload } from "@/lib/api";
import { useApi, useStore } from "@/lib/store";
import type { Directory } from "@/lib/types";

/** "Bring your company's context" (item 24 step 3): an empty workspace's two paths, the ingest's live
 * progress, then first questions built from what was ingested. */
export default function StartPage() {
  const s = useStore();
  const [job, track] = useJob();
  const fileRef = useRef<HTMLInputElement>(null);
  const [showDemo, setShowDemo] = useState(false);
  const router = useRouter();

  const run = async (p: Promise<{ job_id: string }>, kind: string) => {
    try {
      track((await p).job_id, kind);
    } catch (e) {
      s.toast({ tone: "error", title: "Couldn't start", body: String((e as Error).message || e) });
    }
  };
  const loadDemo = () => run(send("POST", "/workspace/demo", {}), "demo");
  const done = job?.state === "done" || (!job && s.workspace && !s.workspace.empty);
  useEffect(() => {
    // after the workspace status refreshes, so Ask doesn't open on its empty state for a moment
    if (job?.state === "done" && job.kind === "demo" && s.workspace && !s.workspace.empty) router.push("/ask");
  }, [job, router, s.workspace]);

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
            <div role="button" tabIndex={0} className="start-card" data-testid="load-demo-company" onClick={loadDemo}
              onKeyDown={(e) => { if (e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); void loadDemo(); } }}>
              <span className="kind now"><i />LOAD THE DEMO COMPANY</span>
              <span className="text"><Building2 className="icon-sm" /> A fintech with 6 teams, 15 systems and a reorganisation</span>
              <span className="returns">its Slack, docs, ADRs, tickets and roster · ready in seconds</span>
              <span className="t-small text-2">Not sure what the demo company is? <button type="button" className="link-btn" onClick={(e) => { e.stopPropagation(); setShowDemo(true); }}>View what&apos;s included</button></span>
            </div>
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
        {showDemo && <DemoContents onClose={() => setShowDemo(false)} onLoad={() => { setShowDemo(false); void loadDemo(); }} />}
        <input ref={fileRef} type="file" hidden accept=".md,.markdown,.txt,.json,.zip"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) void run(upload(`/workspace/ingest${qs({ filename: f.name })}`, f), "ingest"); e.target.value = ""; }} />
      </div>
    </div>
  );
}

// Captured from the demo template graph (seed 1, cached extractions) on Oct 17; the copy a workspace
// loads is that graph, so these only change when the seed does.
const DEMO_SOURCES: [string, number, string][] = [
  ["Slack messages", 400, "Jan 2025 – Sep 2026"],
  ["Tickets", 60, "with assignees, states and comments"],
  ["Wiki pages", 31, "service and project pages, some out of date"],
  ["Meeting notes", 14, "team syncs and ownership reviews"],
  ["Architecture decisions", 12, "ADRs, with the ones they replaced"],
  ["Service catalogue", 1, "owner, tier and project for every system"],
  ["Organisation roster", 1, "teams, leads and members"],
];
const DEMO_GRAPH: [string, number][] = [["teams", 6], ["people", 40], ["systems", 15], ["projects", 10], ["decisions", 12], ["tickets", 60]];
const DEMO_TEAMS = ["Fulfilment", "Infra", "Insights", "Payments", "Platform", "Risk"];
const DEMO_SYSTEMS = ["Aurora", "Billing", "Billing-v2", "Checkout", "Fraud Scoring", "Geo Lookup", "Image Resizer", "Ledger",
  "Postgres Main", "Pricing Engine", "Rate Limiter", "Reporting", "Session Store", "Statements", "Webhook Dispatcher"];

/** What "Load the demo company" brings in, before loading it. */
function DemoContents({ onClose, onLoad }: { onClose: () => void; onLoad: () => void }) {
  return (
    <Modal title="What the demo company includes" size="lg" onClose={onClose} footer={<>
      <Button onClick={onClose}>Close</Button>
      <Button variant="primary" onClick={onLoad}>Load the demo company</Button>
    </>}>
      <div className="stack-3">
        <p className="text-2" style={{ margin: 0 }}>An invented fintech, about 21 months of its work. Every source is demo data: none of it exists outside Nodus.</p>
        <div className="stack">
          <span className="eyebrow">SOURCES · 519 DOCUMENTS</span>
          <table className="demo-table"><tbody>
            {DEMO_SOURCES.map(([k, n, note]) => <tr key={k}><td className="num">{n}</td><td>{k}</td><td className="text-3">{note}</td></tr>)}
          </tbody></table>
        </div>
        <div className="stack">
          <span className="eyebrow">IN THE GRAPH · 569 DATED, CITED FACTS</span>
          <div className="row-wrap">{DEMO_GRAPH.map(([k, n]) => <span key={k} className="composer-chip demo-count"><b>{n}</b> {k}</span>)}</div>
          <div className="t-small text-2"><span className="text-3">Teams:</span> {DEMO_TEAMS.join(", ")}</div>
          <div className="t-small text-2"><span className="text-3">Systems:</span> {DEMO_SYSTEMS.join(", ")}</div>
        </div>
        <div className="stack">
          <span className="eyebrow">THE STORY IN IT</span>
          <p className="text-2" style={{ margin: 0 }}>On 1 Apr 2026 a reorganisation moved Ledger from Platform to Payments. Some wiki pages and chat still say the old thing, so the graph holds 12 open disputes, each with who can settle it. Ask who owns what, why a decision was made, what an outage would break, or what was true before the reorg.</p>
        </div>
      </div>
    </Modal>
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
