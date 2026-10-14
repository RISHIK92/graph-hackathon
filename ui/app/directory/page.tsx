"use client";

import { ArrowDown, ArrowUp, BookOpen, ChevronRight, Flag, Inbox, Search, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Button, Chip, DisputeFlag, Empty, EntityLink, ErrorState, SkeletonRows, Status, Tabs } from "@/components/ui";
import { qs } from "@/lib/api";
import { fmtDate, plural } from "@/lib/format";
import { useApi, useStore } from "@/lib/store";
import type { DirRef, Directory } from "@/lib/types";

const TABS = [
  { id: "teams", label: "Teams" }, { id: "systems", label: "Systems" }, { id: "people", label: "People" },
  { id: "projects", label: "Projects" }, { id: "decisions", label: "Decisions" }, { id: "tickets", label: "Tickets" },
];

export default function DirectoryPage() {
  return <Suspense fallback={null}><DirectoryInner /></Suspense>;
}

function DirectoryInner() {
  const s = useStore();
  const router = useRouter();
  const params = useSearchParams();
  const tab = params.get("tab") || "teams";
  const [q, setQ] = useState("");
  const [onlyDisputed, setOnlyDisputed] = useState(false);
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 }>({ key: "name", dir: 1 });
  const { data, error, loading, reload } = useApi<Directory>(`/directory${qs({ as_of: s.asOf })}`);
  const setTab = (t: string) => router.replace(`/directory${qs({ tab: t === "teams" ? "" : t })}`);

  const counts = data ? { teams: data.teams.length, systems: data.systems.length, people: data.people.length, projects: data.projects.length, decisions: data.decisions.length, tickets: data.tickets.length } : {};
  const pendingStrip = !s.session?.anonymous && s.pendingCount > 0;

  return (
    <div className="page">
      <PageHeader
        title="Directory"
        description="Who owns what, who leads whom, and what depends on what, at the chosen date."
        meta={data ? <span>{plural(data.teams.length, "team")} · {plural(data.systems.length, "system")} · {plural(data.people.length, "person", "people")}</span> : null}
        tabs={<Tabs value={tab} onChange={setTab} tabs={TABS.map((t) => ({ ...t, count: (counts as Record<string, number>)[t.id] }))} />}
      />
      <div className="page-body">
        {pendingStrip && (
          <div className="card-tight row">
            <Inbox className="icon-sm text-2" />
            <span className="t-small"><strong>{plural(s.pendingCount, "item")}</strong> pending for {s.personName(s.actingAs)}.</span>
            <Button size="sm" variant="link" className="right" onClick={() => router.push("/inbox")}>Open inbox</Button>
          </div>
        )}
        <div className="toolbar">
          <div className="input-wrap" style={{ width: 280 }}>
            <Search />
            <input className="input" placeholder={`Filter ${tab}…`} value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter" />
          </div>
          <Button size="sm" variant={onlyDisputed ? "primary" : "secondary"} icon={Flag} onClick={() => setOnlyDisputed((v) => !v)} aria-pressed={onlyDisputed}>Disputed only</Button>
          {(q || onlyDisputed) && <Button size="sm" variant="ghost" icon={X} onClick={() => { setQ(""); setOnlyDisputed(false); }}>Clear</Button>}
          {data && <span className="result-count">{plural((counts as Record<string, number>)[tab] || 0, "row")}</span>}
        </div>
        {error && <ErrorState message={error} onRetry={reload} />}
        {!data && !error && <div className="table-wrap"><SkeletonRows n={8} /></div>}
        {data && (
          <DirTable key={tab} tab={tab} data={data} q={q.trim().toLowerCase()} onlyDisputed={onlyDisputed} sort={sort} setSort={setSort} loading={loading} onClear={() => { setQ(""); setOnlyDisputed(false); }} />
        )}
      </div>
    </div>
  );
}

type Row = Record<string, unknown> & { id: string; name: string; disputed?: boolean };
interface Col { key: string; label: string; num?: boolean; width?: number; render: (r: Row) => React.ReactNode; sortValue?: (r: Row) => string | number }

function refs(xs: DirRef[] | undefined, max = 3) {
  if (!xs?.length) return <span className="cell-muted">—</span>;
  return (
    <span className="row" style={{ gap: 6 }}>
      {xs.slice(0, max).map((x, i) => <span key={x.id} className="row" style={{ gap: 6 }}>{i > 0 && <span className="text-3">·</span>}<EntityLink id={x.id} name={x.name} disputed={x.disputed} /></span>)}
      {xs.length > max && <Chip tone="neutral">+{xs.length - max}</Chip>}
    </span>
  );
}
function ref(x: DirRef | null | undefined, empty = "—") {
  return x ? <EntityLink id={x.id} name={x.name} disputed={x.disputed} /> : <span className="cell-muted">{empty}</span>;
}

