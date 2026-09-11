"use client";

import { useEffect, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Checkbox } from "@/components/ui/Field";
import { AlertCircleIcon, InfoIcon } from "@/components/ui/icons";
import { ApiError, api } from "@/lib/api";
import type { NotificationPreference } from "@/types/notification";

/**
 * Notifications — Sprint 039, Workstream B.
 *
 * Sprint 036 shipped this screen as four `localStorage` keys, and was
 * honest about it in this same file: the preferences applied "to this
 * browser", a server-side table was "genuine follow-up work", and a
 * server-backed setting that nothing read would have been worse than a
 * local one that something did.
 *
 * This is that follow-up. Three things are now true that were not:
 *
 *   1. **Preferences are yours, not this browser's.** They follow you to
 *      your phone, and a colleague muting quote notifications does not
 *      mute yours.
 *   2. **Enforcement is server-side.** A muted notification is never
 *      created, rather than created and then hidden — which is what the
 *      old version did, leaving the unread count still counting them.
 *   3. **Email is real.** GeoCore has sent transactional email since
 *      Sprint 038, so this card no longer claims it cannot. Email is off
 *      for every category by default: turning it on is a deliberate act,
 *      never an upgrade's side effect.
 *
 * The category list is served by the backend rather than hardcoded here,
 * so this screen can never offer a switch for something GeoCore does not
 * actually produce — the same served-vocabulary rule as the automations
 * builder and the project pipeline.
 */
export function NotificationsCard() {
  const [preferences, setPreferences] = useState<NotificationPreference[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savingKey, setSavingKey] = useState<string | null>(null);

  useEffect(() => {
    api
      .getNotificationPreferences()
      .then(setPreferences)
      .catch(() => setError("Couldn't load your notification settings."));
  }, []);

  async function toggle(
    preference: NotificationPreference,
    channel: "in_app" | "email",
    enabled: boolean
  ) {
    const next = { ...preference, [channel]: enabled };
    setSavingKey(`${preference.category}:${channel}`);
    setError(null);
    try {
      // The server's returned list is authoritative — applied only after a
      // successful response, so a failed save never leaves a switch
      // showing a setting that was not stored.
      setPreferences(
        await api.updateNotificationPreferences([
          { category: next.category, in_app: next.in_app, email: next.email },
        ])
      );
    } catch (err) {
      setError(
        err instanceof ApiError ? "Couldn't save that change." : "Something went wrong."
      );
    } finally {
      setSavingKey(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card className="border-info/25 bg-info/5">
        <CardContent className="flex items-start gap-3 py-4">
          <InfoIcon className="mt-0.5 h-[18px] w-[18px] shrink-0 text-info" />
          <p className="text-sm text-foreground">
            These settings are yours, and follow you to any device you sign in on.
            GeoCore doesn&rsquo;t send SMS or push notifications, so there&rsquo;s
            nothing to configure for those.
          </p>
        </CardContent>
      </Card>

      {error && (
        <Card className="border-danger/25 bg-danger/5">
          <CardContent className="flex items-start gap-3 py-4">
            <AlertCircleIcon className="mt-0.5 h-[18px] w-[18px] shrink-0 text-danger" />
            <p className="text-sm text-foreground">{error}</p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>What GeoCore tells you about</CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          {preferences === null && !error && (
            <div className="space-y-3">
              {[0, 1, 2, 3].map((index) => (
                <div key={index} className="h-12 animate-pulse rounded-lg bg-surface-hover" />
              ))}
            </div>
          )}

          {preferences?.length === 0 && (
            <p className="text-sm text-muted">There&rsquo;s nothing to configure yet.</p>
          )}

          {preferences && preferences.length > 0 && (
            <>
              {/* Column headers only from `sm` up. At 390px the switches sit
                  under their own description, where floating column labels
                  would be noise rather than orientation. */}
              <div className="mb-2 hidden items-center justify-end gap-6 pr-1 text-xs font-medium text-muted sm:flex">
                <span className="w-16 text-center">In app</span>
                <span className="w-16 text-center">Email</span>
              </div>

              <ul className="divide-y divide-border">
                {preferences.map((preference) => (
                  <li
                    key={preference.category}
                    className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-foreground">
                        {preference.label}
                      </p>
                      <p className="mt-0.5 text-xs text-muted">
                        {preference.description}
                      </p>
                    </div>

                    <div className="flex shrink-0 items-center gap-6">
                      {/* Visible labels on a phone, where the column
                          headers are hidden — a bare checkbox with no
                          adjacent word is not a control anyone can read. */}
                      <div className="flex w-16 justify-center">
                        <Checkbox
                          label=""
                          aria-label={`${preference.label} in the app`}
                          checked={preference.in_app}
                          disabled={savingKey === `${preference.category}:in_app`}
                          onChange={(e) => toggle(preference, "in_app", e.target.checked)}
                        />
                        <span className="ml-2 text-xs text-muted sm:hidden">In app</span>
                      </div>
                      <div className="flex w-16 justify-center">
                        <Checkbox
                          label=""
                          aria-label={`${preference.label} by email`}
                          checked={preference.email}
                          disabled={savingKey === `${preference.category}:email`}
                          onChange={(e) => toggle(preference, "email", e.target.checked)}
                        />
                        <span className="ml-2 text-xs text-muted sm:hidden">Email</span>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
