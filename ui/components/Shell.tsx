"use client";

import { AlertCircle, Calendar, ChevronDown, ChevronUp, Compass, HelpCircle, Inbox, KeyRound, LogOut, MessageSquare, Moon, PanelLeftClose, PanelLeftOpen, Plug, Search, Settings2, Sun, Terminal, Trash2, UserRound, X, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  { href: "/sources", label: "Sources", key: "s" },
];
const NAV = [
  { href: "/", label: "Home", key: "o", match: (p: string) => p === "/" },
  { href: "/ask", label: "Ask", key: "a", match: (p: string) => p.startsWith("/ask") },
  { href: "/explore", label: "Explore", key: "x", match: (p: string) => /^\/(explore|directory|graph|e\/)/.test(p) },
  { href: "/inbox", label: "Inbox", key: "i", match: (p: string) => p.startsWith("/inbox") },
];
// The signed-in app rail (navbar brief, direction C): the header's pages plus Sources
const RAIL = [...NAV.slice(1), { href: "/sources", label: "Sources", key: "s", match: (p: string) => p.startsWith("/sources") }];
const RAIL_ICONS: Record<string, LucideIcon> = { "/ask": MessageSquare, "/explore": Compass, "/inbox": Inbox, "/sources": Plug };
const RAIL_KEY = "nodus.rail";
const SHARED_NOTE = "Anyone with the demo login sees this data. Emptied every night.";

/** The rail's collapsed state: the saved preference, except on Explore (and Graph and Directory), which start collapsed and keep an
 * expand only until the user leaves it. */
