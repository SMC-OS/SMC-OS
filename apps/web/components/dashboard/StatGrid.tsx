"use client";

import type { SVGProps } from "react";

import { StatCard, StatCardSkeleton } from "@/components/dashboard/StatCard";
import { FileTextIcon, FolderIcon, UsersIcon } from "@/components/ui/icons";
import { useDashboardStats } from "@/hooks/useDashboardStats";
import { cn } from "@/lib/utils";

function GBPIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} {...props}>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M8 19h8M8 19c-.9 0-1.5-.6-1.5-1.5V15h2.2c1.6 0 2.8-1.2 2.8-2.7S10.3 9.6 8.7 9.6H6.5V6.8C6.5 5.3 7.8 4 9.5 4c1.3 0 2.5.7 3 1.9M5.5 12h4.2"
      />
    </svg>
  );
}

export function StatGrid() {
  const { data, status } = useDashboardStats();
  const loading = status === "loading" && !data;

  return (
    <div className={cn("grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4")}>
      {loading || !data ? (
        <>
          <StatCardSkeleton />
          <StatCardSkeleton />
          <StatCardSkeleton />
          <StatCardSkeleton />
        </>
      ) : (
        <>
          <StatCard
            label="Today's Quotes"
            value={data.quotes_today}
            icon={FileTextIcon}
            loading={status === "error"}
          />
          <StatCard
            label="Revenue"
            value={data.revenue}
            format="currency"
            icon={GBPIcon}
            loading={status === "error"}
          />
          <StatCard
            label="Customers"
            value={data.customers}
            icon={UsersIcon}
            loading={status === "error"}
          />
          <StatCard
            label="Projects"
            value={data.projects}
            icon={FolderIcon}
            loading={status === "error"}
          />
        </>
      )}
    </div>
  );
}
