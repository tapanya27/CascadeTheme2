import { AlertCircle, Inbox, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex min-h-[140px] flex-col items-center justify-center gap-3 text-muted-foreground"
    >
      <Loader2 className="h-5 w-5 animate-spin text-primary" aria-hidden />
      <p className="text-sm">{label}</p>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex min-h-[140px] flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border bg-secondary/30 px-6 py-8 text-center">
      <Inbox className="h-6 w-6 text-muted-foreground" aria-hidden />
      <p className="font-medium text-foreground">{title}</p>
      {description ? (
        <p className="max-w-md text-sm text-muted-foreground">{description}</p>
      ) : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  message,
  className,
  onRetry,
}: {
  title?: string;
  message?: string;
  className?: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "flex min-h-[120px] flex-col items-center justify-center gap-2 rounded-lg border border-destructive/25 bg-destructive/5 px-6 py-6 text-center",
        className
      )}
    >
      <AlertCircle className="h-6 w-6 text-destructive" aria-hidden />
      <p className="font-medium text-foreground">{title}</p>
      {message ? (
        <p className="max-w-lg text-sm text-muted-foreground">{message}</p>
      ) : null}
      {onRetry ? (
        <Button type="button" variant="outline" size="sm" className="mt-1" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}

export function SuccessBanner({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="rounded-xl border border-teal-200 bg-teal-50 px-3 py-2 text-sm text-teal-900"
      role="status"
    >
      {children}
    </p>
  );
}

export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "h-28 animate-pulse rounded-xl border border-border bg-secondary/50",
        className
      )}
      aria-hidden
    />
  );
}
