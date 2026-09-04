"use client";

import { AlertCircleIcon, RefreshIcon, WifiOffIcon } from "@/components/ui/icons";
import { useOnlineStatus } from "@/hooks/useOnlineStatus";
import type { FetchStatus } from "@/hooks/usePolling";

export function DashboardStatusBar({
  status,
  error,
  isAuthError,
}: {
  status: FetchStatus;
  error: string | null;
  // Production incident (post-v1.0.1): a 401/403 (expired/invalid session)
  // must never be reported as "Couldn't reach the GeoCore API" — that
  // message is for a real network/API-availability failure only. An auth
  // error means the user is about to be redirected to /login, not that the
  // API is down.
  isAuthError: boolean;
}) {
  const isOnline = useOnlineStatus();

  if (!isOnline) {
    return (
      <div className="mb-4 flex items-center gap-2 rounded-lg border border-warning/30 bg-warning/10 px-4 py-2.5 text-sm text-warning">
        <WifiOffIcon className="h-4 w-4 shrink-0" />
        You&rsquo;re offline. Showing the last data we had — this will refresh
        automatically once you&rsquo;re back online.
      </div>
    );
  }

  if (status === "error" && isAuthError) {
    return (
      <div className="mb-4 flex items-center gap-2 rounded-lg border border-warning/30 bg-warning/10 px-4 py-2.5 text-sm text-warning">
        <AlertCircleIcon className="h-4 w-4 shrink-0" />
        Your session has expired. Redirecting you to sign in&hellip;
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="mb-4 flex items-center gap-2 rounded-lg border border-danger/30 bg-danger/10 px-4 py-2.5 text-sm text-danger">
        <AlertCircleIcon className="h-4 w-4 shrink-0" />
        Couldn&rsquo;t reach the GeoCore API{error ? ` (${error})` : ""}. Retrying
        every 5 seconds.
        <RefreshIcon className="ml-auto h-4 w-4 shrink-0 animate-spin" />
      </div>
    );
  }

  return null;
}
