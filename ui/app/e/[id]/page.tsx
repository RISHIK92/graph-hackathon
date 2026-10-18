"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo } from "react";
import { disputesOf, EntityActions, EntityDisputes, EntityHistory, EntitySources, EntitySummary, useEntity } from "@/components/EntityPanel";
import { Button, Empty, ErrorState, Skeleton, Tabs } from "@/components/ui";
import { qs } from "@/lib/api";
import { fmtDate, labelOf } from "@/lib/format";
import { useStore } from "@/lib/store";
import type { Fact, Pack } from "@/lib/types";

export default function EntityPage() {
  return <Suspense fallback={null}><EntityInner /></Suspense>;
}

function EntityInner() {
  const { id: raw } = useParams<{ id: string }>();
  const id = decodeURIComponent(raw);
  const router = useRouter();
  const params = useSearchParams();
  const tab = params.get("tab") || "overview";
  const setTab = (t: string) => router.replace(`/e/${encodeURIComponent(id)}${qs({ tab: t === "overview" ? "" : t })}`);
  const s = useStore();
  const { data, error, reload } = useEntity(id);
  const disputes = disputesOf(data, id).length;
  const notFound = error && /404|not found/i.test(error);
  const kind = id.split(":")[0];
  // the owner and its lead now, the systems that break with it, and every dated change (design brief step 5)
  const facts = (p?: Pack | null) => (p?.items || []).flatMap((it) => it.facts);
  const owns = facts(data?.owner).find((f) => f.predicate === "OWNS" && f.object_id === id && ["current", "disputed"].includes(f.status));
  const lead = facts(data?.owner).find((f) => f.predicate === "LEADS" && owns && f.object_id === owns.subject_id);
  // an impact path runs from this system through what depends on it to who to tell; the systems are the affected
  const affected = useMemo(() => [...new Map((data?.depended_on_by?.items || []).flatMap((it) => it.path?.steps || []).map((st) => st.node)
    .filter((n) => n.id !== id && n.labels.some((l) => l === "System" || l === "Project")).map((n) => [n.id, n])).values()], [data, id]);
  const history = useMemo(() => Object.values(data?.history || {}).flatMap((p) => facts(p)).filter((f) => f.valid_from > 0)
    .sort((a, b) => b.valid_from - a.valid_from).filter((f, i, xs) => xs.findIndex((x) => x.assertion_id === f.assertion_id) === i).slice(0, 8), [data]);
  // "Before" only when the owner changed: the day before the current owner's start, when an earlier one held it
  const changed = owns?.valid_from || 0;
  const hadEarlier = facts(data?.history?.OWNS).some((f) => f.object_id === id && f.status === "superseded");
  const before = hadEarlier && changed > 86_400_000 ? changed - 86_400_000 : null;
  useEffect(() => { if (data?.name) document.title = `${data.name} · Nodus`; }, [data?.name]);

  const name = data?.name || "";
  return (
    <div className="page">
      <div className="entity-head">
        <nav aria-label="Breadcrumb" className="t-small text-3"><Link href={`/explore${qs({ id })}`}>Explore</Link> / {labelOf(data?.labels, id)}{name ? ` / ${name}` : ""}</nav>
        <div className="row-wrap" style={{ justifyContent: "space-between", alignItems: "flex-end", gap: 20 }}>
          <div className="stack" style={{ gap: 8 }}>
            <span className={`entity-kind ${kind === "system" || kind === "project" ? "sys" : kind === "team" || kind === "person" ? "per" : "rec"}`}>{labelOf(data?.labels, id).toUpperCase()}</span>
            <h1>{name || (notFound ? "Not found" : <Skeleton w={200} h={36} />)}</h1>
            {owns && (
              <span className="text-2">Owned by <span className="e-per">{owns.statement.split(" owns ")[0]}</span>
                {lead ? <> · led by <span className="e-per">{lead.statement.split(" leads ")[0]}</span></> : null}
                {affected.length ? ` · ${affected.length} ${affected.length === 1 ? "system depends" : "systems depend"} on it` : ""}</span>
            )}
            {data?.d && !owns && <span className="text-2">{data.d}</span>}
          </div>
          <div className="row-wrap" style={{ gap: 8 }}>
            {before && (
              <div className="seg" role="group" aria-label="View as of">
                <button type="button" data-testid="entity-as-of-before" className={s.asOf ? "on" : ""} onClick={() => s.setAsOf(before)}>Before {fmtDate(changed)}</button>
                <button type="button" data-testid="entity-as-of-today" className={!s.asOf ? "on" : ""} onClick={() => s.setAsOf(null)}>Today</button>
              </div>
            )}
            {data && <EntityActions data={data} id={id} inPage />}
          </div>
        </div>
        {data && disputes > 0 && (
          <Link href="/inbox" className="entity-dispute">
            <i /><span><strong>{disputes === 1 ? "A fact here is disputed." : `${disputes} facts here are disputed.`}</strong> The record stays until someone eligible settles it.</span>
            <span className="go">Settle in Inbox →</span>
          </Link>
        )}
        {data && <Tabs value={tab} onChange={setTab} tabs={[
          { id: "overview", label: "Overview" },
          { id: "history", label: "History", count: Object.values(data.history || {}).reduce((n, p) => n + p.items.length, 0) || undefined },
          { id: "sources", label: "Sources", count: data.sources?.reduce((n, g) => n + g.sources.length, 0) || undefined },
          { id: "disputes", label: "Disputes", count: disputes || undefined },
        ]} />}
      </div>
      <div className="page-body entity-body">
        <div className="entity-main">
          {notFound && <Empty icon={Search} title="No entity with this id" action={<Button size="sm" onClick={() => s.setPaletteOpen(true)}>Search</Button>}>{id}</Empty>}
          {error && !notFound && <ErrorState message={error} onRetry={reload} />}
          {!data && !error && <div className="stack-3"><Skeleton h={36} /><Skeleton h={36} /><Skeleton h={120} /></div>}
          {data && tab === "overview" && <EntitySummary data={data} id={id} full />}
          {data && tab === "history" && <EntityHistory data={data} />}
          {data && tab === "sources" && <EntitySources data={data} />}
          {data && tab === "disputes" && <EntityDisputes data={data} id={id} />}
        </div>
        {data && (
          <aside className="entity-side">
            {(kind === "system" || kind === "project") && (
              <section className="side-card">
                <span className="eyebrow disp">IF {name.toUpperCase()} GOES DOWN</span>
                <span className="t-strong" style={{ fontSize: 18 }}>{affected.length ? `${affected.length} ${affected.length === 1 ? "system is" : "systems are"} affected` : "Nothing depends on it"}</span>
                {affected.length > 0 && <div className="row-wrap">{affected.map((n) => <Link key={n.id} href={`/e/${encodeURIComponent(n.id)}`} className="ent sys">{n.name}</Link>)}</div>}
                <Link href={`/ask${qs({ q: `What breaks if ${name} goes down, and who do I tell?`, send: "1" })}`} className="home-link">Who to tell →</Link>
              </section>
            )}
            {history.length > 0 && (
              <section className="stack" style={{ gap: 10 }}>
                <span className="eyebrow">HISTORY</span>
                <ol className="side-history">
                  {history.map((f: Fact) => {
                    const at = s.asOf && f.valid_from <= s.asOf && s.asOf < f.valid_to;
                    return (
                      <li key={f.assertion_id} className={`${f.status === "current" ? "now" : f.status === "disputed" ? "disp" : "then"} ${at ? "at" : ""}`}>
                        <span className="date">{fmtDate(f.valid_from)}{at ? " · as of your date" : ""}</span>
                        <span>{f.statement}</span>
                      </li>
                    );
                  })}
                </ol>
              </section>
            )}
            <section className="stack" style={{ gap: 10 }}>
              <span className="eyebrow">WHO KNOWS IT</span>
              <Link href={`/ask${qs({ q: `Who knows about ${name}?`, send: "1" })}`} className="home-link">Ask who knows about {name} →</Link>
            </section>
          </aside>
        )}
      </div>
    </div>
  );
}