function DirTable({ tab, data, q, onlyDisputed, sort, setSort, loading, onClear }: {
  tab: string; data: Directory; q: string; onlyDisputed: boolean; sort: { key: string; dir: 1 | -1 }; setSort: (s: { key: string; dir: 1 | -1 }) => void; loading: boolean; onClear: () => void;
}) {
  const s = useStore();
  const cols: Col[] = useMemo(() => {
    switch (tab) {
      case "teams": return [
        { key: "name", label: "Team", render: (r) => <span className="cell-primary"><EntityLink id={r.id} name={r.name} /></span> },
        { key: "lead", label: "Lead", render: (r) => (r.leads as DirRef[]).length ? refs(r.leads as DirRef[]) : <span className="placeholder t-small">No current lead</span>, sortValue: (r) => (r.leads as DirRef[])[0]?.name || "" },
        { key: "members", label: "Members", num: true, render: (r) => (r.members as DirRef[]).length, sortValue: (r) => (r.members as DirRef[]).length },
        { key: "owns", label: "Owns", render: (r) => refs(r.owns as DirRef[], 4), sortValue: (r) => (r.owns as DirRef[]).length },
        { key: "disputes", label: "Disputes", num: true, render: (r) => { const n = (r.owns as DirRef[]).filter((x) => x.disputed).length + (r.leads as DirRef[]).filter((x) => x.disputed).length; return n ? <Chip tone="error" icon={Flag}>{n}</Chip> : <span className="cell-muted">0</span>; }, sortValue: (r) => (r.owns as DirRef[]).filter((x) => x.disputed).length },
      ];
      case "systems": return [
        { key: "name", label: "System", render: (r) => <span className="cell-primary"><EntityLink id={r.id} name={r.name} />{r.disputed ? <DisputeFlag /> : null}</span> },
        { key: "owner", label: "Owner", render: (r) => ref(r.owner as DirRef | null, "No owner"), sortValue: (r) => (r.owner as DirRef | null)?.name || "" },
        { key: "project", label: "Project", render: (r) => ref(r.project as DirRef | null), sortValue: (r) => (r.project as DirRef | null)?.name || "" },
        { key: "depends_on", label: "Depends on", num: true, render: (r) => r.depends_on as number, sortValue: (r) => r.depends_on as number },
        { key: "depended_on_by", label: "Depended on by", num: true, render: (r) => r.depended_on_by as number, sortValue: (r) => r.depended_on_by as number },
        { key: "decisions", label: "Decisions", num: true, render: (r) => r.decisions as number, sortValue: (r) => r.decisions as number },
      ];
      case "people": return [
        { key: "name", label: "Name", render: (r) => <span className="cell-primary"><EntityLink id={r.id} name={r.name} /></span> },
        { key: "title", label: "Title", render: (r) => (r.title as string) || <span className="cell-muted">—</span>, sortValue: (r) => (r.title as string) || "" },
        { key: "team", label: "Team", render: (r) => ref(r.team as DirRef | null), sortValue: (r) => (r.team as DirRef | null)?.name || "" },
        { key: "leads", label: "Leads", render: (r) => refs(r.leads as DirRef[]), sortValue: (r) => (r.leads as DirRef[]).length },
        { key: "decides", label: "Decides", render: (r) => refs(r.decides as DirRef[]), sortValue: (r) => (r.decides as DirRef[]).length },
        { key: "tickets", label: "Tickets", num: true, render: (r) => r.tickets as number, sortValue: (r) => r.tickets as number },
      ];
      case "projects": return [
        { key: "name", label: "Project", render: (r) => <span className="cell-primary"><EntityLink id={r.id} name={r.name} />{r.disputed ? <DisputeFlag /> : null}</span> },
        { key: "owner", label: "Owner", render: (r) => ref(r.owner as DirRef | null, "No owner"), sortValue: (r) => (r.owner as DirRef | null)?.name || "" },
        { key: "systems", label: "Systems", render: (r) => refs(r.systems as DirRef[], 4), sortValue: (r) => (r.systems as DirRef[]).length },
        { key: "people", label: "People", num: true, render: (r) => r.people as number, sortValue: (r) => r.people as number },
      ];
      case "decisions": return [
        { key: "name", label: "Id", width: 96, render: (r) => <span className="cell-primary"><EntityLink id={r.id} name={r.name} /></span> },
        { key: "title", label: "Title", render: (r) => <span className="wrap">{(r.title as string) || ""}</span>, sortValue: (r) => (r.title as string) || "" },
        { key: "status", label: "Status", render: (r) => <Status status={(r.status as string) || "unknown"} />, sortValue: (r) => (r.status as string) || "" },
        { key: "decided_at", label: "Decided", render: (r) => <span className="cell-mono">{r.decided_at ? fmtDate(r.decided_at as number) : "—"}</span>, sortValue: (r) => (r.decided_at as number) || 0 },
        { key: "deciders", label: "Deciders", render: (r) => refs(r.deciders as DirRef[], 2), sortValue: (r) => (r.deciders as DirRef[])[0]?.name || "" },
        { key: "affects", label: "Affects", render: (r) => refs(r.affects as DirRef[]), sortValue: (r) => (r.affects as DirRef[])[0]?.name || "" },
        { key: "replaces", label: "Replaces", render: (r) => { const rep = r.replaces as DirRef[]; const by = r.replaced_by as DirRef[]; return <span className="row" style={{ gap: 6 }}>{refs(rep, 2)}{by.length ? <Chip tone="neutral">Replaced by {by.map((b) => b.name).join(", ")}</Chip> : null}</span>; } },
      ];
      case "tickets": return [
        { key: "name", label: "Id", width: 96, render: (r) => <span className="cell-primary"><EntityLink id={r.id} name={r.name} />{r.disputed ? <DisputeFlag /> : null}</span> },
        { key: "description", label: "Title", render: (r) => <span className="wrap">{(r.description as string) || ""}</span>, sortValue: (r) => (r.description as string) || "" },
        { key: "about", label: "About", render: (r) => ref(r.about as DirRef | null), sortValue: (r) => (r.about as DirRef | null)?.name || "" },
        { key: "assignee", label: "Assigned to", render: (r) => ref(r.assignee as DirRef | null, "Unassigned"), sortValue: (r) => (r.assignee as DirRef | null)?.name || "" },
        { key: "state", label: "State", render: (r) => r.state ? <Chip tone={r.state === "open" ? "accent" : "neutral"}>{String(r.state).replace(/^\w/, (c) => c.toUpperCase())}</Chip> : <span className="cell-muted">—</span>, sortValue: (r) => (r.state as string) || "" },
      ];
      default: return [];
    }
  }, [tab]);

  const rows = useMemo(() => {
    let xs = ((data as unknown as Record<string, Row[]>)[tab] || []) as Row[];
    if (q) xs = xs.filter((r) => JSON.stringify(r).toLowerCase().includes(q));
    if (onlyDisputed) xs = xs.filter((r) => r.disputed || (r.owns as DirRef[] | undefined)?.some((x) => x.disputed) || (r.leads as DirRef[] | undefined)?.some((x) => x.disputed));
    const col = cols.find((c) => c.key === sort.key);
    const sv = col?.sortValue || ((r: Row) => r.name);
    return [...xs].sort((a, b) => { const x = sv(a), y = sv(b); return (x < y ? -1 : x > y ? 1 : 0) * sort.dir; });
  }, [data, tab, q, onlyDisputed, sort, cols]);

  const selectedId = s.inspector.find((v) => v.kind === "entity")?.kind === "entity" ? (s.inspector[s.inspector.length - 1] as { kind: string; id?: string }).id : undefined;

  return (
    <div className="table-wrap" aria-busy={loading}>
      <table className="table">
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c.key} className={`${c.num ? "num" : ""} sortable`} style={c.width ? { width: c.width } : undefined} onClick={() => setSort({ key: c.key, dir: sort.key === c.key ? (sort.dir === 1 ? -1 : 1) : 1 })} aria-sort={sort.key === c.key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
                <span className="sort">{c.label}{sort.key === c.key && (sort.dir === 1 ? <ArrowUp className="icon-sm" /> : <ArrowDown className="icon-sm" />)}</span>
              </th>
            ))}
            <th style={{ width: 32 }} aria-label="Open" />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className={`clickable ${selectedId === r.id ? "selected" : ""}`} onClick={() => s.openEntity(r.id, r.name)}>
              {cols.map((c) => <td key={c.key} className={c.num ? "num" : ""}>{c.render(r)}</td>)}
              <td><ChevronRight className="icon-sm chev" /></td>
            </tr>
          ))}
          {!rows.length && (
            <tr><td colSpan={cols.length + 1}>
              <Empty icon={BookOpen} title={q || onlyDisputed ? `No ${tab} match` : `No ${tab} in this seed`} action={(q || onlyDisputed) ? <Button size="sm" onClick={onClear}>Clear filters</Button> : undefined}>
                {q || onlyDisputed ? "Try a different filter." : "The world has nothing of this type yet."}
              </Empty>
            </td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
