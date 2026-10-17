"use client";

import { AlertCircle, Calendar, ChevronDown, HelpCircle, KeyRound, LogOut, Moon, Search, Settings2, Sun, Trash2, UserRound, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { dateInputValue, fmtDate, fmtDateTime, fromDateInput, initials } from "@/lib/format";
import { useStore } from "@/lib/store";
import { ACCOUNTS, API_URL, send } from "@/lib/api";
import { CodingAgentHelp } from "./CodingAgentHelp";
import { CommandPalette } from "./CommandPalette";
import Inspector from "./Inspector";
import { Button, Chip, Field, Modal, Notice, Popover, Toasts } from "./ui";

// g+key jumps; Explore merges Directory and Graph (design brief step 6); both stay reachable by key and ⌘K
const JUMPS = [
  { href: "/", label: "Home", key: "o" },
  { href: "/ask", label: "Ask", key: "a" },
  { href: "/explore", label: "Explore", key: "x" },
  { href: "/directory", label: "Directory", key: "d" },
  { href: "/graph", label: "Graph", key: "g" },
  { href: "/inbox", label: "Inbox", key: "i" },
];
const NAV = [
  { href: "/", label: "Home", key: "o", match: (p: string) => p === "/" },
  { href: "/ask", label: "Ask", key: "a", match: (p: string) => p.startsWith("/ask") },
  { href: "/explore", label: "Explore", key: "x", match: (p: string) => /^\/(explore|directory|graph|e\/)/.test(p) },
  { href: "/inbox", label: "Inbox", key: "i", match: (p: string) => p.startsWith("/inbox") },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const s = useStore();
  const hasInspector = s.inspector.length > 0;
  const [helpOpen, setHelpOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const { inspectorPinned, closeInspector, pendingCount } = s;
  const pinned = useRef(inspectorPinned);
  useEffect(() => { pinned.current = inspectorPinned; }, [inspectorPinned]);
  // n5: an unpinned side panel belongs to the page it was opened on
  useEffect(() => { if (!pinned.current) closeInspector(); }, [path, closeInspector]);
  // m14: the tab says where you are, and how much waits in the Inbox
  useEffect(() => {
    const page = JUMPS.find((n) => n.href !== "/" && path.startsWith(n.href))?.label || (path === "/" ? "Home" : "");
    const inbox = pendingCount > 0 ? ` (${pendingCount})` : "";
    if (page) document.title = `${page === "Inbox" ? `Inbox${inbox}` : page} · Nodus`;
  }, [path, pendingCount]);

  // keyboard: ⌘K palette, g+key jumps, / search
  useEffect(() => {
    let pendingG = 0;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (e.target as HTMLElement)?.isContentEditable;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); s.setPaletteOpen(true); return; }
      if (typing) return;
      if (e.key === "/") { e.preventDefault(); s.setPaletteOpen(true); return; }
      if (e.key === "g") { pendingG = Date.now(); return; }
      if (pendingG && Date.now() - pendingG < 800) {
        const n = JUMPS.find((x) => x.key === e.key);
        if (n) { e.preventDefault(); router.push(n.href); }
        pendingG = 0;
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [s, router]);

  // item 24: with accounts on, the app pages need a log-in; the homepage and the log-in page don't
  const open = path === "/" || path.startsWith("/login");
  useEffect(() => {
    if (ACCOUNTS && s.ready && s.account === null && !open) router.replace(`/login?next=${encodeURIComponent(path)}`);
  }, [s.ready, s.account, open, path, router]);
  const past = !!s.asOf;
  return (
    <div className={`app ${hasInspector ? "has-inspector" : ""}`}>
      <header className="topbar">
        <Link href="/" className="brand" aria-label="Nodus home">
          <svg viewBox="0 0 24 24" fill="none" stroke="var(--primary-text)" strokeWidth="1.8" aria-hidden><circle cx="5" cy="6" r="2.4" /><circle cx="19" cy="6" r="2.4" /><circle cx="12" cy="18" r="2.4" /><path d="M7 7.2l3.8 8.6M17 7.2l-3.8 8.6M7.4 6h9.2" /></svg>
          Nodus
        </Link>
        <nav className="topnav" aria-label="Main">
          {NAV.map((n) => {
            const active = n.match(path);
            return (
              <Link key={n.href} href={n.href} className={`nav-item ${active ? "active" : ""}`} title={`${n.label}  g ${n.key}`} aria-current={active ? "page" : undefined}>
                {n.label}
                {n.href === "/inbox" && s.pendingCount > 0 && <span className="nav-count" aria-label={`${s.pendingCount} awaiting you`}>{s.pendingCount}</span>}
              </Link>
            );
          })}
        </nav>
        <div className="topbar-tools">
          <button className="search-btn" onClick={() => s.setPaletteOpen(true)} aria-label="Search and commands">
            <Search className="icon-sm" />
            <span>Search</span>
            <kbd>⌘K</kbd>
          </button>
          <LiveStatus />
          <AsOfPill />
          {s.people.length > 0 && <ActingMenu />}
          {ACCOUNTS ? <AccountMenu onReset={() => setResetOpen(true)} /> : <AccessBadge />}
          <ThemeToggle />
          <button className="icon-btn" onClick={() => setHelpOpen(true)} title="Use from your coding agent (MCP)" aria-label="Use from your coding agent (MCP)"><HelpCircle className="icon-sm" /></button>
        </div>
      </header>

      <div className="main">
        {ACCOUNTS && s.account?.demo && (
          <div className="demo-banner" role="status">
            <span>Shared demo workspace: anyone with the demo login sees this data. It&apos;s emptied every night.</span>
            <button type="button" className="composer-chip then" onClick={() => setResetOpen(true)}>Reset workspace</button>
          </div>
        )}
        <div className={`content ${past ? "past" : ""}`}>
          {s.sessionError ? <ApiDown /> : ACCOUNTS && s.workspace?.empty && /^\/(ask|directory|graph|inbox|e\/)/.test(path) ? <EmptyWorkspace /> : children}
        </div>
      </div>

      <Inspector />
      {s.sessionSheetOpen && <SessionSheet onHelp={() => { s.setSessionSheetOpen(false); setHelpOpen(true); }} />}
      {helpOpen && <CodingAgentHelp onClose={() => setHelpOpen(false)} />}
      {s.paletteOpen && <CommandPalette />}
      {resetOpen && <ResetWorkspace onClose={() => setResetOpen(false)} />}
      <Toasts />
    </div>
  );
}

/** "Graph live" once the session is up; never a blocking "Connecting…" (design brief shell). */
function LiveStatus() {
  const s = useStore();
  const state = s.sessionError ? "down" : !s.session ? "wait" : "";
  return (
    <button className={`live-dot ${state}`} onClick={() => s.setSessionSheetOpen(true)} title="Session settings">
      <span>{s.sessionError ? "API unreachable" : !s.session ? "Starting" : "Graph live"}</span>
    </button>
  );
}

/** Sun/moon: Phosphor dark or light (item 24 step 7); also in the account menu and as "Switch theme" in ⌘K. */
function ThemeToggle() {
  const s = useStore();
  const next = s.theme === "dark" ? "light" : "dark";
  return (
    <button className="icon-btn" onClick={() => s.setTheme(next)} title={`Switch to the ${next} theme`} aria-label={`Switch to the ${next} theme`}>
      {s.theme === "dark" ? <Sun className="icon-sm" /> : <Moon className="icon-sm" />}
    </button>
  );
}

/** Empty the workspace: drops its graph (item 24 step 2). Confirmed first, since it can't be undone. */
function ResetWorkspace({ onClose }: { onClose: () => void }) {
  const s = useStore();
  const [busy, setBusy] = useState(false);
  return (
    <Modal title="Empty this workspace?" onClose={onClose} busy={busy} footer={<>
      <Button onClick={onClose} disabled={busy}>Cancel</Button>
      <Button variant="primary" busy={busy} onClick={async () => {
        setBusy(true);
        try {
          await send("POST", "/workspace/reset", {});
          s.setThread([]);
          s.bump();
          s.retrySession();   // the session lived in the dropped graph
          s.toast({ tone: "info", title: "Workspace emptied" });
          onClose();
        } catch (e) {
          s.toast({ tone: "error", title: "Couldn't empty it", body: String((e as Error).message || e) });
        } finally { setBusy(false); }
      }}>Empty workspace</Button>
    </>}>
      <div className="t-small text-2">Every source, fact and answer in {s.account?.demo ? "the shared demo workspace" : "your workspace"} is deleted. This can&apos;t be undone.</div>
    </Modal>
  );
}

/** The account menu (item 24): who is logged in, their workspace, log out. Logged out: a Log in link. */
function AccountMenu({ onReset }: { onReset: () => void }) {
  const s = useStore();
  const router = useRouter();
  if (s.account === undefined) return null;
  if (!s.account) return <Link href="/login" className="pill">Log in</Link>;
  const a = s.account;
  return (
    <Popover
      align="right"
      trigger={({ toggle, open }) => (
        <button className="pill" onClick={toggle} aria-haspopup="menu" aria-expanded={open} title={a.email}>
          <span className="truncate" style={{ maxWidth: 160 }}>{a.demo ? "Demo account" : a.email}</span>
          <ChevronDown className="icon-sm" />
        </button>
      )}
    >
      {(close) => (
        <div className="acct-menu" role="menu">
          <div className="who">
            <span className="t-strong truncate">{a.email}</span>
            <span className="t-small text-3">Workspace {a.workspace}{a.demo ? " · shared demo" : ""}</span>
          </div>
          <div className="divider" />
          <button className="menu-item" role="menuitem" onClick={() => s.setTheme(s.theme === "dark" ? "light" : "dark")}>{s.theme === "dark" ? <Sun className="icon-sm" /> : <Moon className="icon-sm" />}{s.theme === "dark" ? "Light theme" : "Dark theme"}</button>
          <button className="menu-item" role="menuitem" onClick={() => { close(); onReset(); }}><Trash2 className="icon-sm" />Empty this workspace</button>
          <button className="menu-item" role="menuitem" onClick={async () => { close(); await s.logout(); router.push("/"); }}><LogOut className="icon-sm" />Log out</button>
        </div>
      )}
    </Popover>
  );
}

function AccessBadge() {
  const s = useStore();
  if (!s.session) return null;
  return s.session.anonymous ? (
    <button className="access-badge" onClick={() => s.setSessionSheetOpen(true)} title="Paste the write token in Session settings">Read-only · writes need a token</button>
  ) : (
    <button className="access-badge write" onClick={() => s.setSessionSheetOpen(true)} title="Session settings"><KeyRound className="icon-sm" /> Can write</button>
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
          <span className="acting-label">Acting as</span>
          <span className="who truncate" style={{ maxWidth: 160 }}>{me?.name || "…"}</span>
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

/** Session sheet: mode, token, acting person, as-of, debug, reset (DESIGN.md §4.1). */
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
              <input className="input" type="password" placeholder="Paste token" value={tok} onChange={(e) => setTok(e.target.value)} autoComplete="off" data-autofocus />
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
      </div>
      <div className="t-small text-3">Debug panels (raw packs, verifier report) show when the page URL has <code>?debug=1</code>.</div>
      <div className="t-small"><button className="link-btn" onClick={onHelp}>Use from your coding agent (MCP)</button></div>
    </Modal>
  );
}

/** Every app page of an empty workspace (item 24 step 3): one way forward, not an empty table. */
function EmptyWorkspace() {
  return (
    <div className="ask-start"><div className="ask-start-inner">
      <div className="stack" style={{ gap: 10 }}>
        <span className="eyebrow">THIS WORKSPACE IS EMPTY</span>
        <h1 className="ask-start-title">Nothing to show yet</h1>
        <p className="text-2" style={{ margin: 0, fontSize: 16 }}>Answers, owners, decisions and disputes appear once the workspace has a source. Connect one, or load the demo company.</p>
      </div>
      <div><Link href="/start" className="composer-send" style={{ display: "inline-flex" }}>Bring your company&apos;s context</Link></div>
    </div></div>
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
