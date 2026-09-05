"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import CompanyIdentityCard from "@/components/settings/CompanyIdentityCard";
import { BillingCard } from "@/components/settings/BillingCard";
import { BrandingCard } from "@/components/settings/BrandingCard";
import { NotificationsCard } from "@/components/settings/NotificationsCard";
import { SecurityCard } from "@/components/settings/SecurityCard";
import { TeamCard } from "@/components/settings/TeamCard";
import { Card, CardContent } from "@/components/ui/Card";
import { SETTINGS_SECTIONS } from "@/lib/navigation";
import { cn } from "@/lib/utils";

/**
 * Settings V2 — Sprint 036, Workstream I.
 *
 * The previous Settings page was a single 483-line scroll: company
 * identity, team, billing, invite form and invitation list stacked on top
 * of each other, with billing — the thing an owner most needs to find —
 * fourth from the top.
 *
 * This is the same functionality organised by what a person came to do.
 * The section lives in the URL (?section=billing) so a section is
 * linkable and survives a refresh, which a piece of local component state
 * would not.
 *
 * Owner-only sections are hidden from Staff rather than shown disabled: a
 * greyed-out "Billing" row tells a member of staff there is something
 * they are not allowed to see, which is noise on a page they visit to
 * change their own notification settings. The server enforces the real
 * rule regardless (require_role(OWNER)).
 */
function SettingsContent() {
  const router = useRouter();
  const params = useSearchParams();
  const { isAuthenticated, isReady, role } = useAuth();

  const isOwner = role === "Owner";
  const sections = SETTINGS_SECTIONS.filter(
    (section) => !section.ownerOnly || isOwner
  );

  // Derived, not initialised once.
  //
  // A useState initialiser reading `sections` runs on the very first
  // render, when AuthProvider has not resolved the role yet — so
  // `sections` holds only the non-Owner ones and a deep link to
  // ?section=billing falls back to the first available section and stays
  // there even after the role arrives. That made an Owner-only section
  // unlinkable for the one person allowed to see it.
  //
  // `chosen` records an explicit click; until there is one, the URL
  // decides, and it is re-evaluated on every render as the role resolves.
  const [chosen, setChosen] = useState<string | null>(null);
  const requested = params.get("section");
  const active =
    (chosen && sections.some((section) => section.key === chosen) ? chosen : null) ??
    (sections.some((section) => section.key === requested) ? (requested as string) : null) ??
    sections[0]?.key ??
    "notifications";

  useEffect(() => {
    if (isReady && !isAuthenticated) router.replace("/login");
  }, [isReady, isAuthenticated, router]);

  if (!isReady || !isAuthenticated) return null;

  function select(key: string) {
    setChosen(key);
    // replaceState rather than router.push: switching a settings tab is
    // not a navigation someone expects the back button to undo one step
    // at a time, but the URL still has to be shareable.
    window.history.replaceState(null, "", `/settings?section=${key}`);
  }

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
          Settings
        </h1>
        <p className="mt-1 text-sm text-muted">
          Your company, your team and how GeoCore works for you.
        </p>
      </div>

      <div className="flex flex-col gap-6 lg:flex-row">
        {/* Horizontally scrolling tabs on a phone, a vertical list from
            `lg`. A vertical nav at 360px would eat half the screen before
            the content it navigates to. */}
        <nav
          aria-label="Settings sections"
          className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 lg:mx-0 lg:w-56 lg:shrink-0 lg:flex-col lg:overflow-visible lg:px-0"
        >
          {sections.map((section) => {
            const SectionIcon = section.icon;
            const selected = active === section.key;

            return (
              <button
                key={section.key}
                type="button"
                aria-current={selected ? "page" : undefined}
                onClick={() => select(section.key)}
                className={cn(
                  "flex shrink-0 items-center gap-2.5 rounded-lg px-3.5 py-2.5 text-sm font-medium transition-colors lg:w-full lg:text-left",
                  selected
                    ? "bg-accent text-accent-foreground"
                    : "text-muted hover:bg-surface-hover hover:text-foreground"
                )}
              >
                <SectionIcon className="h-[18px] w-[18px] shrink-0" />
                <span className="whitespace-nowrap lg:whitespace-normal">
                  {section.label}
                </span>
              </button>
            );
          })}
        </nav>

        <div className="min-w-0 flex-1">
          {sections.map(
            (section) =>
              active === section.key && (
                <div key={section.key}>
                  <p className="mb-4 text-sm text-muted">{section.description}</p>
                  {section.key === "company" && <CompanyIdentityCard />}
                  {section.key === "branding" && <BrandingCard />}
                  {section.key === "team" && <TeamCard />}
                  {section.key === "billing" && <BillingCard />}
                  {section.key === "notifications" && <NotificationsCard />}
                  {section.key === "security" && <SecurityCard />}
                </div>
              )
          )}

          {sections.length === 0 && (
            <Card>
              <CardContent>
                <p className="text-sm text-muted">
                  There&rsquo;s nothing here for your account to configure.
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={null}>
      <SettingsContent />
    </Suspense>
  );
}
