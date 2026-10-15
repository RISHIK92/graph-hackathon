"use client";

import { AlertCircle, AlertTriangle, CheckCircle2, ChevronRight, Flag, Info, Loader2, X, type LucideIcon } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { statusTone } from "@/lib/format";
import { STATUS_LABEL } from "@/lib/labels";
import { useOpenMode, useStore } from "@/lib/store";

// buttons

export function Button({
  variant = "secondary", size, icon: Icon, children, busy, className = "", ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "danger-solid" | "link";
  size?: "sm";
  icon?: LucideIcon;
  busy?: boolean;
}) {
  const cls = ["btn", variant === "danger-solid" ? "danger solid" : variant === "secondary" ? "" : variant, size || "", !children ? "icon-only" : "", className]
    .filter(Boolean).join(" ");
  return (
    <button className={cls} disabled={rest.disabled || busy} {...rest}>
      {busy ? <Loader2 className="icon-sm spin" /> : Icon ? <Icon className="icon-sm" /> : null}
      {children}
    </button>
  );
}

// chips

export function Chip({ tone, icon: Icon, children, onClick, title, dashed, strike, className = "" }: {
  tone?: "success" | "warning" | "error" | "accent" | "neutral";
  icon?: LucideIcon; children: ReactNode; onClick?: () => void; title?: string; dashed?: boolean; strike?: boolean; className?: string;
}) {
  const cls = ["chip", tone || "", dashed ? "dashed" : "", strike ? "strike" : "", onClick ? "clickable" : "", className].filter(Boolean).join(" ");
  if (onClick) {
    return (
      <button type="button" className={cls} onClick={onClick} title={title}>
        {Icon && <Icon />}
        {children}
      </button>
    );
  }
  return (
    <span className={cls} title={title}>
      {Icon && <Icon />}
      {children}
    </span>
  );
}

/** Status as dot + word (never colour alone). */
export function Status({ status, className = "" }: { status: string; className?: string }) {
  const t = statusTone(status);
  return (
    <span className={`status ${t.strike ? "strike" : ""} ${className}`}>
      <i className={t.dot} aria-hidden />
      {STATUS_LABEL[status] || status}
    </span>
  );
}

export function StatusChip({ status }: { status: string }) {
  const t = statusTone(status);
  return (
    <span className={`chip ${t.tone} ${t.strike ? "strike" : ""}`}>
      <i className={t.dot} aria-hidden style={{ width: 6, height: 6 }} />
      {STATUS_LABEL[status] || status}
    </span>
  );
}

export function CountBadge({ n, accent }: { n: number; accent?: boolean }) {
  return <span className={`count-badge ${accent ? "accent" : ""}`}>{n}</span>;
}

export function DisputeFlag({ title = "Open dispute" }: { title?: string }) {
  return <Flag className="flag" aria-label={title} role="img" />;
}

// notices, toasts, states

const TONE_ICON: Record<string, LucideIcon> = { info: Info, success: CheckCircle2, warning: AlertTriangle, error: AlertCircle };

export function Notice({ tone = "info", title, children, actions }: {
  tone?: "info" | "success" | "warning" | "error"; title?: ReactNode; children?: ReactNode; actions?: ReactNode;
}) {
  const Icon = TONE_ICON[tone];
  return (
    <div className={`notice ${tone === "info" ? "" : tone}`} role={tone === "error" ? "alert" : undefined}>
      <Icon className="lead" />
      <div className="body">
        {title && <div className="title">{title}</div>}
        {children && <div>{children}</div>}
        {actions && <div className="row-wrap" style={{ marginTop: 4 }}>{actions}</div>}
      </div>
    </div>
  );
}

export function Toasts() {
  const { toasts, dismissToast } = useStore();
  if (!toasts.length) return null;
  return (
    <div className="toast-stack" aria-live="polite">
      {toasts.map((t) => {
        const Icon = TONE_ICON[t.tone];
        return (
          <div key={t.id} className={`toast ${t.tone}`}>
            <Icon className="lead" />
            <div className="body">
              <div className="title">{t.title}</div>
              {t.body && <div className="t-small text-2">{t.body}</div>}
              {t.action && (
                <div className="actions">
                  <button className="link-btn t-small" onClick={() => { t.action?.onClick(); dismissToast(t.id); }}>{t.action.label}</button>
                </div>
              )}
            </div>
            <button className="btn ghost sm icon-only" aria-label="Dismiss" onClick={() => dismissToast(t.id)}>
              <X className="icon-sm" />
            </button>
          </div>
        );
      })}
    </div>
  );
}

export function Skeleton({ w = "100%", h = 12, className = "" }: { w?: number | string; h?: number; className?: string }) {
  return <span className={`skeleton ${className}`} style={{ width: w, height: h, display: "block" }} aria-hidden />;
}

export function SkeletonRows({ n = 5, cols = [40, 20, 20, 10] }: { n?: number; cols?: number[] }) {
  return (
    <div aria-busy="true" aria-label="Loading">
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="sk-row">
          {cols.map((c, j) => <Skeleton key={j} w={`${c}%`} />)}
        </div>
      ))}
    </div>
  );
}

