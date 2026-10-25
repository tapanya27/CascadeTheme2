import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

export function MetricCard({
  label,
  value,
  description,
  icon: Icon,
  hint,
  className,
  stagger,
}: {
  label: string;
  value: React.ReactNode;
  description: string;
  icon: LucideIcon;
  hint?: string;
  className?: string;
  stagger?: 1 | 2 | 3 | 4;
}) {
  return (
    <div
      className={cn(
        "surface surface-glow group relative overflow-hidden p-4 transition-transform duration-200 hover:-translate-y-0.5 sm:p-5 animate-fade-up",
        stagger ? `stagger-${stagger}` : null,
        className
      )}
    >
      <div className="pointer-events-none absolute -right-6 -top-6 h-24 w-24 rounded-full bg-primary/10 blur-2xl transition-opacity group-hover:opacity-100" />
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
            {label}
          </p>
          <p className="mt-2 font-display text-3xl tracking-tight text-foreground">
            {value}
          </p>
          <p className="mt-1.5 text-sm text-muted-foreground">{description}</p>
          {hint ? (
            <p className="mt-2 text-[11px] text-primary/80">{hint}</p>
          ) : null}
        </div>
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-primary/25 bg-primary/10 text-primary">
          <Icon className="h-5 w-5" aria-hidden />
        </div>
      </div>
    </div>
  );
}
