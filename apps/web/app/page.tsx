"use client";

import { useAuth } from "@/components/auth/AuthProvider";
import { CommandCentrePanel } from "@/components/dashboard/command-centre/CommandCentrePanel";
import { DashboardStatusBar } from "@/components/dashboard/DashboardStatusBar";
import { QuickActions } from "@/components/dashboard/QuickActions";
import { RecentActivityPanel } from "@/components/dashboard/RecentActivityPanel";
import { StatGrid } from "@/components/dashboard/StatGrid";
import { useDashboardStats } from "@/hooks/useDashboardStats";

export default function DashboardPage() {
  const { status, error } = useDashboardStats();
  const { name } = useAuth();

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Welcome back{name ? `, ${name}` : ""}
        </h1>
        <p className="mt-1 text-sm text-muted">
          Here&rsquo;s what&rsquo;s happening across SIMO OS right now.
        </p>
      </div>

      <DashboardStatusBar status={status} error={error} />

      <StatGrid />

      <div className="mt-6">
        <CommandCentrePanel />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <RecentActivityPanel />
        </div>
        <div className="space-y-6">
          <QuickActions />
        </div>
      </div>
    </div>
  );
}
