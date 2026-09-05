"use client";

import Link from "next/link";
import type { ComponentType, SVGProps } from "react";

import { Card } from "@/components/ui/Card";
import { useCountUp } from "@/hooks/useCountUp";
import { cn, formatCurrency } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: number;
  format?: "number" | "currency";
  /** The workspace's currency. Required when format is "currency" — a
   * money figure with an assumed currency is a wrong figure. */
  currency?: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  /** One short line saying what this number actually is. Sprint 036
   * (Workstream C): a metric with no definition invites the reader to
   * invent one — "Quoted value" in particular is repeatedly mistaken for
   * revenue, which it is not. */
  caption?: string;
  href?: string;
  loading?: boolean;
}

export function StatCard({
  label,
  value,
  format = "number",
  currency = "GBP",
  icon: StatIcon,
  caption,
  href,
  loading = false,
}: StatCardProps) {
  const animated = useCountUp(value);

  const display =
    format === "currency"
      ? formatCurrency(animated, currency)
      : animated.toLocaleString("en-GB");

  const body = (
    <>
      <div className="flex items-start justify-between gap-3">
        <p className="min-w-0 text-sm font-medium text-muted">{label}</p>
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-subtle text-accent">
          <StatIcon className="h-[18px] w-[18px]" />
        </div>
      </div>

      <p
        className={cn(
          "mt-3 text-2xl font-semibold tracking-tight text-foreground transition-opacity sm:text-3xl",
          loading && "opacity-40"
        )}
      >
        {display}
      </p>
      {caption && <p className="mt-1 text-xs text-muted">{caption}</p>}
    </>
  );

  if (href) {
    return (
      <Link
        href={href}
        className="block rounded-2xl transition-shadow hover:shadow-[var(--shadow-md)]"
      >
        <Card className="h-full p-5">{body}</Card>
      </Link>
    );
  }

  return <Card className="p-5">{body}</Card>;
}

export function StatCardSkeleton() {
  return (
    <Card className="p-5">
      <div className="h-4 w-24 animate-pulse rounded bg-surface-hover" />
      <div className="mt-4 h-8 w-20 animate-pulse rounded bg-surface-hover" />
    </Card>
  );
}
