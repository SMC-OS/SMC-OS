import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * Sprint 036 (Workstream B). Cards are the main surface in GeoCore, so
 * they carry the design system's restraint: one soft, warm-tinted shadow
 * (never a heavy drop shadow), a real border so they still read as
 * separate surfaces in dark mode where shadows barely register, and a
 * generous radius that matches the buttons and inputs.
 */
export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-border bg-surface shadow-[var(--shadow-sm)]",
        className
      )}
      {...props}
    />
  );
}

/** A card that responds to being pointed at — for cards that are links. */
export function InteractiveCard({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <Card
      className={cn(
        "transition-shadow duration-150 hover:border-border-strong hover:shadow-[var(--shadow-md)]",
        className
      )}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-5 pb-0", className)} {...props} />;
}

export function CardContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-5", className)} {...props} />;
}

export function CardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={cn(
        "text-[13px] font-semibold uppercase tracking-wide text-muted",
        className
      )}
      {...props}
    />
  );
}

/**
 * The empty state every list and panel in GeoCore uses.
 *
 * Sprint 036's contract forbids fabricated metrics, which makes empty
 * states load-bearing rather than decorative: when there is no data, the
 * product has to say so and say what to do about it, not render a zero
 * that looks like a measurement.
 */
export function EmptyState({
  title,
  description,
  action,
  className,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("px-5 py-10 text-center", className)}>
      <p className="text-sm font-medium text-foreground">{title}</p>
      {description && (
        <p className="mx-auto mt-1 max-w-sm text-sm text-muted">{description}</p>
      )}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}
