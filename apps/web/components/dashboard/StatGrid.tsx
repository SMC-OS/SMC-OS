"use client";

import { StatCard, StatCardSkeleton } from "@/components/dashboard/StatCard";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";
import { FileTextIcon, FolderIcon, TrendingUpIcon, UsersIcon } from "@/components/ui/icons";
import { useDashboardStats } from "@/hooks/useDashboardStats";

/**
 * Sprint 036 (Workstream C).
 *
 * Two things changed here beyond the palette:
 *
 * 1. The currency icon. The previous build drew its own £ glyph as an SVG
 *    path, which hardcoded a currency into a picture — a workspace set to
 *    EUR would have shown euros next to a pound sign. Quoted value now
 *    uses a trend icon and the figure itself carries the currency, which
 *    is the only place a currency belongs.
 *
 * 2. Captions. "Quoted value" is the metric most often misread as
 *    revenue. It is the total of quotes raised — a price offered, not
 *    income — and the tile now says so rather than leaving the reader to
 *    assume (the same distinction the backend has drawn since Sprint 025).
 */
export function StatGrid() {
  const { data, status } = useDashboardStats();
  const { currency } = useWorkspace();
  const loading = status === "loading" && !data;

  if (loading || !data) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCardSkeleton />
        <StatCardSkeleton />
        <StatCardSkeleton />
        <StatCardSkeleton />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard
        label="Quotes today"
        value={data.quotes_today}
        icon={FileTextIcon}
        caption="Raised since midnight"
        href="/quotes"
        loading={status === "error"}
      />
      <StatCard
        label="Quoted value"
        value={data.quoted_value}
        format="currency"
        currency={currency}
        icon={TrendingUpIcon}
        caption="Total quoted — a price offered, not income"
        href="/quotes"
        loading={status === "error"}
      />
      <StatCard
        label="Customers"
        value={data.customers}
        icon={UsersIcon}
        caption="On your books"
        href="/customers"
        loading={status === "error"}
      />
      <StatCard
        label="Projects"
        value={data.projects}
        icon={FolderIcon}
        caption="All stages"
        href="/projects"
        loading={status === "error"}
      />
    </div>
  );
}
