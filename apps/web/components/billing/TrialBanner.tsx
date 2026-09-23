"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { api } from "@/lib/api";
import type { Subscription } from "@/types/billing";

/**
 * Phase B — a slim, always-visible note while a workspace is on GeoCore's
 * no-card trial: days remaining, and a link to choose a plan. It turns
 * amber in the last 3 days. It renders nothing for paid, grandfathered or
 * Stripe-managed subscriptions (trial_state is only set for the no-card
 * trial), and nothing on /pricing itself, which shows its own full state.
 * An expired trial never reaches here: AppShell already sends that
 * workspace to /pricing.
 */
export function TrialBanner() {
  const pathname = usePathname();
  const { isReady, isAuthenticated, verificationRequired, billingAccessRequired, role } = useAuth();
  const [subscription, setSubscription] = useState<Subscription | null>(null);

  const eligible = isReady && isAuthenticated && !verificationRequired && !billingAccessRequired;

  useEffect(() => {
    if (!eligible) return;
    let cancelled = false;
    api
      .getSubscription()
      .then((sub) => {
        if (!cancelled) setSubscription(sub);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [eligible]);

  const state = subscription?.trial_state;
  if (!eligible || pathname === "/pricing" || (state !== "active" && state !== "ending_soon")) {
    return null;
  }

  const days = subscription?.trial_days_remaining ?? 0;
  const daysText = days === 1 ? "1 day" : `${days} days`;
  const endingSoon = state === "ending_soon";

  return (
    <div
      role="status"
      className={`flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2 text-sm lg:px-8 ${
        endingSoon ? "border-warning/30 bg-warning/10 text-warning" : "border-border bg-surface text-muted"
      }`}
    >
      <span>
        <strong className="font-medium">{daysText} left</strong> in your free trial. No card required.
      </span>
      {role === "Owner" ? (
        <Link href="/pricing" className="tap-link font-medium underline-offset-2 hover:underline">
          Choose a plan
        </Link>
      ) : (
        <span className="text-xs">Your workspace owner can choose a plan.</span>
      )}
    </div>
  );
}
