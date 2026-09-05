"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Field, Input, Select, ToggleChip } from "@/components/ui/Field";
import { CheckIcon, SparklesIcon, ZapIcon } from "@/components/ui/icons";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { SUPPORTED_CURRENCIES } from "@/types/tenant";
import type { Trade } from "@/types/quote";

type Step = "trades" | "company" | "team" | "done";

const STEPS: { key: Step; label: string }[] = [
  { key: "trades", label: "Your work" },
  { key: "company", label: "Your company" },
  { key: "team", label: "Your team" },
];

/**
 * Onboarding V2 — Sprint 036, Workstream J.
 *
 * Three steps, all skippable, none of them blocking. The whole flow is
 * optional by design: a builder who signed up on a phone between jobs
 * should be able to get to the product, and setup that stops them is
 * setup they will resent rather than complete.
 *
 * The most important behaviour here is the one you cannot see: a
 * workspace that is already in use never reaches this page. `required`
 * comes from the backend and is computed from whether the workspace has
 * real customers, quotes or projects — not from a column — because every
 * workspace that existed before Sprint 036 has a null completion date and
 * sending an established business through a setup wizard would be a
 * regression dressed as a feature.
 *
 * The trade selection is real: it is stored on the workspace and drives
 * which quote template a trade opens by default. It is not a survey.
 */
