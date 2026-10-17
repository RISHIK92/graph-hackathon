"use client";

import { useEffect, useState } from "react";
import { get } from "@/lib/api";
import { useStore } from "@/lib/store";

export interface Job { id: string; state: "running" | "done" | "failed"; docs: number; total: number; facts: number; disputes: number; error: string; kind: string }

/** Poll an ingest job (item 24) until it ends; then the store refreshes the workspace's status. */
export function useJob(): [Job | null, (id: string, kind: string) => void] {
  const s = useStore();
  const [job, setJob] = useState<Job | null>(null);
  useEffect(() => {
    if (!job || job.state !== "running") return;
    const t = setInterval(() => get<Job>(`/workspace/jobs/${job.id}`).then((j) => {
      setJob(j);
      if (j.state !== "running") { s.bump(); s.retrySession(); }   // a demo load replaces the graph, sessions included
    }).catch(() => undefined), 600);
    return () => clearInterval(t);
  }, [job, s]);
  return [job, (id, kind) => setJob({ id, state: "running", docs: 0, total: 0, facts: 0, disputes: 0, error: "", kind })];
}

export function JobProgress({ job }: { job: Job }) {
  const pct = job.total ? Math.round((job.docs / job.total) * 100) : 0;
  const what = job.kind === "demo" ? "Loading the demo company…" : job.kind.startsWith("sync:") ? `Reading ${job.kind.slice(5)}…` : "Reading your source…";
  return (
    <div className="job nx-rise" role="status" aria-live="polite">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <span className="t-strong">{job.state === "running" ? what : job.state === "done" ? "Done" : "That didn't work"}</span>
        <span className="home-mono t-small text-3">{job.docs}{job.total ? ` of ${job.total}` : ""} documents</span>
      </div>
      <div className="job-bar"><i style={{ width: `${job.state === "done" ? 100 : pct}%` }} /></div>
      <div className="row-wrap t-small">
        <span><b>{job.facts}</b> facts</span>
        <span><b className="disp">{job.disputes}</b> disputes</span>
      </div>
      {job.error && <div className="auth-err">{job.error}</div>}
    </div>
  );
}
