"use client";

import { BookOpen, Calendar, GitBranch, Inbox, MessageSquare, Search, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { get, qs } from "@/lib/api";
import { labelOf } from "@/lib/format";
import { useStore } from "@/lib/store";
import type { GraphData } from "@/lib/types";

interface Item { id: string; kind: string; title: string; sub?: string; icon: React.ElementType; run: () => void }

/** ⌘K: entities, pages, people to switch to, ask a question. */
export function CommandPalette() {
  const s = useStore();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const [nodes, setNodes] = useState<GraphData["nodes"]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const close = () => s.setPaletteOpen(false);

  useEffect(() => {
    inputRef.current?.focus();
    get<GraphData>(`/graph${qs({ as_of: s.asOf })}`).then((g) => setNodes(g.nodes)).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const items = useMemo<Item[]>(() => {
    const t = q.trim().toLowerCase();
    const pages: Item[] = [
      { id: "p-ask", kind: "Page", title: "Ask", icon: MessageSquare, run: () => router.push("/ask") },
      { id: "p-dir", kind: "Page", title: "Directory", icon: BookOpen, run: () => router.push("/directory") },
      { id: "p-graph", kind: "Page", title: "Graph", icon: GitBranch, run: () => router.push("/graph") },
      { id: "p-inbox", kind: "Page", title: "Inbox", icon: Inbox, run: () => router.push("/inbox") },
      { id: "p-today", kind: "Time", title: "View today", icon: Calendar, run: () => s.setAsOf(null) },
    ];
    const ents: Item[] = nodes
      .filter((n) => !t || n.name.toLowerCase().includes(t) || n.id.includes(t))
      .slice(0, t ? 12 : 6)
      .map((n) => ({ id: n.id, kind: labelOf(n.labels, n.id), title: n.name, sub: n.id, icon: BookOpen, run: () => s.openEntity(n.id, n.name) }));
    const ppl: Item[] = t
      ? s.people.filter((p) => p.name.toLowerCase().includes(t)).slice(0, 4).map((p) => ({ id: `sw-${p.id}`, kind: "Switch", title: `Act as ${p.name}`, sub: p.leads.length ? `Leads ${p.leads.join(", ")}` : p.team.join(", "), icon: UserRound, run: () => { s.setActingAs(p.id); s.toast({ tone: "info", title: `Now acting as ${p.name}` }); } }))
      : [];
    const ask: Item[] = t.length > 2 ? [{ id: "ask", kind: "Ask", title: `Ask “${q.trim()}”`, icon: MessageSquare, run: () => router.push(`/ask${qs({ q: q.trim() })}`) }] : [];
    const pg = pages.filter((p) => !t || p.title.toLowerCase().includes(t));
    return [...ents, ...ppl, ...ask, ...pg];
  }, [q, nodes, s, router]);

  useEffect(() => setSel(0), [q]);

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setSel((i) => Math.min(items.length - 1, i + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setSel((i) => Math.max(0, i - 1)); }
    else if (e.key === "Enter") { e.preventDefault(); const it = items[sel]; if (it) { it.run(); close(); } }
    else if (e.key === "Escape") { close(); }
  };

  return (
    <div className="modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) close(); }}>
      <div className="modal cmdk" role="dialog" aria-modal="true" aria-label="Search and commands" onKeyDown={onKey}>
        <div className="cmdk-input">
          <Search className="icon-sm text-3" />
          <input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search entities, people, pages, or type a question…" aria-label="Search" />
          <kbd>esc</kbd>
        </div>
        <div className="cmdk-list" role="listbox">
          {items.map((it, i) => {
            const Icon = it.icon;
            return (
              <button key={it.id} className="menu-item" role="option" aria-selected={i === sel} onMouseEnter={() => setSel(i)} onClick={() => { it.run(); close(); }}>
                <Icon className="icon-sm text-3" />
                <span className="kind">{it.kind}</span>
                <span className="truncate">{it.title}</span>
                {it.sub && <span className="meta truncate">{it.sub}</span>}
              </button>
            );
          })}
          {!items.length && <div className="t-small text-3" style={{ padding: 12 }}>Nothing matches.</div>}
        </div>
      </div>
    </div>
  );
}
