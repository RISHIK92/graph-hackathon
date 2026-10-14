"use client";

import { useParams } from "next/navigation";
import { ActionRecord, actionTitle, useAction } from "@/components/ActionRecord";
import { PageHeader } from "@/components/PageHeader";
import { Skeleton } from "@/components/ui";

export default function ActionPage() {
  const { id: raw } = useParams<{ id: string }>();
  const id = decodeURIComponent(raw);
  const { data } = useAction(id);
  const me = data?.pack.items[0]?.actions?.[0];
  return (
    <div className="page">
      <PageHeader title={me ? actionTitle(me) : <Skeleton w={240} h={18} />} description="What this action relied on, what it produced, and who was involved." asOf={false} />
      <div className="page-body" style={{ maxWidth: 880 }}>
        <ActionRecord id={id} inPage />
      </div>
    </div>
  );
}