export default function OnboardingPage() {
  const router = useRouter();
  const { isAuthenticated, isReady, tenantName } = useAuth();
  const { refresh } = useWorkspace();

  const [step, setStep] = useState<Step>("trades");
  const [trades, setTrades] = useState<Trade[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [currency, setCurrency] = useState("GBP");
  const [legalName, setLegalName] = useState("");
  const [city, setCity] = useState("");
  const [phone, setPhone] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteLink, setInviteLink] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!isReady) return;
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }

    let cancelled = false;
    api
      .getOnboardingState()
      .then((state) => {
        if (cancelled) return;
        if (!state.required) {
          // Already set up, or already being used. Straight through.
          router.replace("/");
          return;
        }
        setSelected(state.trades);
        setCurrency(state.currency);
        setChecked(true);
      })
      .catch(() => {
        // A failure to load setup state must not lock someone out of
        // their own workspace — show the flow rather than a dead end.
        if (!cancelled) setChecked(true);
      });

    api.getTrades().then((loaded) => !cancelled && setTrades(loaded)).catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [isReady, isAuthenticated, router]);

  if (!isReady || !isAuthenticated || !checked) return null;

  function toggleTrade(key: string, on: boolean) {
    setSelected((current) =>
      on ? [...current, key] : current.filter((value) => value !== key)
    );
  }

  async function saveTrades() {
    setBusy(true);
    setError(null);
    try {
      await api.updateOnboarding({ trades: selected, currency });
      refresh();
      setStep("company");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 403
          ? "Only the workspace owner can finish setting up."
          : "Could not save that. You can set it later in Settings."
      );
    } finally {
      setBusy(false);
    }
  }

  async function saveCompany() {
    setBusy(true);
    setError(null);
    try {
      await api.updateCompanyProfile({
        legal_name: legalName.trim() || null,
        city: city.trim() || null,
        contact_phone: phone.trim() || null,
      });
      refresh();
      setStep("team");
    } catch {
      setError("Could not save that. You can set it later in Settings.");
    } finally {
      setBusy(false);
    }
  }

  async function invite() {
    setBusy(true);
    setError(null);
    try {
      const created = await api.createInvitation(inviteEmail);
      setInviteLink(`${window.location.origin}/invite/${created.token}`);
    } catch {
      setError("Could not create that invitation. You can invite people from Settings.");
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    setBusy(true);
    try {
      await api.updateOnboarding({ complete: true });
      refresh();
    } catch {
      // Marking completion is best effort. Someone who has reached the
      // end of setup must not be held there by a failed write — the
      // backend also treats a workspace with real data as complete.
    } finally {
      router.replace("/");
    }
  }

  const stepIndex = STEPS.findIndex((entry) => entry.key === step);

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
          Set up {tenantName ?? "your workspace"}
        </h1>
        <p className="mt-1 text-sm text-muted">
          Three quick questions. Skip any of them — nothing here is required.
        </p>
      </div>

      <ol className="mb-6 flex items-center gap-2" aria-label="Setup progress">
        {STEPS.map((entry, index) => (
          <li key={entry.key} className="flex flex-1 items-center gap-2">
            <span
              className={cn(
                "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
                index < stepIndex
                  ? "bg-accent text-accent-foreground"
                  : index === stepIndex
                    ? "border-2 border-accent text-accent"
                    : "border border-border text-muted"
              )}
              aria-current={index === stepIndex ? "step" : undefined}
            >
              {index < stepIndex ? <CheckIcon className="h-3.5 w-3.5" /> : index + 1}
            </span>
            <span
              className={cn(
                "hidden text-sm sm:block",
                index === stepIndex ? "font-medium text-foreground" : "text-muted"
              )}
            >
              {entry.label}
            </span>
            {index < STEPS.length - 1 && <span className="h-px flex-1 bg-border" />}
          </li>
        ))}
      </ol>

      {error && (
        <p className="mb-4 rounded-lg bg-warning/10 px-3 py-2 text-sm text-warning" role="alert">
          {error}
        </p>
      )}

      {step === "trades" && (
        <Card>
          <CardContent>
            <h2 className="text-lg font-semibold text-foreground">
              What kind of work do you do?
            </h2>
            <p className="mt-1 text-sm text-muted">
              Pick everything that applies. This sets up your quote templates — you can
              always quote anything.
            </p>

            <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-3">
              {trades.map((trade) => (
                <ToggleChip
                  key={trade.key}
                  checked={selected.includes(trade.key)}
                  onChange={(on) => toggleTrade(trade.key, on)}
                >
                  {trade.label}
                </ToggleChip>
              ))}
            </div>

            <div className="mt-6 max-w-xs">
              <Field label="Currency" htmlFor="currency">
                <Select
                  id="currency"
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                >
                  {SUPPORTED_CURRENCIES.map((code) => (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>

            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Button size="lg" disabled={busy} onClick={saveTrades}>
                Continue
              </Button>
              <Button variant="ghost" onClick={() => setStep("company")}>
                Skip
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === "company" && (
        <Card>
          <CardContent>
            <h2 className="text-lg font-semibold text-foreground">Your company</h2>
            <p className="mt-1 text-sm text-muted">
              These appear on the quotes your customers receive. You can fill in the
              rest — VAT number, registered address, logo — in Settings.
            </p>

            <div className="mt-5 flex flex-col gap-5">
              <Field label="Registered or trading name" htmlFor="legalName">
                <Input
                  id="legalName"
                  value={legalName}
                  onChange={(e) => setLegalName(e.target.value)}
                  placeholder="e.g. Hartley Building Ltd"
                />
              </Field>
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                <Field label="Town or city" htmlFor="city">
                  <Input id="city" value={city} onChange={(e) => setCity(e.target.value)} />
                </Field>
                <Field label="Phone" htmlFor="phone">
                  <Input
                    id="phone"
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                  />
                </Field>
              </div>
            </div>

            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Button size="lg" disabled={busy} onClick={saveCompany}>
                Continue
              </Button>
              <Button variant="ghost" onClick={() => setStep("team")}>
                Skip
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === "team" && (
        <Card>
          <CardContent>
            <h2 className="text-lg font-semibold text-foreground">Bring your team in</h2>
            <p className="mt-1 text-sm text-muted">
              {/* The honest version. GeoCore has no email delivery, so
                  the link is presented as the output of the action
                  rather than as an apology for a missing feature. */}
              We&rsquo;ll give you a private joining link to send them however you
              normally get hold of your team.
            </p>

            <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-end">
              <Field label="Their email" htmlFor="inviteEmail" className="flex-1">
                <Input
                  id="inviteEmail"
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="colleague@yourcompany.co.uk"
                />
              </Field>
              <Button variant="outline" disabled={busy || !inviteEmail} onClick={invite}>
                Create link
              </Button>
            </div>

            {inviteLink && (
              <div className="mt-4 rounded-xl border border-accent/30 bg-accent-subtle p-4">
                <p className="text-sm font-medium text-foreground">Joining link ready</p>
                <Input
                  readOnly
                  value={inviteLink}
                  onFocus={(e) => e.currentTarget.select()}
                  aria-label="Joining link"
                  className="mt-2 text-xs"
                />
              </div>
            )}

            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Button size="lg" disabled={busy} onClick={() => setStep("done")}>
                Continue
              </Button>
              <Button variant="ghost" onClick={() => setStep("done")}>
                Skip
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === "done" && (
        <Card>
          <CardContent className="text-center">
            <Badge tone="success">Ready</Badge>
            <h2 className="mt-3 text-lg font-semibold text-foreground">
              You&rsquo;re set up
            </h2>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted">
              Add a customer, price a job, and let GeoCore chase the rest.
            </p>

            <div className="mt-6 grid grid-cols-1 gap-3 text-left sm:grid-cols-2">
              <Link
                href="/quotes/new"
                className="rounded-xl border border-border p-4 transition-colors hover:border-border-strong hover:bg-surface-hover"
              >
                <p className="text-sm font-medium text-foreground">Price your first job</p>
                <p className="mt-0.5 text-sm text-muted">
                  Line by line, in the trade you actually work in.
                </p>
              </Link>
              <Link
                href="/automations"
                className="rounded-xl border border-border p-4 transition-colors hover:border-border-strong hover:bg-surface-hover"
              >
                <p className="flex items-center gap-1.5 text-sm font-medium text-foreground">
                  <ZapIcon className="h-4 w-4 text-champagne" />
                  Turn on an automation
                </p>
                <p className="mt-0.5 text-sm text-muted">
                  Chase unanswered quotes without remembering to.
                </p>
              </Link>
            </div>

            <Button size="lg" className="mt-6" disabled={busy} onClick={finish}>
              <SparklesIcon className="h-4 w-4" />
              Go to GeoCore
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
