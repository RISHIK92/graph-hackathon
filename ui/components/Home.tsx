"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { qs } from "@/lib/api";
import { useApi, useStore } from "@/lib/store";
import type { Directory, Pack } from "@/lib/types";
import { CodingAgentHelp } from "./CodingAgentHelp";

// Every value below is from the seed-1 demo company (captured from the API on a fresh seed), never invented:
// the catalogue entry behind "Platform owns Reporting", Platform as Ledger's owner before the reorg on 1 Apr 2026,
// the stale "Ledger overview" wiki page, and the real impact and dispute answers (item 19 design brief).
const ask = (q: string) => `/ask${qs({ q, send: "1" })}`;
const SAMPLES = ["Who owns Reporting?", "Who owned Ledger before the reorg?", "Why was ADR-007 accepted?"];
const WORDS = ["owns", "decided", "changed"];

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const m = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(m.matches);
    const on = () => setReduced(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, []);
  return reduced;
}

function useTick(ms: number, n: number, run: boolean): [number, (i: number) => void] {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (!run) return;
    const t = setInterval(() => setI((x) => (x + 1) % n), ms);
    return () => clearInterval(t);
  }, [ms, n, run]);
  return [i, setI];
}

export default function Home() {
  const still = useReducedMotion();
  const [help, setHelp] = useState(false);
  return (
    <div className="home">
      <div className="nx-barwrap" aria-hidden><div className="nx-bar" /></div>
      <Hero still={still} />
      <Problem still={still} />
      <Moments onMcp={() => setHelp(true)} />
      <GraphSection still={still} />
      <HowItWorks still={still} />
      <Footer />
      {help && <CodingAgentHelp onClose={() => setHelp(false)} />}
    </div>
  );
}

