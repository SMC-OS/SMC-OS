"use client";

import { useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Checkbox } from "@/components/ui/Field";
import { InfoIcon } from "@/components/ui/icons";
import { NOTIFICATION_PREFERENCE_KEY, readValue, writeValue } from "@/lib/storage-keys";

const PREFERENCES = [
  {
    key: "quote_activity",
    label: "Quote activity",
    description: "When a quote is approved or is about to expire.",
  },
  {
    key: "project_activity",
    label: "Project activity",
    description: "When a job changes stage or is about to start.",
  },
  {
    key: "task_reminders",
    label: "Task reminders",
    description: "When something an automation created is waiting on you.",
  },
  {
    key: "customer_messages",
    label: "Customer messages",
    description: "When a customer replies through their portal.",
  },
] as const;

type Preferences = Record<string, boolean>;

const DEFAULTS: Preferences = Object.fromEntries(
  PREFERENCES.map((preference) => [preference.key, true])
);

/**
 * Notifications — Sprint 036, Workstream I.
 *
 * Honest about what this is. GeoCore has exactly one notification
 * channel: the in-app bell. There is no email, SMS or push
 * infrastructure, so this screen does not offer per-channel toggles that
 * would do nothing, and it says so rather than leaving a reader to
 * assume "email me" is coming from somewhere.
 *
 * The preferences themselves are stored in this browser and control what
 * the notifications panel shows. That is a real, working behaviour and a
 * stated limitation: a per-user server-side preference table is genuine
 * follow-up work (see docs/SPRINTS/sprint-036.md §10), and shipping a
 * server-backed setting that nothing reads would be worse than shipping a
 * local one that something does.
 */
/** Reads stored preferences, falling back to the defaults for a missing
 * or corrupted value — a corrupted value is not worth an error state,
 * since the fallback is exactly what a first-time visitor sees. Pure and
 * outside the component so it can be a lazy useState initialiser rather
 * than a setState inside an effect. */
function storedPreferences(): Preferences {
  const stored = readValue(NOTIFICATION_PREFERENCE_KEY);
  if (!stored) return DEFAULTS;
  try {
    return { ...DEFAULTS, ...(JSON.parse(stored) as Preferences) };
  } catch {
    return DEFAULTS;
  }
}

export function NotificationsCard() {
  // Lazy initialiser, not an effect: localStorage is unavailable during
  // SSR, but this component only ever renders on the client (its parent
  // page is "use client" and auth-gated), so reading it here is safe and
  // avoids the cascading render a setState-in-effect would cause.
  const [preferences, setPreferences] = useState<Preferences>(storedPreferences);

  function toggle(key: string, enabled: boolean) {
    const next = { ...preferences, [key]: enabled };
    setPreferences(next);
    writeValue(NOTIFICATION_PREFERENCE_KEY, JSON.stringify(next));
  }

  return (
    <div className="flex flex-col gap-6">
      <Card className="border-info/25 bg-info/5">
        <CardContent className="flex items-start gap-3 py-4">
          <InfoIcon className="mt-0.5 h-[18px] w-[18px] shrink-0 text-info" />
          <p className="text-sm text-foreground">
            GeoCore notifies you inside the app, in the bell menu. It doesn&rsquo;t send
            email, SMS or push notifications yet, so there&rsquo;s nothing to configure
            for those.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>What you see in the app</CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          <p className="mb-4 text-sm text-muted">
            These settings apply to this browser.
          </p>
          <div className="flex flex-col gap-4">
            {PREFERENCES.map((preference) => (
              <div key={preference.key}>
                <Checkbox
                  label={preference.label}
                  checked={preferences[preference.key] ?? true}
                  onChange={(e) => toggle(preference.key, e.target.checked)}
                />
                <p className="ml-6 mt-0.5 text-xs text-muted">{preference.description}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
