"use client";

import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { InfoIcon, LogOutIcon } from "@/components/ui/icons";
import { api } from "@/lib/api";
import type { AuthUser } from "@/types/auth";

/**
 * Security — Sprint 036, Workstream I.
 *
 * Built strictly on what the backend actually supports today, which is:
 * who you are signed in as, what role you hold, and signing out.
 *
 * There is deliberately no "change password", no "two-factor
 * authentication" and no "active sessions" list, because none of those
 * endpoints exist. A disabled control or a "coming soon" row would tell a
 * reader the feature is nearly there; naming the gap plainly tells them
 * the truth and is the honest version of this screen until the endpoints
 * are built (see docs/SPRINTS/sprint-036.md §10).
 */
export function SecurityCard() {
  const { logout, role } = useAuth();
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    api.getMe().then(setUser).catch(() => {});
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Your account</CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="min-w-0">
              <dt className="text-xs font-medium text-muted">Name</dt>
              <dd className="truncate text-sm text-foreground">{user?.name ?? "—"}</dd>
            </div>
            <div className="min-w-0">
              <dt className="text-xs font-medium text-muted">Email</dt>
              <dd className="truncate text-sm text-foreground">{user?.email ?? "—"}</dd>
            </div>
            <div className="min-w-0">
              <dt className="text-xs font-medium text-muted">Role</dt>
              <dd className="text-sm text-foreground">
                <Badge tone={role === "Owner" ? "accent" : "neutral"}>{role ?? "—"}</Badge>
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Session</CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          <p className="mb-4 text-sm text-muted">
            You&rsquo;re signed in on this device. Signing out clears your session here.
          </p>
          <Button variant="outline" onClick={logout}>
            <LogOutIcon className="h-4 w-4" />
            Sign out
          </Button>
        </CardContent>
      </Card>

      <Card className="border-info/25 bg-info/5">
        <CardContent className="flex items-start gap-3 py-4">
          <InfoIcon className="mt-0.5 h-[18px] w-[18px] shrink-0 text-info" />
          <div>
            <p className="text-sm font-medium text-foreground">
              Changing your password and two-factor authentication
            </p>
            <p className="mt-0.5 text-sm text-muted">
              These aren&rsquo;t available in GeoCore yet. Contact your workspace owner
              if you need your access changed in the meantime.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
