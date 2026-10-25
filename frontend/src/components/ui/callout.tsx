import { AlertTriangle, CheckCircle2, Info } from "lucide-react";

import { cn } from "@/lib/utils";

const styles = {
  info: "border-sky-200 bg-sky-50 text-sky-950",
  warning: "border-amber-200 bg-amber-50 text-amber-950",
  success: "border-teal-200 bg-teal-50 text-teal-950",
  danger: "border-rose-200 bg-rose-50 text-rose-950",
} as const;

const icons = {
  info: Info,
  warning: AlertTriangle,
  success: CheckCircle2,
  danger: AlertTriangle,
};

export function Callout({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: keyof typeof styles;
  title?: string;
  children: React.ReactNode;
  className?: string;
}) {
  const Icon = icons[tone];
  return (
    <div
      role="note"
      className={cn(
        "flex gap-3 rounded-2xl border px-4 py-3 text-sm",
        styles[tone],
        className
      )}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0 opacity-90" aria-hidden />
      <div className="min-w-0 space-y-1">
        {title ? <p className="font-semibold text-foreground">{title}</p> : null}
        <div className="leading-relaxed text-muted-foreground [&_a]:underline">
          {children}
        </div>
      </div>
    </div>
  );
}
