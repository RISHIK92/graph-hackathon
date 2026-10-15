"use client";

import { Search } from "lucide-react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import { disputesOf, EntityActions, EntityDisputes, EntityHistory, EntitySources, EntitySummary, useEntity } from "@/components/EntityPanel";
import { PageHeader } from "@/components/PageHeader";
import { Button, Chip, Empty, ErrorState, Skeleton, Tabs } from "@/components/ui";
import { qs } from "@/lib/api";
import { labelOf } from "@/lib/format";
import { useStore } from "@/lib/store";

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
  useEffect(() => { if (data?.name) document.title = `${data.name} · Company Brain`; }, [data?.name]);

  return (
    <div className="page">
      <PageHeader
        title={data?.name || (notFound ? "Not found" : <Skeleton w={160} h={18} />)}
        description={data?.d || undefined}
        meta={<Chip tone="neutral">{labelOf(data?.labels, id)}</Chip>}
        actions={<EntityActions data={data} id={id} inPage />}
        tabs={data ? (
          <Tabs value={tab} onChange={setTab} tabs={[
            { id: "overview", label: "Overview" },
            { id: "history", label: "History", count: Object.values(data.history || {}).reduce((n, p) => n + p.items.length, 0) || undefined },
            { id: "sources", label: "Sources", count: data.sources?.reduce((n, g) => n + g.sources.length, 0) || undefined },
            { id: "disputes", label: "Disputes", count: disputes || undefined },
          ]} />
        ) : undefined}
      />
      <div className="page-body" style={{ maxWidth: 1040 }}>
        {notFound && <Empty icon={Search} title="No entity with this id" action={<Button size="sm" onClick={() => s.setPaletteOpen(true)}>Search</Button>}>{id}</Empty>}
        {error && !notFound && <ErrorState message={error} onRetry={reload} />}
        {!data && !error && <div className="stack-3"><Skeleton h={36} /><Skeleton h={36} /><Skeleton h={120} /></div>}
        {data && tab === "overview" && <EntitySummary data={data} id={id} full />}
        {data && tab === "history" && <EntityHistory data={data} />}
        {data && tab === "sources" && <EntitySources data={data} />}
        {data && tab === "disputes" && <EntityDisputes data={data} id={id} />}
      </div>
    </div>
  );
}