function useRail(path: string): [boolean, () => void] {
  const onExplore = /^\/(explore|graph|directory)/.test(path);   // the pages the rail lights as Explore
  const [saved, setSaved] = useState(false);
  const [exploreOpen, setExploreOpen] = useState(false);
  useEffect(() => {
    let v: string | null = null;
    try { v = localStorage.getItem(RAIL_KEY); } catch { v = null; }
    setSaved(v ? v === "collapsed" : window.innerWidth < 1100);
  }, []);
  useEffect(() => { if (!onExplore) setExploreOpen(false); }, [onExplore]);
  const toggle = useCallback(() => {
    if (onExplore) { setExploreOpen((o) => !o); return; }
    setSaved((c) => {
      try { localStorage.setItem(RAIL_KEY, c ? "expanded" : "collapsed"); } catch { /* a blocked store keeps it per visit */ }
      return !c;
    });
  }, [onExplore]);
  return [onExplore ? !exploreOpen : saved, toggle];
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const s = useStore();
  const hasInspector = s.inspector.length > 0;
  const [helpOpen, setHelpOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const { inspectorPinned, closeInspector, pendingCount } = s;
  const [collapsed, toggleRail] = useRail(path);
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
      if (e.key === "[" && ACCOUNTS && s.account) { e.preventDefault(); toggleRail(); return; }
      if (e.key === "/") { e.preventDefault(); s.setPaletteOpen(true); return; }
      if (e.key === "g") { pendingG = Date.now(); return; }
      if (pendingG && Date.now() - pendingG < 800) {
        const n = JUMPS.find((x) => x.key === e.key);
        if (n) { e.preventDefault(); router.push(n.href); }
        pendingG = 0;
      }
    };
    document.addEventListener("keydown", onKey);
    window.addEventListener("nodus:toggle-rail", toggleRail);
    return () => { document.removeEventListener("keydown", onKey); window.removeEventListener("nodus:toggle-rail", toggleRail); };
  }, [s, router, toggleRail]);

  // item 24: with accounts on, the app pages need a log-in; the homepage and the log-in page don't. Once
  // logged in, Ask is home (user decision): the marketing homepage is for visitors only.
  const open = path === "/" || path.startsWith("/login");
  const signedIn = ACCOUNTS && !!s.account;
  useEffect(() => {
    if (ACCOUNTS && s.ready && s.account === null && !open) router.replace(`/login?next=${encodeURIComponent(path)}`);
    if (signedIn && path === "/") router.replace("/ask");
  }, [s.ready, s.account, open, signedIn, path, router]);
  const past = !!s.asOf;
  const ws = s.account?.demo ? "Demo workspace" : "Your workspace";
  const page = RAIL.find((n) => n.match(path))?.label || JUMPS.find((n) => n.href !== "/" && path.startsWith(n.href))?.label || (path.startsWith("/start") ? "Get started" : path.startsWith("/s/") ? "Source" : "");
  return (
    <div className={`app ${signedIn ? "has-rail" : ""} ${hasInspector ? "has-inspector" : ""}`}>
      {signedIn ? (
        <Rail collapsed={collapsed} onToggle={toggleRail} workspace={ws} onHelp={() => setHelpOpen(true)} onReset={() => setResetOpen(true)} />
      ) : (
      <header className="topbar">
        <Link href="/" className="brand" aria-label="Nodus home">
          <Mark />
          Nodus
        </Link>
        <nav className="topnav" aria-label="Main">
          {NAV.map((n) => {
            const active = n.match(path);
            return (
              <Link key={n.href} href={n.href} className={`nav-item ${active ? "active" : ""}`} title={`${n.label}  g ${n.key}`} aria-current={active ? "page" : undefined}>
                {n.label}
                {n.href === "/inbox" && s.pendingCount > 0 && (!ACCOUNTS || s.account) && <span className="nav-count" aria-label={`${s.pendingCount} awaiting you`}>{s.pendingCount}</span>}
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
          {s.people.length > 0 && (!ACCOUNTS || s.account) && <ActingMenu />}
          {ACCOUNTS ? s.account === null && <Link href="/login" className="pill">Log in</Link> : <AccessBadge />}
          <ThemeToggle />
          <button className="icon-btn" onClick={() => setHelpOpen(true)} title="Use from your coding agent (MCP)" aria-label="Use from your coding agent (MCP)"><HelpCircle className="icon-sm" /></button>
        </div>
      </header>
      )}

      <div className="main">
        {signedIn && (
          <div className="railbar">
            <span className="crumb">{ws}{page && <> / <b>{page}</b></>}</span>
            <button className="search-btn" onClick={() => s.setPaletteOpen(true)} aria-label="Search and commands">
              <Search className="icon-sm" />
              <span>Search or jump to…</span>
              <kbd>⌘K</kbd>
            </button>
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

function Mark() {
  return <svg viewBox="0 0 24 24" fill="none" stroke="var(--primary-text)" strokeWidth="1.8" aria-hidden><circle cx="5" cy="6" r="2.4" /><circle cx="19" cy="6" r="2.4" /><circle cx="12" cy="18" r="2.4" /><path d="M7 7.2l3.8 8.6M17 7.2l-3.8 8.6M7.4 6h9.2" /></svg>;
}

/** The signed-in app rail (navbar brief, direction C): workspace, pages, the lens (as-of and acting person),
 * the coding-agent hint and the account. Collapsed, it shows icons with tooltips. */
function Rail({ collapsed, onToggle, workspace, onHelp, onReset }: { collapsed: boolean; onToggle: () => void; workspace: string; onHelp: () => void; onReset: () => void }) {
  const path = usePathname();
  const s = useStore();
  const shared = !!s.account?.demo && !!s.workspace && !s.workspace.empty;
  const tip = (t: string) => (collapsed ? t : undefined);
  return (
    <aside className={`rail ${collapsed ? "collapsed" : ""}`}>
      <div className="rail-ws" title={shared ? SHARED_NOTE : undefined}>
        <Link href="/ask" className="rail-ws-name" aria-label={`${workspace}, Ask`} title={tip(workspace)}>
          <Mark />
          <span className="rail-label truncate">{workspace}</span>
        </Link>
        <div className="rail-ws-status">
          <LiveStatus />
          {shared && <span className="rail-shared" title={SHARED_NOTE}>SHARED</span>}
        </div>
      </div>
      <nav className="rail-nav" aria-label="Main">
        {RAIL.map((n) => {
          const active = n.match(path);
          const Icon = RAIL_ICONS[n.href];
          const count = n.href === "/inbox" ? s.pendingCount : 0;
          const tid = `rail-${n.href.slice(1)}`;
          return (
            <Link key={n.href} href={n.href} data-testid={tid} className={`rail-item ${active ? "active" : ""}`} aria-current={active ? "page" : undefined}
              aria-label={count ? `${n.label}, ${count} awaiting you` : n.label} title={collapsed ? `${n.label}  g ${n.key}` : undefined}>
              <Icon />
              <span className="rail-label">{n.label}</span>
              {count > 0 ? <span className="rail-count r">{count}</span> : <kbd className="rail-label r">g {n.key}</kbd>}
            </Link>
          );
        })}
      </nav>
      <div className="rail-section">
        <span className="rail-heading">LENS</span>
        <AsOfPill rail={collapsed ? "collapsed" : "open"} />
        {s.people.length > 0 && <ActingMenu rail={collapsed ? "collapsed" : "open"} />}
      </div>
      <span className="rail-spacer" />
      <div className="rail-section">
        <button className="rail-item" data-testid="rail-mcp" onClick={onHelp} aria-label="Connect your coding agent (MCP)" title={tip("Connect your coding agent (MCP)")}>
          <Terminal />
          <span className="rail-label">Connect your coding agent</span>
          <span className="rail-mcp rail-label r">MCP</span>
        </button>
        <button className="rail-item" data-testid="rail-toggle" onClick={onToggle} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed} title={collapsed ? "Expand sidebar  [" : undefined}>
          {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
          <span className="rail-label">Collapse sidebar</span>
          <kbd className="rail-label r">[</kbd>
        </button>
      </div>
      <AccountMenu onReset={onReset} collapsed={collapsed} />
    </aside>
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

/** A full load of the homepage: the log-in guard can't race it to /login, and no workspace state (people,
 * Inbox count, thread) outlives the account. */
async function logOut(logout: () => Promise<void>) {
  await logout();
  window.location.assign("/");
}

function AccountMenu({ onReset, collapsed }: { onReset: () => void; collapsed: boolean }) {
  const s = useStore();
  if (!s.account) return null;
  const a = s.account;
  const name = a.demo ? "Demo account" : a.email;
  // the account menu (item 24): who is logged in, their workspace, the theme, log out
  return (
    <div className="rail-foot">
    <Popover
      align="side"
      trigger={({ toggle, open }) => (
        <button className="rail-acct" onClick={toggle} aria-haspopup="menu" aria-expanded={open} aria-label={`${name}: account menu`} title={collapsed ? name : a.email}>
          <span className="avatar">{a.demo ? "DA" : initials(a.email.split("@")[0].replace(/[._-]+/g, " "))}</span>
          <span className="rail-acct-text rail-label">
            <span className="truncate">{name}</span>
            <span className="t-small text-3">Theme, workspace, log out</span>
          </span>
          <ChevronUp className="icon-sm rail-label r" />
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
          {s.workspace && !s.workspace.empty && <button className="menu-item danger" role="menuitem" onClick={() => { close(); onReset(); }}><Trash2 className="icon-sm" />Empty this workspace</button>}
          <button className="menu-item" role="menuitem" onClick={() => { close(); void logOut(s.logout); }}><LogOut className="icon-sm" />Log out</button>
        </div>
      )}
    </Popover>
    </div>
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
function AsOfPill({ rail }: { rail?: "open" | "collapsed" }) {
  const s = useStore();
  const [open, setOpen] = useState(false);
  const label = s.asOf ? `As of ${fmtDate(s.asOf)}` : "Today";
  return (
    <Popover
      align={rail ? "side" : "right"}
      open={open}
      onOpenChange={setOpen}
      trigger={({ toggle }) => rail ? (
        <button className={`rail-item lens ${s.asOf ? "warn" : ""}`} data-testid="as-of-button" onClick={toggle} aria-haspopup="dialog" aria-expanded={open}
          aria-label={`${label}: show the organisation as it was on a date`} title={rail === "collapsed" ? label : "Show the organisation as it was on a date"}>
          <Calendar />
          <span className="rail-label">{label}</span>
          {s.asOf && <span className="x rail-label r" role="button" data-testid="as-of-clear" aria-label="Back to today" onClick={(e) => { e.stopPropagation(); s.setAsOf(null); s.toast({ tone: "info", title: "Viewing today" }); }}><X className="icon-sm" /></span>}
        </button>
      ) : (
        <button className={`pill ${s.asOf ? "warn" : ""}`} data-testid="as-of-button" onClick={toggle} aria-haspopup="dialog" aria-expanded={open} title="Show the organisation as it was on a date">
          <Calendar className="icon-sm" />
          {s.asOf ? `As of ${fmtDate(s.asOf)}` : "Today"}
          {s.asOf ? (
            <span className="x" role="button" data-testid="as-of-clear" aria-label="Back to today" onClick={(e) => { e.stopPropagation(); s.setAsOf(null); s.toast({ tone: "info", title: "Viewing today" }); }}><X className="icon-sm" /></span>
          ) : <ChevronDown className="icon-sm" />}
        </button>
      )}
    >
      {(close) => (
        <div className="stack-3" style={{ padding: 8, width: 280 }}>
          <Field label="View the organisation as of" help="Owners, leads and teams are shown as they were on this date.">
            <input className="input" type="date" data-testid="as-of-input" value={dateInputValue(s.asOf)} onChange={(e) => s.setAsOf(fromDateInput(e.target.value))} />
          </Field>
          <div className="row">
            <Button size="sm" data-testid="as-of-today" onClick={() => { s.setAsOf(null); close(); }}>Today</Button>
            <Button size="sm" variant="primary" className="right" data-testid="as-of-done" onClick={close}>Done</Button>
          </div>
        </div>
      )}
    </Popover>
  );
}

function ActingMenu({ rail }: { rail?: "open" | "collapsed" }) {
  const s = useStore();
  const me = s.people.find((p) => p.id === s.actingAs);
  const [q, setQ] = useState("");
  const list = useMemo(() => s.people.filter((p) => !q || p.name.toLowerCase().includes(q.toLowerCase()) || p.leads.some((l) => l.toLowerCase().includes(q.toLowerCase()))), [s.people, q]);
  return (
    <Popover
      align={rail ? "side" : "right"}
      trigger={({ toggle, open }) => rail ? (
        <button className="rail-item lens" data-testid="acting-as-button" onClick={toggle} aria-haspopup="menu" aria-expanded={open} aria-label={`Acting as ${me?.name || "…"}`}
          title={rail === "collapsed" ? `Acting as ${me?.name || "…"}` : "Acting as (demo identity, not authentication)"}>
          <span className="avatar">{me ? initials(me.name) : "…"}</span>
          <span className="rail-label truncate">Acting as <span className="who">{me?.name || "…"}</span></span>
        </button>
      ) : (
        <button className="pill" data-testid="acting-as-button" onClick={toggle} aria-haspopup="menu" aria-expanded={open} title="Acting as (demo identity, not authentication)">
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
            <div className="input-wrap"><Search /><input className="input sm" data-testid="acting-as-search" placeholder="Switch person…" value={q} onChange={(e) => setQ(e.target.value)} autoFocus
              onKeyDown={async (e) => { if (e.key === "Enter" && list[0]) { e.preventDefault(); close(); await s.setActingAs(list[0].id); s.toast({ tone: "info", title: `Now acting as ${list[0].name}` }); } }} /></div>
          </div>
          <div style={{ maxHeight: 280, overflow: "auto" }} role="menu">
            {list.map((p) => (
              <button key={p.id} data-testid={`acting-as-option-${p.id.replace(/^person:/, "")}`} className={`menu-item ${p.id === s.actingAs ? "active" : ""}`} role="menuitem" onClick={async () => { close(); await s.setActingAs(p.id); s.toast({ tone: "info", title: `Now acting as ${p.name}` }); }}>
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
      <div><Link href="/start" data-testid="bring-context" className="composer-send" style={{ display: "inline-flex" }}>Bring your company&apos;s context</Link></div>
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
