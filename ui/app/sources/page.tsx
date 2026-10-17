"use client";

import { useRef, useState } from "react";
import { JobProgress, useJob } from "@/components/JobProgress";
import { API_URL, qs, send, upload } from "@/lib/api";
import { useApi, useStore } from "@/lib/store";

interface SourceRow { kind: string; label: string; fields: string[]; missing: string[]; connected: boolean }

const ABOUT: Record<string, string> = {
  slack: "Messages and threads from the channels you pick, each linking back to Slack.",
  linear: "Issues, comments, assignees, projects and team members.",
  github: "Issues, pull requests and review comments, and CODEOWNERS as who owns the repo.",
  jira: "Issues, comments, assignees and components.",
  docs: "Markdown or text pages, or a Slack export. Add the page's URL so citations link to it.",
};
const PLACEHOLDER: Record<string, string> = {
  token: "API key or token", repo: "owner/repository", site: "https://your-site.atlassian.net", email: "you@company.com",
  jql: "project = ENG (optional)", channels: "#general, #payments", url: "https://… (optional)",
};

/** Connect a source (item 24 step 4): each says what it needs; keys are stored encrypted, never shown again. */
export default function SourcesPage() {
  const s = useStore();
  const { data, reload } = useApi<SourceRow[]>("/workspace/sources");
  const [job, track] = useJob();
  return (
    <div className="ask-start">
      <div className="ask-start-inner">
        <div className="stack" style={{ gap: 10 }}>
          <span className="eyebrow">SOURCES</span>
          <h1 className="ask-start-title">Connect your company&apos;s sources</h1>
          <p className="text-2" style={{ margin: 0, fontSize: 16 }}>Everything is read into {s.account?.demo ? "the shared demo workspace" : "your workspace"} only. Every answer cites where it came from and links back to it.</p>
        </div>
        {job && <JobProgress job={job} />}
        <div className="stack-3">
          {(data || []).map((r) => <SourceCard key={r.kind} row={r} onChange={reload} onJob={track} busy={job?.state === "running"} />)}
        </div>
      </div>
    </div>
  );
}

function SourceCard({ row, onChange, onJob, busy }: { row: SourceRow; onChange: () => void; onJob: (id: string, kind: string) => void; busy: boolean }) {
  const s = useStore();
  const [cfg, setCfg] = useState<Record<string, string>>({});
  const fileRef = useRef<HTMLInputElement>(null);
  const fields = row.kind === "docs" ? ["url"] : row.fields.filter((f) => !(row.kind === "slack" && f === "token"));
  const err = (e: unknown) => s.toast({ tone: "error", title: "That didn't work", body: String((e as Error).message || e) });
  const save = async () => {
    const config = Object.fromEntries(Object.entries(cfg).map(([k, v]) => [k, k === "channels" ? v.split(",").map((x) => x.trim()).filter(Boolean) : v]));
    try { await send("POST", `/workspace/sources/${row.kind}`, { config }); setCfg({}); onChange(); s.toast({ tone: "success", title: `${row.label} connected` }); }
    catch (e) { err(e); }
  };
  const sync = async () => {
    try { onJob((await send<{ job_id: string }>("POST", `/workspace/sources/${row.kind}/sync`, {})).job_id, `sync:${row.label}`); }
    catch (e) { err(e); }
  };
  return (
    <section className="source-card">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <span className="t-strong">{row.label}</span>
        {row.missing.length ? <span className="access-badge">Not configured</span> : row.connected && row.kind !== "docs" ? <span className="access-badge write">Connected</span> : null}
      </div>
      <span className="t-small text-2">{ABOUT[row.kind]}</span>
      {row.missing.length > 0 ? (
        <span className="t-small text-3">Not configured: the server needs {row.missing.join(", ")}. Once they&apos;re set, connect here.</span>
      ) : (
        <>
          {row.kind === "slack" && !row.connected && <a className="composer-send" style={{ alignSelf: "flex-start" }} href={`${API_URL}/auth/slack/start`}>Connect with Slack</a>}
          {(row.kind !== "slack" || row.connected) && fields.length > 0 && (
            <div className="source-fields">
              {fields.map((f) => (
                <label key={f} className="auth-field"><span>{f === "jql" ? "JQL" : f[0].toUpperCase() + f.slice(1)}</span>
                  <input type={f === "token" ? "password" : "text"} autoComplete="off" placeholder={PLACEHOLDER[f]} value={cfg[f] || ""}
                    onChange={(e) => setCfg({ ...cfg, [f]: e.target.value })} />
                </label>
              ))}
            </div>
          )}
          <div className="row-wrap">
            {row.kind === "docs" ? (
              <>
                <button type="button" className="composer-send" disabled={busy} onClick={() => fileRef.current?.click()}>Upload a file</button>
                <input ref={fileRef} type="file" hidden accept=".md,.markdown,.txt,.json,.zip" onChange={async (e) => {
                  const f = e.target.files?.[0];
                  e.target.value = "";
                  if (!f) return;
                  try { onJob((await upload<{ job_id: string }>(`/workspace/ingest${qs({ filename: f.name, url: cfg.url })}`, f)).job_id, "ingest"); }
                  catch (x) { err(x); }
                }} />
              </>
            ) : (
              <>
                {(row.kind !== "slack" || row.connected) && <button type="button" className="composer-chip" onClick={save}>{row.connected ? "Save changes" : "Connect"}</button>}
                {row.connected && <button type="button" className="composer-send" disabled={busy} onClick={sync}>Sync now</button>}
                {row.connected && <button type="button" className="composer-chip" onClick={async () => { try { await send("DELETE", `/workspace/sources/${row.kind}`, {}); onChange(); } catch (e) { err(e); } }}>Disconnect</button>}
              </>
            )}
          </div>
        </>
      )}
    </section>
  );
}
