import { useEffect, useRef, useState, type ReactNode } from "react";
import { motion } from "motion/react";
import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { SIGNAL_WEIGHTS, masteryBand } from "@/lib/chaigaram";

/* ------------------------------------------------------------------ */

export function Panel({
  className,
  children,
  tint,
  ...rest
}: React.HTMLAttributes<HTMLDivElement> & { tint?: boolean }) {
  return (
    <div
      className={cn(
        "rounded-xl border border-border/80 shadow-panel transition-all duration-200 hover:border-border-strong hover:shadow-float",
        tint ? "bg-surface-2" : "bg-surface",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

export function PanelHeader({
  title,
  subtitle,
  action,
  className,
}: {
  title: string;
  subtitle?: string | undefined;
  action?: ReactNode | undefined;
  className?: string | undefined;
}) {
  return (
    <div
      className={cn(
        "flex items-start justify-between gap-4 border-b border-border/60 px-5 py-4",
        className,
      )}
    >
      <div className="min-w-0">
        <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
        {subtitle ? (
          <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{subtitle}</p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ */

export function useCountUp(target: number, duration = 900) {
  const [value, setValue] = useState(0);
  const raf = useRef<number | null>(null);

  useEffect(() => {
    const start = performance.now();
    const from = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(from + (target - from) * eased);
      if (t < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
    };
  }, [target, duration]);

  return value;
}

export function CountUp({
  value,
  decimals = 0,
  suffix = "",
  className,
}: {
  value: number;
  decimals?: number | undefined;
  suffix?: string | undefined;
  className?: string | undefined;
}) {
  const animated = useCountUp(value);
  return (
    <span className={cn("num", className)}>
      {animated.toFixed(decimals)}
      {suffix}
    </span>
  );
}

/* ------------------------------------------------------------------ */

export function StatCard({
  label,
  value,
  suffix,
  decimals,
  hint,
  footer,
  icon,
  tone = "default",
  raw,
}: {
  label: string;
  value?: number | undefined;
  suffix?: string | undefined;
  decimals?: number | undefined;
  hint?: string | undefined;
  footer?: ReactNode | undefined;
  icon?: ReactNode | undefined;
  tone?: "default" | "warn" | "positive" | "primary" | undefined;
  raw?: string | undefined;
}) {
  const toneClass =
    tone === "warn"
      ? "text-warn"
      : tone === "positive"
        ? "text-positive"
        : tone === "primary"
          ? "text-primary"
          : "text-foreground";
  return (
    <Panel className="p-4">
      <div className="flex items-center justify-between">
        <span className="label-xs">{label}</span>
        <span className="text-muted-foreground/70">{icon}</span>
      </div>
      <div className={cn("mt-3 text-3xl font-medium leading-none", toneClass)}>
        {raw ? (
          <span className="num text-2xl">{raw}</span>
        ) : (
          <CountUp value={value ?? 0} decimals={decimals} suffix={suffix} />
        )}
      </div>
      {hint ? <p className="mt-2 text-xs text-muted-foreground">{hint}</p> : null}
      {footer}
    </Panel>
  );
}

/* ------------------------------------------------------------------ */

export function TrendArrow({ delta }: { delta: number }) {
  const Icon = delta > 0.5 ? ArrowUpRight : delta < -0.5 ? ArrowDownRight : ArrowRight;
  const tone = delta > 0.5 ? "text-positive" : delta < -0.5 ? "text-warn" : "text-muted-foreground";
  return (
    <span className={cn("inline-flex items-center gap-1 num text-xs", tone)}>
      <Icon className="h-3.5 w-3.5" />
      {delta > 0 ? "+" : ""}
      {delta.toFixed(1)}
    </span>
  );
}

export function MasteryPill({ score }: { score: number }) {
  const band = masteryBand(score);
  const tone =
    band.tone === "positive"
      ? "bg-positive/12 text-positive"
      : band.tone === "warn"
        ? "bg-warn/12 text-warn"
        : "bg-primary/12 text-primary";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded px-1.5 py-0.5 text-[11px] font-medium",
        tone,
      )}
    >
      <span className="num">{Math.round(score)}</span>
      {band.label}
    </span>
  );
}

/** Small stacked bar showing the three weighted signal contributions. */
export function SignalBar({
  quiz,
  time,
  revisit,
  className,
}: {
  quiz: number;
  time: number;
  revisit: number;
  className?: string | undefined;
}) {
  const parts = [
    { v: quiz * SIGNAL_WEIGHTS.quiz, cls: "bg-primary" },
    { v: time * SIGNAL_WEIGHTS.time, cls: "bg-accent" },
    { v: revisit * SIGNAL_WEIGHTS.revisit, cls: "bg-warn" },
  ];
  return (
    <div
      className={cn("flex h-1.5 w-full gap-px overflow-hidden rounded-full bg-muted", className)}
    >
      {parts.map((p, i) => (
        <motion.div
          key={i}
          initial={{ width: 0 }}
          animate={{ width: `${p.v}%` }}
          transition={{ duration: 0.7, delay: i * 0.06, ease: "easeOut" }}
          className={p.cls}
        />
      ))}
    </div>
  );
}

export function Meter({
  value,
  tone = "primary",
  className,
}: {
  value: number;
  tone?: "primary" | "warn" | "accent" | "muted" | undefined;
  className?: string | undefined;
}) {
  const cls =
    tone === "warn"
      ? "bg-warn"
      : tone === "accent"
        ? "bg-accent"
        : tone === "muted"
          ? "bg-muted-foreground/50"
          : "bg-primary";
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded-full bg-muted", className)}>
      <motion.div
        initial={{ width: 0 }}
        animate={{ width: `${Math.max(0, Math.min(100, value))}%` }}
        transition={{ duration: 0.8, ease: "easeOut" }}
        className={cn("h-full rounded-full", cls)}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */

export function ChartSkeleton({
  height = 240,
  bars = 12,
}: {
  height?: number | undefined;
  bars?: number;
}) {
  return (
    <div className="flex items-end gap-1.5 px-4 py-4" style={{ height }}>
      {Array.from({ length: bars }).map((_, i) => (
        <div
          key={i}
          className="flex-1 animate-pulse rounded-sm bg-muted"
          style={{
            height: `${25 + ((i * 37) % 70)}%`,
            animationDelay: `${i * 60}ms`,
          }}
        />
      ))}
    </div>
  );
}

export function RowsSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-4">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="h-9 animate-pulse rounded bg-muted"
          style={{ animationDelay: `${i * 70}ms`, opacity: 1 - i * 0.1 }}
        />
      ))}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  hint,
  action,
}: {
  icon?: ReactNode | undefined;
  title: string;
  hint?: string | undefined;
  action?: ReactNode | undefined;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <div className="grid h-10 w-10 place-items-center rounded-md border border-border bg-surface-2 text-muted-foreground">
        {icon}
      </div>
      <p className="text-sm font-medium">{title}</p>
      {hint ? <p className="max-w-sm text-xs text-muted-foreground">{hint}</p> : null}
      {action}
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string | undefined;
  title: string;
  description?: string | undefined;
  action?: ReactNode | undefined;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        {eyebrow ? <div className="label-xs mb-1">{eyebrow}</div> : null}
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description ? (
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {action}
    </div>
  );
}

export const chartAxis = {
  stroke: "var(--muted-foreground)",
  fontSize: 11,
  tickLine: false,
  axisLine: false,
};

export function ChartTooltipBox({
  active,
  payload,
  label,
}: {
  active?: boolean | undefined;
  payload?:
    | Array<{ name?: string | undefined; value?: number | string | undefined; color?: string }>
    | undefined;
  label?: string | number | undefined;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-border-strong bg-popover px-3 py-2 shadow-float">
      {label !== undefined ? (
        <div className="mb-1 text-xs font-medium text-foreground">{label}</div>
      ) : null}
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="h-2 w-2 rounded-sm" style={{ background: p.color }} />
          <span>{p.name}</span>
          <span className="num ml-auto text-foreground">
            {typeof p.value === "number" ? p.value.toFixed(0) : p.value}
          </span>
        </div>
      ))}
    </div>
  );
}