export function Empty({ icon: Icon, title, children, action, compact }: {
  icon?: LucideIcon; title: ReactNode; children?: ReactNode; action?: ReactNode; compact?: boolean;
}) {
  return (
    <div className={`empty ${compact ? "compact" : ""}`}>
      {Icon && <Icon />}
      <div>
        <div className="title">{title}</div>
        {children && <div className="t-small">{children}</div>}
      </div>
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry, inline }: { message: string; onRetry?: () => void; inline?: boolean }) {
  return (
    <div className={`errstate ${inline ? "inline" : ""}`} role="alert">
      <AlertCircle className="lead" />
      <div className="body">
        <div className="t-strong">Something went wrong</div>
        <div className="t-small text-2">{message}</div>
        {(onRetry) && (
          <div className="actions">
            {onRetry && <Button size="sm" onClick={onRetry}>Retry</Button>}
            <Button size="sm" variant="ghost" onClick={() => navigator.clipboard?.writeText(message)}>Copy details</Button>
          </div>
        )}
      </div>
    </div>
  );
}

export function Placeholder({ children }: { children: ReactNode }) {
  return <span className="placeholder t-small">{children}</span>;
}

// tabs

export interface TabDef { id: string; label: ReactNode; count?: number; disabled?: boolean; reason?: string }

export function Tabs({ tabs, value, onChange, className = "" }: { tabs: TabDef[]; value: string; onChange: (id: string) => void; className?: string }) {
  return (
    <div className={`tabs ${className}`} role="tablist">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          className="tab"
          aria-selected={value === t.id}
          aria-disabled={t.disabled || undefined}
          title={t.disabled ? t.reason : undefined}
          onClick={() => !t.disabled && onChange(t.id)}
        >
          {t.label}
          {t.count !== undefined && <span className="count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Segmented<T extends string>({ options, value, onChange }: { options: { id: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="segmented" role="group">
      {options.map((o) => (
        <button key={o.id} aria-pressed={value === o.id} onClick={() => onChange(o.id)}>{o.label}</button>
      ))}
    </div>
  );
}

// modal

export function Modal({ title, size, onClose, children, footer, busy }: {
  title: ReactNode; size?: "md" | "lg"; onClose: () => void; children: ReactNode; footer?: ReactNode; busy?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const labelId = useId();
  // Callers pass onClose inline; reading it through a ref keeps the focus effect from re-running (and
  // stealing focus from the field being typed in) on every render.
  const close = useRef(onClose);
  const busyRef = useRef(busy);
  useEffect(() => {
    close.current = onClose;
    busyRef.current = busy;
  });
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    const el = ref.current;
    const focusables = () => Array.from(el?.querySelectorAll<HTMLElement>("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])") || []).filter((x) => !x.hasAttribute("disabled"));
    (focusables()[0] || el)?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busyRef.current) { e.stopPropagation(); close.current(); }
      if (e.key === "Tab") {
        const f = focusables();
        if (!f.length) return;
        const first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    const body = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = body;
      prev?.focus?.();
    };
  }, []);
  return (
    <div className="modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}>
      <div className={`modal ${size || ""}`} role="dialog" aria-modal="true" aria-labelledby={labelId} ref={ref} tabIndex={-1}>
        <div className="modal-header">
          <h2 className="t-heading grow" id={labelId}>{title}</h2>
          <Button variant="ghost" size="sm" icon={X} aria-label="Close" onClick={onClose} disabled={busy} />
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}

// misc

export function Field({ label, help, error, children }: { label: ReactNode; help?: ReactNode; error?: ReactNode; children: ReactNode }) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
      {help && !error && <div className="help">{help}</div>}
      {error && <div className="err"><AlertCircle className="icon-sm" />{error}</div>}
    </div>
  );
}

export function Details({ summary, children, open }: { summary: ReactNode; children: ReactNode; open?: boolean }) {
  return (
    <details className="details" open={open}>
      <summary><ChevronRight />{summary}</summary>
      <div className="details-body">{children}</div>
    </details>
  );
}

/** Entity name that opens the entity in the inspector. */
export function EntityLink({ id, name, disputed, className = "" }: { id: string; name?: string; disputed?: boolean; className?: string }) {
  const { openEntity } = useStore();
  const mode = useOpenMode();
  return (
    <button type="button" className={`entity-link ${className}`} onClick={(e) => { e.stopPropagation(); openEntity(id, name, mode); }}>
      {name || id}
      {disputed && <DisputeFlag />}
    </button>
  );
}

export function KV({ rows, narrow }: { rows: [ReactNode, ReactNode][]; narrow?: boolean }) {
  return (
    <dl className={`kv ${narrow ? "narrow" : ""}`}>
      {rows.map(([k, v], i) => (
        <div key={i} style={{ display: "contents" }}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Popover({ trigger, children, align = "left", open, onOpenChange }: {
  trigger: (p: { open: boolean; toggle: () => void }) => ReactNode; children: ReactNode | ((close: () => void) => ReactNode);
  align?: "left" | "right"; open?: boolean; onOpenChange?: (v: boolean) => void;
}) {
  const [inner, setInner] = useState(false);
  const isOpen = open ?? inner;
  const set = (v: boolean) => { setInner(v); onOpenChange?.(v); };
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!isOpen) return;
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) set(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") set(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("keydown", onKey); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);
  return (
    <div className="popover-anchor" ref={ref}>
      {trigger({ open: isOpen, toggle: () => set(!isOpen) })}
      {isOpen && <div className={`popover ${align}`}>{typeof children === "function" ? children(() => set(false)) : children}</div>}
    </div>
  );
}
