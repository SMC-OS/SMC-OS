"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth/AuthProvider";
import { CommandCentrePanel } from "@/components/dashboard/command-centre/CommandCentrePanel";
import { DashboardStatusBar } from "@/components/dashboard/DashboardStatusBar";
import { QuickActions } from "@/components/dashboard/QuickActions";
import { RecentActivityPanel } from "@/components/dashboard/RecentActivityPanel";
import { StatGrid } from "@/components/dashboard/StatGrid";
import { useDashboardStats } from "@/hooks/useDashboardStats";

export default function DashboardPage() {
  const router = useRouter();
  const { status, error, isAuthError } = useDashboardStats();
  const { name, isAuthenticated, isReady } = useAuth();

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

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Welcome back{name ? `, ${name}` : ""}
        </h1>
        <p className="mt-1 text-sm text-muted">
          Here&rsquo;s what&rsquo;s happening across GeoCore right now.
        </p>
      </div>

      <DashboardStatusBar status={status} error={error} isAuthError={isAuthError} />

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
