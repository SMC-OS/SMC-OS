"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth/AuthProvider";
import { AIInsightCard } from "@/components/dashboard/AIInsightCard";
import { AttentionPanel } from "@/components/dashboard/AttentionPanel";
import { AutomationActivityPanel } from "@/components/dashboard/AutomationActivityPanel";
import { CommandCentrePanel } from "@/components/dashboard/command-centre/CommandCentrePanel";
import { DashboardStatusBar } from "@/components/dashboard/DashboardStatusBar";
import { QuickActions } from "@/components/dashboard/QuickActions";
import { RecentActivityPanel } from "@/components/dashboard/RecentActivityPanel";
import { StatGrid } from "@/components/dashboard/StatGrid";
import { UpcomingPanel } from "@/components/dashboard/UpcomingPanel";
import { useDashboardStats } from "@/hooks/useDashboardStats";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";

/**
 * Dashboard V2 — Sprint 036, Workstream C.
 *
 * An operational command centre rather than four KPI cards. Every number
 * on this page comes from a real endpoint over this tenant's own data;
 * where a section has nothing to show it renders a real empty state that
 * says what would put something there, rather than a zero that reads as a
 * measurement.
 *
 * Layout: single column on a phone, two columns from `lg`. The ordering
 * matters on a phone, where the reader only sees the first screen —
 * headline numbers, then what needs doing, then what is coming up.
 */
export default function DashboardPage() {
  const router = useRouter();
  const { status, error, isAuthError } = useDashboardStats();
  const { name, tenantName, isAuthenticated, isReady } = useAuth();
  const { profile } = useWorkspace();

  // Production incident (post-v1.0.1): unlike every other protected page
  // (customers, projects, quotes, settings), the dashboard had no guard at
  // all — an unauthenticated or session-expired visitor saw a broken
  // dashboard shell instead of being sent to /login.
  useEffect(() => {
    if (!isReady) return;
    if (!isAuthenticated) {
      router.replace("/login");
    }
  }, [isReady, isAuthenticated, router]);

  if (!isReady || !isAuthenticated) return null;

  const company = profile?.trading_name || profile?.legal_name || tenantName;

  return (
    <div className="mx-auto max-w-7xl">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
          {greeting()}
          {name ? `, ${name.split(" ")[0]}` : ""}
        </h1>
        <p className="mt-1 text-sm text-muted">
          {company
            ? `Here's where ${company} stands today.`
            : "Here's where your business stands today."}
        </p>
      </div>

      <DashboardStatusBar status={status} error={error} isAuthError={isAuthError} />

      <StatGrid />

      <div className="mt-6">
        <AIInsightCard />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <AttentionPanel />
          <CommandCentrePanel />
          <RecentActivityPanel />
        </div>

        <div className="space-y-6">
          <QuickActions />
          <UpcomingPanel />
          <AutomationActivityPanel />
        </div>
      </div>
    </div>
  );
}

/** A greeting that matches the time of day. Trades start early; "Good
 * morning" at 06:00 is right and "Welcome back" is filler. */
function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}
