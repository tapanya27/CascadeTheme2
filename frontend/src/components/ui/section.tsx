import { cn } from "@/lib/utils";

export function PageMain({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <main
      className={cn(
        "flex min-h-0 flex-1 flex-col space-y-5 overflow-y-auto p-4 sm:p-6 lg:p-8",
        className
      )}
    >
      {children}
    </main>
  );
}

export function Section({
  title,
  description,
  actions,
  children,
  className,
}: {
  title?: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("space-y-3", className)}>
      {(title || actions) && (
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            {title ? (
              <h2 className="font-display text-lg tracking-tight text-foreground">
                {title}
              </h2>
            ) : null}
            {description ? (
              <p className="mt-0.5 max-w-2xl text-sm text-muted-foreground">
                {description}
              </p>
            ) : null}
          </div>
          {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
        </div>
      )}
      {children}
    </section>
  );
}

export function Panel({
  children,
  className,
  id,
}: {
  children: React.ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <div id={id} className={cn("surface p-4 sm:p-5", className)}>
      {children}
    </div>
  );
}

export function KeyValue({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium text-foreground">{value}</dd>
    </div>
  );
}
