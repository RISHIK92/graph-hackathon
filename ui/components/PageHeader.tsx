"use client";

import type { ReactNode } from "react";
import { fmtDate } from "@/lib/format";
import { useStore } from "@/lib/store";
import { Chip } from "./ui";

/** Page header pattern (DESIGN.md §3.6): title, description, meta, actions, optional tab row. */
export function PageHeader({ title, description, meta, actions, tabs, asOf = true }: {
  title: ReactNode; description?: ReactNode; meta?: ReactNode; actions?: ReactNode; tabs?: ReactNode; asOf?: boolean;
}) {
  const s = useStore();
  return (
    <div className="page-header">
      <div className="page-header-row">
        <div className="stack" style={{ gap: 0 }}>
          <h1 className="t-title">{title}</h1>
          {description && <div className="t-small text-2">{description}</div>}
        </div>
        <div className="page-meta">
          {asOf && s.asOf && <Chip tone="warning">As of {fmtDate(s.asOf)}</Chip>}
          {meta}
        </div>
        {actions && <div className="page-actions">{actions}</div>}
      </div>
      {tabs && <div className="page-tabs">{tabs}</div>}
    </div>
  );
}
