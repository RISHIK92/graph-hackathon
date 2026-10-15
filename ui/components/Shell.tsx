"use client";

import {
  AlertCircle, BookOpen, HelpCircle, LayoutGrid, Calendar, ChevronDown, GitBranch, Inbox, Info, KeyRound, Loader2, MessageSquare, PanelLeft, Search, Settings2, UserRound, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { dateInputValue, fmtDate, fmtDateTime, fromDateInput, initials } from "@/lib/format";
import { useStore } from "@/lib/store";
import { API_URL } from "@/lib/api";
import { CodingAgentHelp } from "./CodingAgentHelp";
import { CommandPalette } from "./CommandPalette";
import Inspector from "./Inspector";
import { Button, Chip, CountBadge, Field, Modal, Notice, Popover, Segmented, Toasts } from "./ui";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutGrid, key: "o" },
  { href: "/ask", label: "Ask", icon: MessageSquare, key: "a" },
  { href: "/directory", label: "Directory", icon: BookOpen, key: "d" },
  { href: "/graph", label: "Graph", icon: GitBranch, key: "g" },
  { href: "/inbox", label: "Inbox", icon: Inbox, key: "i" },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const s = useStore();
  const hasInspector = s.inspector.length > 0;
  const [helpOpen, setHelpOpen] = useState(false);
  const { inspectorPinned, closeInspector, pendingCount } = s;
  const pinned = useRef(inspectorPinned);
  useEffect(() => { pinned.current = inspectorPinned; }, [inspectorPinned]);
  // n5: an unpinned side panel belongs to the page it was opened on
  useEffect(() => { if (!pinned.current) closeInspector(); }, [path, closeInspector]);
  // m14: the tab says where you are, and how much waits in the Inbox
  useEffect(() => {
    const page = NAV.find((n) => n.href !== "/" && path.startsWith(n.href))?.label || (path === "/" ? "Overview" : "");
    const inbox = pendingCount > 0 ? ` (${pendingCount})` : "";
    if (page) document.title = `${page === "Inbox" ? `Inbox${inbox}` : page} · Company Brain`;
  }, [path, pendingCount]);

  // keyboard: ⌘K palette, [ sidebar, g+key jumps, / search
  useEffect(() => {
    let pendingG = 0;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (e.target as HTMLElement)?.isContentEditable;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); s.setPaletteOpen(true); return; }
      if (typing) return;
      if (e.key === "/") { e.preventDefault(); s.setPaletteOpen(true); return; }
      if (e.key === "[") { e.preventDefault(); s.setSidebarCollapsed(!s.sidebarCollapsed); return; }
      if (e.key === "g") { pendingG = Date.now(); return; }
      if (pendingG && Date.now() - pendingG < 800) {
        const n = NAV.find((x) => x.key === e.key);
        if (n) { e.preventDefault(); router.push(n.href); }
        pendingG = 0;
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [s, router]);

  const past = !!s.asOf;
  return (
    <div className={`app ${hasInspector ? "has-inspector" : ""} ${s.sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <nav className="sidebar" aria-label="Primary">
        <div className="sidebar-brand">
          <span className="mark" aria-hidden><GitBranch /></span>
          <span className="truncate">Company Brain</span>
        </div>
        {NAV.map((n) => {
          const active = path === n.href || path.startsWith(`${n.href}/`) || (n.href === "/directory" && path.startsWith("/e/"));
          const Icon = n.icon;
          return (
            <Link key={n.href} href={n.href} className={`nav-item ${active ? "active" : ""}`} title={n.label} aria-current={active ? "page" : undefined}>
              <Icon className="icon" />
              <span>{n.label}</span>
              {n.href === "/inbox" && s.pendingCount > 0 ? <span className="nav-badge"><CountBadge n={s.pendingCount} accent /></span> : <kbd className="nav-kbd">g {n.key}</kbd>}
            </Link>
          );
        })}
        <div className="sidebar-footer">
          <SessionStatus />
          <button className="session-status" onClick={() => setHelpOpen(true)} title="Use from your coding agent">
            <HelpCircle className="icon-sm" /><span>Help: use from your coding agent</span>
          </button>
          <button className="session-status" onClick={() => s.setSidebarCollapsed(!s.sidebarCollapsed)} title="Toggle sidebar  [">
            <PanelLeft className="icon-sm" /><span>Collapse</span><kbd className="right">[</kbd>
          </button>
        </div>
      </nav>

      <div className="main">
        <header className="ctxbar">
          <button className="search-btn" onClick={() => s.setPaletteOpen(true)} aria-label="Search and commands">
            <Search className="icon-sm" />
            <span>Search entities, questions, people…</span>
            <kbd>⌘K</kbd>
          </button>
          <span className="grow" />
          <AsOfPill />
          <ActingMenu />
        </header>
        <div className={`content ${past ? "past" : ""}`}>
          {s.sessionError ? <ApiDown /> : children}
        </div>
      </div>

      <Inspector />
      {s.sessionSheetOpen && <SessionSheet onHelp={() => { s.setSessionSheetOpen(false); setHelpOpen(true); }} />}
      {helpOpen && <CodingAgentHelp onClose={() => setHelpOpen(false)} />}
      {s.paletteOpen && <CommandPalette />}
      <Toasts />
    </div>
  );
}

function SessionStatus() {
  const s = useStore();
  const anon = s.session?.anonymous;
  return (
    <button className="session-status" onClick={() => s.setSessionSheetOpen(true)} title="Session settings">
      {s.sessionError ? <AlertCircle className="icon-sm text-error" /> : !s.session ? <Loader2 className="icon-sm spin text-3" /> : anon ? <Info className="icon-sm text-warning" /> : <KeyRound className="icon-sm text-success" />}
      <span className="truncate">{s.sessionError ? "API unreachable" : !s.session ? "Connecting…" : anon ? "Demo mode: nothing is saved" : "Writes enabled"}</span>
      <Settings2 className="icon-sm right" />
    </button>
  );
}

/** As-of pill: "Today" or "As of 12 Mar 2026 · ×"; the past is never silent (DESIGN.md §4.1). */
function AsOfPill() {
  const s = useStore();
  const [open, setOpen] = useState(false);
  return (
    <Popover
      align="right"
      open={open}
      onOpenChange={setOpen}
      trigger={({ toggle }) => (
        <button className={`pill ${s.asOf ? "warn" : ""}`} onClick={toggle} aria-haspopup="dialog" aria-expanded={open} title="Show the organisation as it was on a date">
          <Calendar className="icon-sm" />
          {s.asOf ? `As of ${fmtDate(s.asOf)}` : "Today"}
          {s.asOf ? (
            <span className="x" role="button" aria-label="Back to today" onClick={(e) => { e.stopPropagation(); s.setAsOf(null); s.toast({ tone: "info", title: "Viewing today" }); }}><X className="icon-sm" /></span>
          ) : <ChevronDown className="icon-sm" />}
        </button>
      )}
    >
      {(close) => (
        <div className="stack-3" style={{ padding: 8, width: 280 }}>
          <Field label="View the organisation as of" help="Owners, leads and teams are shown as they were on this date.">
            <input className="input" type="date" value={dateInputValue(s.asOf)} onChange={(e) => s.setAsOf(fromDateInput(e.target.value))} />
          </Field>
          <div className="row">
            <Button size="sm" onClick={() => { s.setAsOf(null); close(); }}>Today</Button>
            <Button size="sm" variant="primary" className="right" onClick={close}>Done</Button>
          </div>
        </div>
      )}
    </Popover>
  );
}

function ActingMenu() {
  const s = useStore();
  const me = s.people.find((p) => p.id === s.actingAs);
  const [q, setQ] = useState("");
  const list = useMemo(() => s.people.filter((p) => !q || p.name.toLowerCase().includes(q.toLowerCase()) || p.leads.some((l) => l.toLowerCase().includes(q.toLowerCase()))), [s.people, q]);
  return (
    <Popover
      align="right"
      trigger={({ toggle, open }) => (
        <button className="pill" onClick={toggle} aria-haspopup="menu" aria-expanded={open} title="Acting as (demo identity, not authentication)">
          <span className="avatar">{me ? initials(me.name) : "?"}</span>
          <span className="truncate" style={{ maxWidth: 160 }}>{me?.name || "Acting as…"}</span>
          <Chip tone="neutral" title="Switching person is for the demo. It is not a login.">Demo identity</Chip>
          <ChevronDown className="icon-sm" />
        </button>
      )}
    >
      {(close) => (
        <div style={{ width: 360 }}>
          {me && (
            <div className="stack" style={{ padding: "8px 10px 10px" }}>
              <div className="row">
                <span className="avatar lg">{initials(me.name)}</span>
                <div className="stack" style={{ gap: 2 }}>
                  <div className="t-strong">{me.name}</div>
                  <div className="t-small text-2">{me.title || "Person"}{me.team.length ? ` · ${me.team.join(", ")}` : ""}</div>
                </div>
              </div>
              <div className="row-wrap">
                {me.leads.map((l) => <Chip key={l} tone="accent" icon={UserRound}>Leads {l}</Chip>)}
                {me.decides.map((d) => <Chip key={d} tone="neutral">Decides {d}</Chip>)}
                {!me.leads.length && !me.decides.length && <Chip tone="neutral">Member</Chip>}
              </div>
              <div className="t-small text-3">Demo identity, not authentication. Only the right person (for example the owner&apos;s lead) can confirm a fact.</div>
            </div>
          )}
          <div className="divider" />
          <div style={{ padding: "4px 6px" }}>
            <div className="input-wrap"><Search /><input className="input sm" placeholder="Switch person…" value={q} onChange={(e) => setQ(e.target.value)} autoFocus
              onKeyDown={async (e) => { if (e.key === "Enter" && list[0]) { e.preventDefault(); close(); await s.setActingAs(list[0].id); s.toast({ tone: "info", title: `Now acting as ${list[0].name}` }); } }} /></div>
          </div>
          <div style={{ maxHeight: 280, overflow: "auto" }} role="menu">
            {list.map((p) => (
              <button key={p.id} className={`menu-item ${p.id === s.actingAs ? "active" : ""}`} role="menuitem" onClick={async () => { close(); await s.setActingAs(p.id); s.toast({ tone: "info", title: `Now acting as ${p.name}` }); }}>
                <span className="avatar">{initials(p.name)}</span>
                <span className="truncate">{p.name}</span>
                <span className="meta truncate">{p.leads.length ? `Leads ${p.leads.join(", ")}` : p.decides.length ? `Decides ${p.decides.join(", ")}` : p.team.join(", ")}</span>
              </button>
            ))}
            {!list.length && <div className="t-small text-3" style={{ padding: 10 }}>No one matches.</div>}
          </div>
          <div className="divider" />
          <button className="menu-item" onClick={() => { close(); s.setSessionSheetOpen(true); }}><Settings2 className="icon-sm" />Session settings</button>
        </div>
      )}
    </Popover>
  );
}

/** Session sheet: mode, token, acting person, as-of, theme, debug, reset (DESIGN.md §4.1). */
async function tokenAccepted(token: string, actingAs: string): Promise<boolean> {
  try {
    const r = await fetch(`${API_URL}/sessions`, {
      method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ acting_as: actingAs }),
    });
    return r.ok && !(await r.json()).anonymous;
  } catch {
    return false;
  }
}

function SessionSheet({ onHelp }: { onHelp: () => void }) {
  const s = useStore();
  const [tok, setTok] = useState("");
  const anon = s.session?.anonymous;
  return (
    <Modal title="Session" size="md" onClose={() => s.setSessionSheetOpen(false)} footer={<Button variant="primary" onClick={() => s.setSessionSheetOpen(false)}>Done</Button>}>
      {s.sessionError ? (
        <Notice tone="error" title="API unreachable" actions={<Button size="sm" onClick={s.retrySession}>Retry</Button>}>{s.sessionError}</Notice>
      ) : anon ? (
        <Notice tone="warning" title="Demo mode">Nothing you type is stored, there is no memory between visits, and writes (confirm, undo, actions) are off. Requests are rate-limited. Paste the write token to enable writes.</Notice>
      ) : (
        <Notice tone="success" title="Writes enabled">Confirm, undo and actions are recorded under the acting person.{s.nextResetAt ? ` The graph resets to its seed at ${fmtDateTime(s.nextResetAt)}; the reset waits while sessions are active.` : ""}</Notice>
      )}
      <div className="sheet-grid">
        <Field label="Write token" help={s.token ? "A token is set for this browser." : "Access token (for this demo). Saved in this browser only."}>
          {s.token ? (
            <div className="row"><Chip tone="success" icon={KeyRound}>Token set</Chip><Button size="sm" onClick={() => { s.setToken(""); setTok(""); }}>Remove</Button></div>
          ) : (
            <form className="row" onSubmit={async (e) => {
              e.preventDefault();
              const t = tok.trim();
              if (!t) return;
              // M8: check the token now, with a session of its own, instead of saving whatever was pasted
              const ok = await tokenAccepted(t, s.actingAs);
              if (ok) {
                s.setToken(t);
                s.toast({ tone: "success", title: "Writes enabled", body: "Confirm, undo and actions are now recorded as the acting person." });
              } else {
                s.toast({ tone: "error", title: "That token wasn't accepted", body: "Check it and try again." });
              }
            }}>
              <input className="input" type="password" placeholder="Paste token" value={tok} onChange={(e) => setTok(e.target.value)} autoComplete="off" autoFocus />
              <Button type="submit" size="sm" disabled={!tok.trim()}>Use</Button>
            </form>
          )}
        </Field>
        <Field label="Acting as" help="Demo identity, not authentication.">
          <select className="select" value={s.actingAs} onChange={(e) => s.setActingAs(e.target.value)}>
            {s.people.map((p) => <option key={p.id} value={p.id}>{p.name}{p.leads.length ? ` · leads ${p.leads.join(", ")}` : ""}</option>)}
          </select>
        </Field>
        <Field label="As of" help="Show the organisation as it was on this date. Leave empty for today.">
          <div className="row">
            <input className="input" type="date" value={dateInputValue(s.asOf)} onChange={(e) => s.setAsOf(fromDateInput(e.target.value))} />
            {s.asOf && <Button size="sm" onClick={() => s.setAsOf(null)}>Today</Button>}
          </div>
        </Field>
        <Field label="Theme" help="Light is the default. Dark is applied only when chosen here.">
          <Segmented options={[{ id: "light", label: "Light" }, { id: "dark", label: "Dark" }, { id: "system", label: "System" }]} value={s.theme} onChange={(v) => s.setTheme(v)} />
        </Field>
      </div>
      <div className="t-small text-3">Debug panels (raw packs, verifier report) show when the page URL has <code>?debug=1</code>.</div>
      <div className="t-small"><button className="link-btn" onClick={onHelp}>Use from your coding agent (MCP)</button></div>
    </Modal>
  );
}

function ApiDown() {
  const s = useStore();
  return (
    <div className="page"><div className="page-body" style={{ alignItems: "center", justifyContent: "center" }}>
      <div className="card stack-3" style={{ maxWidth: 520 }}>
        <div className="row"><AlertCircle className="icon text-error" /><span className="t-heading">The API is unreachable</span></div>
        <div className="t-small text-2">{s.sessionError}</div>
        <div className="t-small text-2">The UI talks only to the Python API. Start it with <code>uvicorn api.app:app --port 8000</code> or set <code>NEXT_PUBLIC_API_URL</code>.</div>
        <div className="row"><Button variant="primary" onClick={s.retrySession}>Retry</Button><Button onClick={() => s.setSessionSheetOpen(true)}>Session settings</Button></div>
      </div>
    </div></div>
  );
}