function Hero({ still }: { still: boolean }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [word] = useTick(2600, WORDS.length, !still);
  const [phase, setPhase] = useState(4);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const replay = () => {
    timers.current.forEach(clearTimeout);
    if (still) { setPhase(4); return; }
    setPhase(0);
    timers.current = [[1, 250], [2, 1150], [3, 1450], [4, 2250]].map(([p, ms]) => setTimeout(() => setPhase(p), ms));
  };
  useEffect(() => {
    replay();
    const t = timers.current;
    return () => t.forEach(clearTimeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [still]);
  const prev = (word + WORDS.length - 1) % WORDS.length;
  return (
    <section className="hero" aria-labelledby="hero-title">
      <div className="hero-copy">
        <span className="home-eyebrow nx-rise">Company memory on a FalkorDB graph</span>
        <h1 id="hero-title" className="nx-rise nx-d1">
          Know who{" "}
          <span className="nx-words">
            {WORDS.map((w, i) => <span key={w} className={`nx-word ${i === word ? "on" : i === prev ? "gone" : "off"}`} aria-hidden={i !== word}>{w}</span>)}
          </span>
          <br />what, and since when.
        </h1>
        <p className="hero-sub nx-rise nx-d2">Nodus reads Slack, docs and tickets into a graph of dated facts. Every answer is a path through that graph, with the sentence it came from.</p>
        <form className="hero-ask nx-rise nx-d3" onSubmit={(e) => { e.preventDefault(); if (q.trim()) router.push(ask(q.trim())); }}>
          <label htmlFor="hero-q" className="sr-only">Ask a question</label>
          <input id="hero-q" type="text" value={q} onChange={(e) => setQ(e.target.value)} placeholder="What breaks if Aurora goes down?" autoComplete="off" />
          <button type="submit">Ask</button>
        </form>
        <div className="hero-try nx-rise nx-d4">
          <span>Try</span>
          {SAMPLES.map((s, i) => <Link key={s} href={ask(s)} className="home-btn"><span className="num">{i + 1}</span>{s}</Link>)}
        </div>
      </div>

      <div className="hero-card nx-rise nx-d2" aria-live="polite">
        <div className="hero-card-top">
          <span>YOU ASKED · WHO OWNS REPORTING?</span>
          <button type="button" className="home-btn" onClick={replay} aria-label="Replay the answer">Replay</button>
        </div>
        {phase === 1 && <span className="nx-think">Walking the graph · OWNS, LEADS…</span>}
        {phase >= 2 && (
          <p className="hero-answer nx-rise"><span className="e-per">Platform</span> owns <span className="e-sys">Reporting</span>.<sup className="nx-cite">[1]</sup> <span className="e-per">Tomas Reyes</span> leads Platform.<sup className="nx-cite">[2]</sup></p>
        )}
        {phase >= 3 && (
          <div className="hero-path">
            <span className="nx-chip sys nx-rise">Reporting</span>
            <span className="nx-rel nx-rise nx-d1">← OWNS</span>
            <span className="nx-chip per nx-rise nx-d2">Platform</span>
            <span className="nx-rel nx-rise nx-d3">← LEADS</span>
            <span className="nx-chip per nx-rise nx-d4">Tomas Reyes</span>
            <span className="nx-meta nx-rise nx-d5">2 hops · 2 sources</span>
          </div>
        )}
        {phase >= 4 && (
          <>
            <div className="hero-source nx-rise">
              <span className="nx-cite">[1]</span>
              <div className="stack" style={{ gap: 4 }}>
                <q>Reporting · Owner: Platform · since 1 Jan 2025</q>
                <span className="src-meta">Service catalogue · Reporting entry · valid since 1 Jan 2025</span>
              </div>
            </div>
            <div className="hero-links nx-rise nx-d1">
              <Link href={ask("Who owns Reporting?")} className="home-link">Show how I answered</Link>
              <Link href={ask("Who owns Reporting?")} className="home-link">See the Cypher</Link>
            </div>
          </>
        )}
        <span className="hero-example">Example from the demo company</span>
      </div>
    </section>
  );
}

const WITHOUT = [
  { title: "Search Slack for “ledger owner”", body: "Old threads and new threads, and nobody says which is current." },
  { title: "Open the wiki", body: "The Ledger overview page says Platform owns Ledger. It was written on 10 Jun 2025, before the reorg." },
  { title: "Page Platform", body: "Payments has owned Ledger since 1 Apr 2026. Nobody updated the page." },
  { title: "Ask around until someone remembers", body: "Payments, probably. Who leads it now?" },
];
const WITH = [
  { title: "Ask: “What breaks if Ledger goes down, and who do I tell?”", body: "One question, in plain words." },
  { title: "Checkout, Reporting and Statements are affected", body: "Found by walking DEPENDS_ON edges in the graph; Statements depends on Ledger through Reporting." },
  { title: "Tell Priya Raman, Tomas Reyes and Bob Lindqvist", body: "The leads of the teams that own Ledger and what depends on it, each fact cited." },
  { title: "The stale wiki page is flagged", body: "“Flag stale docs about Ledger” finds the Ledger overview passage that still says Platform." },
];

function Problem({ still }: { still: boolean }) {
  const [tick] = useTick(1100, 9, !still);
  const shown = still ? 4 : Math.min(tick, 4);
  const end = still || tick >= 5;
  const col = (kind: "without" | "with", list: typeof WITH, head: string, last: string) => (
    <div className={`problem-col ${kind}`}>
      <span className="head">{head}</span>
      {list.map((p, i) => (
        <div key={p.title} className={`nx-pstep ${i < shown ? "on" : ""}`}>
          <span className="nx-pnum">{i + 1}</span>
          <span className="stack" style={{ gap: 2 }}><span className="title">{p.title}</span><span className="body">{p.body}</span></span>
        </div>
      ))}
      <span className={`end ${end ? "on" : ""}`}>{last}</span>
    </div>
  );
  return (
    <section className="home-section problem" aria-labelledby="problem-title">
      <div className="home-wrap">
        <div className="home-intro">
          <span className="home-eyebrow" style={{ color: "var(--dispute-text)" }}>The problem</span>
          <h2 id="problem-title">2 a.m. Ledger is down.<br /><span style={{ color: "var(--text-label)" }}>Who do you page?</span></h2>
          <p className="home-lede" style={{ fontSize: 17 }}>The answer exists somewhere in your company. It&apos;s just spread across a Slack thread, a wiki page written before the reorg, and someone&apos;s memory.</p>
        </div>
        <div className="problem-cols">
          {col("without", WITHOUT, "WITHOUT NODUS", "→ the wrong team woke up, and the stale page is still there")}
          {col("with", WITH, "WITH NODUS", "→ one question, the right people, with the source to prove it")}
        </div>
      </div>
    </section>
  );
}

const MOMENTS = [
  { label: "CITED ANSWERS", title: "Every answer shows its path", body: "Not a summary of documents: a walk through the graph, with the source sentence behind each step.", cta: "Ask who owns Reporting →", href: ask("Who owns Reporting?") },
  { label: "TIME TRAVEL", title: "Rewind the company to any date", body: "Facts keep the dates they held. Ask about the time before the reorg and get that time's answer, cited.", cta: "Compare then and now →", href: ask("Who owned Ledger before the reorg?") },
  { label: "DISPUTES", title: "Contradictions get settled, not buried", body: "When a chat message contradicts the record, Nodus keeps both and asks the one person the graph says can decide.", cta: "Settle a dispute →", href: "/inbox" },
  { label: "CODING AGENTS", title: "Claude Code asks it too", body: "An MCP server gives agents the same cited answers: who owns this service, and what breaks if I change it.", cta: "Connect over MCP →", href: "" },
];

function Moments({ onMcp }: { onMcp: () => void }) {
  const [active, setActive] = useState(0);
  const [hover, setHover] = useState(false);
  const [paused, setPaused] = useState(false);
  const demo = (i: number) => [
    <span key="p" className="nx-demo"><span className="e-sys">Reporting</span><span className="nx-rel">←</span><span className="e-per">Platform</span><span className="nx-rel">←</span><span className="e-per">Tomas Reyes</span><span className="nx-meta" style={{ marginLeft: "auto" }}>2 hops · each cited</span></span>,
    <span key="t" className="nx-thennow"><span className="then"><span className="tag">THEN · TO 31 MAR 2026</span>Platform owned Ledger</span><span className="now"><span className="tag">NOW · SINCE 1 APR 2026</span>Payments owns Ledger</span></span>,
    <span key="d" className="nx-demo col"><span className="row" style={{ gap: 8 }}><span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--dispute)" }} />A chat message says “Infra owns Ledger now”</span><span style={{ color: "var(--text-label)" }}>Can settle: <span className="e-per">Priya Raman</span>, lead of the owning team</span></span>,
    <span key="m" className="nx-demo col home-mono" style={{ fontSize: 12.5 }}><span style={{ color: "var(--text-label)" }}>› get_owner(&quot;system:checkout&quot;)</span><span>Payments · Priya Raman <span style={{ color: "var(--primary-text)" }}>[cited]</span></span></span>,
  ][i];
  return (
    <section className="home-section" aria-labelledby="moments-title">
      <div className="home-wrap">
        <div className="moments-head">
          <div className="home-intro" style={{ maxWidth: "46em" }}>
            <span className="home-eyebrow">What a wiki can&apos;t do</span>
            <h2 id="moments-title" className="home-h2">Four things you can try in one click.</h2>
          </div>
          <button type="button" className="home-btn" onClick={() => setPaused(!paused)} aria-pressed={paused}>{paused ? "Play tour" : "Pause tour"}</button>
        </div>
        <div className={`nx-cards ${hover || paused ? "nx-paused" : ""}`} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
          {MOMENTS.map((m, i) => {
            const on = i === active;
            return (
              <div key={m.label} className={`nx-card ${on ? "active" : ""}`} onClick={() => setActive(i)}>
                <button type="button" className="stack" style={{ gap: 14, textAlign: "left", font: "inherit", color: "inherit", background: "none", border: 0, padding: 0, cursor: "pointer" }}
                  aria-expanded={on} onClick={(e) => { e.stopPropagation(); setActive(i); }}>
                  <span className="label">{String(i + 1).padStart(2, "0")} · {m.label}</span>
                  <span className="title">{m.title}</span>
                </button>
                <span className="nx-detail">
                  <span className="body">{m.body}</span>
                  {demo(i)}
                  {m.href ? <Link href={m.href} className="nx-cta">{m.cta}</Link>
                    : <button type="button" className="nx-cta" style={{ background: "none", border: 0, padding: 0, font: "inherit", cursor: "pointer" }} onClick={onMcp}>{m.cta}</button>}
                </span>
                <span className="nx-track" aria-hidden><span className="nx-fill" onAnimationEnd={() => { if (on) setActive((i + 1) % MOMENTS.length); }} /></span>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

type Kind = "s" | "p" | "d";
const N: Record<string, { name: string; x: number; y: number; k: Kind }> = {
  priya: { name: "Priya Raman", x: 12, y: 18, k: "p" },
  payments: { name: "Payments", x: 32, y: 34, k: "p" },
  ledger: { name: "Ledger", x: 56, y: 50, k: "s" },
  infra: { name: "Infra", x: 62, y: 13, k: "p" },
  checkout: { name: "Checkout", x: 86, y: 24, k: "s" },
  reporting: { name: "Reporting", x: 88, y: 55, k: "s" },
  statements: { name: "Statements", x: 78, y: 84, k: "s" },
  aurora: { name: "Aurora", x: 48, y: 87, k: "s" },
  adr: { name: "ADR-007: Move Ledger to Aurora", x: 20, y: 66, k: "d" },
  platform: { name: "Platform", x: 13, y: 90, k: "p" },
};
const E = [
  { id: "lead", a: "priya", b: "payments", label: "LEADS" },
  { id: "owns", a: "payments", b: "ledger", label: "OWNS" },
  { id: "owns2", a: "payments", b: "checkout", label: "OWNS" },
  { id: "d1", a: "checkout", b: "ledger", label: "DEPENDS_ON" },
  { id: "d2", a: "reporting", b: "ledger", label: "DEPENDS_ON" },
  { id: "d3", a: "statements", b: "reporting", label: "DEPENDS_ON" },
  { id: "runs", a: "ledger", b: "aurora", label: "DEPENDS_ON" },
  { id: "aff", a: "adr", b: "ledger", label: "AFFECTS" },
  { id: "disp", a: "infra", b: "ledger", label: "OWNS? · DISPUTED", kind: "dispute" },
  { id: "then", a: "platform", b: "ledger", label: "OWNED · THEN", kind: "then" },
];
const F = [
  { title: "Answers with receipts", body: "Every claim links to the sentence it came from. You get a path through the graph, not a paragraph.", nodes: ["priya", "payments", "checkout"], edges: ["lead", "owns2"], caption: "Who owns Checkout? → Checkout ← OWNS ← Payments ← LEADS ← Priya Raman · 2 hops · each hop cited" },
  { title: "A memory with dates", body: "Facts keep when they started and stopped being true, so you can ask about any day.", nodes: ["platform", "payments", "ledger"], edges: ["then", "owns"], caption: "As of 31 Mar 2026: Platform owned Ledger. From 1 Apr 2026: Payments. Both answers cited." },
  { title: "Disagreements, settled by the org chart", body: "Conflicts are kept and flagged, then routed to the one person the graph says can decide.", nodes: ["infra", "ledger", "payments", "priya"], edges: ["disp", "lead", "owns"], caption: "Someone says “Infra owns Ledger now” in chat. Who can settle it? Priya Raman: she LEADS Payments, which OWNS Ledger." },
  { title: "Blast radius in one question", body: "Graph algorithms on a dated snapshot (PageRank, betweenness, shortest paths) find what breaks and who to tell.", nodes: ["aurora", "ledger", "checkout", "reporting", "statements"], edges: ["runs", "d1", "d2", "d3"], caption: "What breaks if Aurora goes down? Ledger, Checkout, Reporting and Statements. Tell Bob Lindqvist, Priya Raman and Tomas Reyes." },
  { title: "Decisions you can trace", body: "Why something is the way it is: the decision, who made it, and what it changed.", nodes: ["adr", "ledger", "aurora"], edges: ["aff", "runs"], caption: "Why was ADR-007 accepted? → it moved Ledger to Aurora (10 Feb 2026), because “Postgres Main could not sustain Ledger write volume during month-end close”." },
  { title: "Built for coding agents", body: "Claude Code asks the same graph over MCP. Writes follow the same permissions, and every one can be undone.", nodes: ["priya", "payments", "ledger", "checkout", "reporting", "statements"], edges: ["lead", "owns", "d1", "d2", "d3"], caption: "get_owner · critical_systems · connection_between · knowledge_gaps: 16 read tools, 6 write tools" },
];
const KC: Record<Kind, [string, string, string]> = { s: ["var(--entity-system-bg)", "var(--entity-system)", "var(--entity-system-border)"], p: ["var(--entity-person-bg)", "var(--entity-person)", "var(--entity-person-border)"], d: ["var(--entity-record-bg)", "var(--entity-record)", "var(--entity-record-border)"] };

function GraphSection({ still }: { still: boolean }) {
  const [locked, setLocked] = useState(false);
  const [feat, setFeat] = useTick(5000, F.length, !still && !locked);
  const cur = F[feat];
  return (
    <section className="home-section home-graph" aria-labelledby="graph-title">
      <div className="home-wrap">
        <div className="home-intro">
          <span className="home-eyebrow">The graph</span>
          <h2 id="graph-title" className="home-h2">Every feature is a walk through one graph.</h2>
          <p className="home-lede">Pick a feature to see the relationships it uses. This is the demo company: real nodes, real edge types.</p>
        </div>
        <div className="graph-cols">
          <div className="feat-list">
            {F.map((f, i) => (
              <button key={f.title} type="button" className={`nx-feat ${i === feat ? "active" : ""}`} aria-pressed={i === feat} onClick={() => { setFeat(i); setLocked(true); }}>
                <span className="num">{String(i + 1).padStart(2, "0")}</span>
                <span className="stack" style={{ gap: 4 }}><span className="title">{f.title}</span><span className="fbody">{f.body}</span></span>
              </button>
            ))}
          </div>
          <div className="graph-stage">
            <figure className="graph-fig" role="img" aria-label={`Demo company graph. Highlighted for: ${cur.title}. ${cur.caption}`}>
              <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
                {E.map((e) => {
                  const a = N[e.a], b = N[e.b], lit = cur.edges.includes(e.id);
                  const stroke = e.kind === "dispute" ? (lit ? "var(--dispute)" : "var(--dispute-border)") : e.kind === "then" ? (lit ? "var(--then)" : "var(--then-border)") : lit ? "var(--primary-text)" : "var(--line-mid)";
                  const cls = e.kind ? "nx-edge nx-dashed" : lit ? "nx-edge nx-flow" : "nx-edge";
                  return <line key={e.id} x1={a.x} y1={a.y} x2={b.x} y2={b.y} className={cls} vectorEffect="non-scaling-stroke" style={{ stroke, strokeWidth: lit ? 2.4 : 1.2 }} />;
                })}
              </svg>
              {E.map((e) => {
                const a = N[e.a], b = N[e.b], lit = cur.edges.includes(e.id);
                const color = e.kind === "dispute" ? "var(--dispute)" : e.kind === "then" ? "var(--then)" : "var(--primary-text)";
                return <span key={e.id} className="nx-elabel" style={{ left: `${(a.x + b.x) / 2}%`, top: `${(a.y + b.y) / 2}%`, color, opacity: lit ? 1 : 0 }}>{e.label}</span>;
              })}
              {Object.entries(N).map(([id, n]) => {
                const lit = cur.nodes.includes(id), c = KC[n.k];
                return <span key={id} className={`nx-node ${lit ? "lit" : ""}`} style={{ left: `${n.x}%`, top: `${n.y}%`, background: c[0], color: c[1], borderColor: lit ? c[1] : c[2], opacity: lit ? 1 : 0.32 }}>{n.name}</span>;
              })}
            </figure>
            <div className="graph-foot">
              <span key={feat} className="graph-caption">{cur.caption}</span>
              <span className="graph-legend">
                <span><i style={{ background: "var(--entity-system)" }} />Systems</span>
                <span><i style={{ background: "var(--entity-person)" }} />Teams, people</span>
                <span><i style={{ background: "var(--entity-record)" }} />Decisions</span>
                <span><i className="line" style={{ background: "var(--then)" }} />Then</span>
                <span><i className="line" style={{ background: "var(--dispute)" }} />Disputed</span>
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

const PHASES = [
  ["SENTENCE", "Someone says something new. Nodus keeps it word for word."],
  ["FACT", "The words become a fact: who, what, and since when."],
  ["GRAPH", "FalkorDB finds the conflict. Nothing is overwritten."],
  ["ANSWER", "The next answer tells the truth, with receipts."],
];
type Tok = { text: string; x: number; y: number; fs: number; bg: string; fg: string; bd: string; pad: string; mono?: boolean; bs?: string };
const plain = (text: string, x: number): Tok => ({ text, x, y: 32, fs: 40, bg: "transparent", fg: "var(--text)", bd: "transparent", pad: "0px 0px" });
const TOKENS: Tok[][] = [
  [plain("“Infra", 28), { text: "Infra", x: 20, y: 40, fs: 16, bg: "var(--entity-person-bg)", fg: "var(--entity-person)", bd: "var(--entity-person)", pad: "7px 14px" }, { text: "Infra", x: 30, y: 58, fs: 15, bg: "var(--dispute-bg)", fg: "var(--dispute-text)", bd: "var(--dispute)", pad: "6px 13px", bs: "dashed" }],
  [plain("owns", 41), { text: "—OWNS→", x: 38, y: 40, fs: 14, bg: "transparent", fg: "var(--text-quote)", bd: "transparent", pad: "0px 0px", mono: true }, { text: "OWNS? · DISPUTES", x: 47, y: 51, fs: 11, bg: "var(--bg)", fg: "var(--dispute)", bd: "transparent", pad: "1px 6px", mono: true }],
  [plain("Ledger", 55.5), { text: "Ledger", x: 56, y: 40, fs: 16, bg: "var(--entity-system-bg)", fg: "var(--entity-system)", bd: "var(--entity-system)", pad: "7px 14px" }, { text: "Ledger", x: 64, y: 38, fs: 18, bg: "var(--entity-system-bg)", fg: "var(--entity-system)", bd: "var(--entity-system)", pad: "9px 18px" }],
  [plain("now.”", 71.5), { text: "valid from: today", x: 78, y: 40, fs: 13, bg: "var(--now-bg)", fg: "var(--primary-text)", bd: "var(--now-border)", pad: "6px 12px", mono: true }, { text: "claimed today", x: 30, y: 67, fs: 11, bg: "transparent", fg: "var(--text-label)", bd: "transparent", pad: "0px 0px", mono: true }],
];

function HowItWorks({ still }: { still: boolean }) {
  const s = useStore();
  const who = s.people.find((p) => p.id === s.actingAs)?.name || "Someone";
  const [locked, setLocked] = useState(false);
  const [ph, setPh] = useTick(3800, PHASES.length, !still && !locked);
  const g = ph >= 2 ? 1 : 0;
  return (
    <section className="home-section" aria-labelledby="how-title">
      <div className="home-wrap" style={{ gap: 32 }}>
        <div className="home-intro">
          <span className="home-eyebrow">How it works</span>
          <h2 id="how-title" className="home-h2">Watch a sentence turn into a graph.</h2>
        </div>
        <div className="how-box">
          <div className="how-phases">
            {PHASES.map(([label, line], i) => (
              <button key={label} type="button" aria-pressed={i === ph} onClick={() => { setPh(i); setLocked(true); }}
                className={`nx-ph ${i === ph ? "active" : i < ph ? "done" : ""} ${locked ? "locked" : ""}`}>
                <span className="num">{String(i).padStart(2, "0")}</span>
                <span className="stack" style={{ gap: 4 }}><span className="label">{label}</span><span className="line">{line}</span></span>
                <span className="nx-ph-bar" aria-hidden><span className="nx-ph-fill" /></span>
              </button>
            ))}
          </div>
          <figure className="how-fig" role="img" aria-label={`Step ${String(ph).padStart(2, "0")}, ${PHASES[ph][0]}: ${PHASES[ph][1]}`}>
            {ph === 1 && <span className="nx-scan" aria-hidden />}
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
              <line className="g" x1="12" y1="15" x2="30" y2="26" vectorEffect="non-scaling-stroke" style={{ stroke: "var(--entity-person-border)", strokeWidth: 1.6, opacity: g }} />
              <line className="g nx-flow" x1="30" y1="26" x2="64" y2="38" vectorEffect="non-scaling-stroke" style={{ stroke: "var(--primary-text)", strokeWidth: 2.2, opacity: g }} />
              <line className="g nx-dashed" x1="30" y1="58" x2="64" y2="38" vectorEffect="non-scaling-stroke" style={{ stroke: "var(--dispute)", strokeWidth: 2, opacity: g }} />
            </svg>
            <span className="nx-node g" style={{ left: "12%", top: "15%", background: "var(--entity-person-bg)", color: "var(--entity-person)", borderColor: "var(--entity-person-border)", opacity: g }}>Priya Raman</span>
            <span className="nx-elabel g" style={{ left: "21%", top: "20.5%", color: "var(--entity-person)", opacity: g }}>LEADS</span>
            <span className="nx-node g" style={{ left: "30%", top: "26%", background: "var(--entity-person-bg)", color: "var(--entity-person)", borderColor: "var(--entity-person)", opacity: g }}>Payments</span>
            <span className="nx-elabel g" style={{ left: "47%", top: "29%", color: "var(--primary-text)", opacity: g }}>OWNS · since 1 Apr 2026</span>
            {TOKENS.map((t, i) => {
              const k = t[Math.min(ph, 2)];
              return (
                <span key={i} className="nx-tok" style={{ left: `${k.x}%`, top: `${k.y}%`, fontSize: k.fs, background: k.bg, color: k.fg, borderColor: k.bd, padding: k.pad, borderStyle: k.bs || "solid", fontFamily: k.mono ? "var(--mono)" : "var(--font)" }}>{k.text}</span>
              );
            })}
            {ph === 0 && <span className="how-cap meta">{who} · in chat with Nodus</span>}
            {ph === 1 && <span className="how-cap span">source span kept word for word · {who}, chat, just now</span>}
            {ph >= 2 && <span className="how-cap conflict">conflict found · nothing overwritten</span>}
            {ph === 3 && (
              <div className="how-cap answer">
                <span className="q">NEXT TIME ANYONE ASKS · WHO OWNS LEDGER?</span>
                <span className="a">Recorded: <span className="e-per">Payments</span> owns <span className="e-sys">Ledger</span> (catalogue)<sup className="nx-cite">[1]</sup>; <span className="e-disp">disputed by a chat message saying “Infra owns Ledger”</span><sup className="nx-cite">[2]</sup>. <span className="e-per">Priya Raman</span> can settle it.</span>
              </div>
            )}
          </figure>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  const s = useStore();
  const dir = useApi<Directory>(`/directory${qs({ as_of: s.asOf })}`);
  const gaps = useApi<Pack>(`/gaps${qs({ as_of: s.asOf })}`);
  const d = dir.data;
  const gap = (gaps.data?.items || []).find((it) => it.aggregate?.count && it.aggregate.members.length)?.aggregate;
  const first = gap?.members[0];
  const n = (x: number | undefined, label: string, cls = "") => <span><b className={cls}>{x ?? "–"}</b> {label}</span>;
  return (
    <footer className="home-section">
      <div className="home-foot">
        <span className="tag">DEMO GRAPH{s.nextResetAt ? " · RESETS NIGHTLY" : ""}</span>
        {n(d?.teams.length, "teams")}
        {n(d?.systems.length, "systems")}
        {n(d?.decisions.length, "decisions")}
        {n(d?.systems.filter((x) => x.disputed).length, "open disputes", "disp")}
        <span className="grow" />
        {first && (
          <span>Gap: <Link href={`/e/${encodeURIComponent(first.id)}`} className="e-sys">{first.name}</Link> {/\bteams? with no lead/.test(gap?.text || "") ? "has no lead" : "has no owner with a lead"}</span>
        )}
      </div>
    </footer>
  );
}
