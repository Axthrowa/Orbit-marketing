import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import type { Tone } from "../types";
import { OrbitIcon } from "./OrbitIcon";
import type { OrbitIconName } from "./OrbitIcon";

export function Badge({ tone, children, title }: { tone: Tone; children: ReactNode; title?: string }) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {children}
    </span>
  );
}

type ButtonVariant = "default" | "primary" | "warning" | "danger" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  small?: boolean;
  busy?: boolean;
  icon?: OrbitIconName;
}

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  default: "",
  primary: "button-primary",
  warning: "button-warning",
  danger: "button-danger",
  ghost: "button-quiet",
};

export function Button({ variant = "default", small, busy, icon, children, disabled, className, ...rest }: ButtonProps) {
  const classes = ["button", VARIANT_CLASS[variant], small ? "button-sm" : "", className ?? ""].filter(Boolean).join(" ");
  return (
    <button type="button" {...rest} className={classes} disabled={disabled || busy}>
      {busy ? <Loader2 size={14} className="spin" aria-hidden /> : icon ? <OrbitIcon name={icon} /> : null}
      {children}
    </button>
  );
}

/** Orbit paneli: üstte küçük mor etiket (kicker) + başlık; `lift` üzerine gelince yükselir. */
export function Card({
  title,
  kicker,
  actions,
  icon,
  children,
  flush,
  lift = true,
  className,
}: {
  title?: ReactNode;
  kicker?: string;
  actions?: ReactNode;
  icon?: OrbitIconName;
  children: ReactNode;
  flush?: boolean;
  lift?: boolean;
  className?: string;
}) {
  const hasHeader = title !== undefined || actions !== undefined || kicker !== undefined;
  return (
    <section className={["panel", lift ? "lift" : "", className ?? ""].filter(Boolean).join(" ")}>
      {hasHeader ? (
        <header className="panel-header">
          <div>
            {kicker ? <span className="small-label">{kicker}</span> : null}
            {title !== undefined ? <h2>{title}</h2> : null}
          </div>
          {actions !== undefined || icon ? (
            <div className="flex flex-wrap items-center gap-2">
              {actions}
              {icon ? (
                <span className="round-icon">
                  <OrbitIcon name={icon} />
                </span>
              ) : null}
            </div>
          ) : null}
        </header>
      ) : null}
      <div className={flush ? "" : hasHeader ? "panel-body" : "panel-body pt-6"}>{children}</div>
    </section>
  );
}

export function Alert({
  tone,
  title,
  children,
  actions,
}: {
  tone: Tone;
  title?: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className={`alert alert-${tone}`} role={tone === "danger" ? "alert" : "status"}>
      <div className="min-w-0 flex-1">
        {title ? <div className="font-semibold" style={{ color: `var(--${tone === "neutral" ? "ink" : tone})` }}>{title}</div> : null}
        {children ? <div className={title ? "muted mt-0.5" : ""}>{children}</div> : null}
        {actions ? <div className="mt-2 flex flex-wrap gap-2">{actions}</div> : null}
      </div>
    </div>
  );
}

/** Orbit haftalık kartı: etiket, büyük sayı, açıklama ve renkli simge kutusu. */
export function Kpi({
  label,
  value,
  sub,
  tone,
  icon = "chart",
  iconTone = 0,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: Tone;
  icon?: OrbitIconName;
  iconTone?: 0 | 1 | 2 | 3 | 4;
}) {
  return (
    <article className="panel lift weekly-card">
      <span>{label}</span>
      <strong style={tone ? { color: `var(--${tone})` } : undefined}>{value}</strong>
      {sub ? <small>{sub}</small> : null}
      <span className={`card-icon tone-${iconTone}`}>
        <OrbitIcon name={icon} />
      </span>
    </article>
  );
}

export function SentimentBar({ positive, negative, sample }: { positive: number | null; negative: number | null; sample: number }) {
  if (positive === null || negative === null || sample === 0) {
    return <span className="muted">Veri yok</span>;
  }
  const neutral = Math.max(0, 1 - positive - negative);
  const label = `%${Math.round(positive * 100)} olumlu · %${Math.round(neutral * 100)} nötr · %${Math.round(negative * 100)} olumsuz (${sample} yorum)`;
  return (
    <div title={label}>
      <div className="bar" role="img" aria-label={label}>
        <span className="bar-pos" style={{ width: `${positive * 100}%` }} />
        <span className="bar-neu" style={{ width: `${neutral * 100}%` }} />
        <span className="bar-neg" style={{ width: `${negative * 100}%` }} />
      </div>
      <div className="mt-1 flex justify-between text-[10px]">
        <span style={{ color: "var(--success)" }}>%{Math.round(positive * 100)}</span>
        <span style={{ color: "var(--danger)" }}>%{Math.round(negative * 100)}</span>
      </div>
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <p className="empty">
      <strong>{title}</strong>
      {children}
    </p>
  );
}

export function Field({ label, hint, children, htmlFor }: { label: string; hint?: ReactNode; children: ReactNode; htmlFor?: string }) {
  return (
    <div className="min-w-0">
      <label className="label" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
      {hint ? <div className="hint">{hint}</div> : null}
    </div>
  );
}

export function Avatar({ name }: { name: string }) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toLocaleUpperCase("tr-TR") ?? "")
    .join("");
  return (
    <span className="avatar" aria-hidden>
      {initials}
    </span>
  );
}
