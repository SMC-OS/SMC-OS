"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { AutomationBuilder } from "@/components/automations/AutomationBuilder";
import { AutomationRunsPanel } from "@/components/automations/AutomationRunsPanel";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, EmptyState } from "@/components/ui/Card";
import { InfoIcon, PlusIcon, TrashIcon, ZapIcon } from "@/components/ui/icons";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  ACTION_KIND_LABEL,
  ACTION_KIND_TONE,
  actionKind,
  actionLabel,
} from "@/types/automation";
import type {
  Automation,
  AutomationMeta,
  AutomationTemplate,
} from "@/types/automation";

/**
 * Automations — Sprint 036, Workstream G.
 *
 * Three things this page has to do well, in order of importance:
 *
 * 1. Say plainly what an automation can and cannot do. Every action is
 *    internal to the workspace; nothing here contacts a customer. That
 *    fact comes from the backend (`meta.delivery`) rather than being
 *    hardcoded copy, so it stays true if delivery is ever built.
 * 2. Get someone to a working automation without them learning a
 *    trigger/condition/action model — hence templates first, builder
 *    second.
 * 3. Show failures. An automation that quietly stopped working is the
 *    failure mode this feature has to defend against, so run history is
 *    on the page rather than behind a link.
 */
export default function AutomationsPage() {
  const router = useRouter();
  const { isAuthenticated, isReady, role } = useAuth();

  const [automations, setAutomations] = useState<Automation[] | null>(null);
  const [templates, setTemplates] = useState<AutomationTemplate[]>([]);
  const [meta, setMeta] = useState<AutomationMeta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);

  const isOwner = role === "Owner";

  const load = useCallback(() => {
    api
      .getAutomations()
      .then(setAutomations)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Something went wrong.")
      );
  }, []);

  useEffect(() => {
    if (!isReady) return;
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }
    load();
    api.getAutomationTemplates().then(setTemplates).catch(() => {});
    api.getAutomationMeta().then(setMeta).catch(() => {});
  }, [isReady, isAuthenticated, router, load]);

  if (!isReady || !isAuthenticated) return null;

  const activeTemplateKeys = new Set(
    (automations ?? []).map((automation) => automation.template_key).filter(Boolean)
  );

  async function activate(templateKey: string) {
    setBusyKey(templateKey);
    setError(null);
    try {
      await api.activateAutomationTemplate(templateKey);
      load();
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 403
          ? "Only the workspace owner can turn automations on."
          : "Could not turn that automation on."
      );
    } finally {
      setBusyKey(null);
    }
  }

  async function toggle(automation: Automation) {
    setBusyKey(automation.id);
    setError(null);
    try {
      await api.updateAutomation(automation.id, { enabled: !automation.enabled });
      load();
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 403
          ? "Only the workspace owner can change automations."
          : "Could not update that automation."
      );
    } finally {
      setBusyKey(null);
    }
  }

  async function remove(automation: Automation) {
    setBusyKey(automation.id);
    setError(null);
    try {
      await api.deleteAutomation(automation.id);
      load();
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 403
          ? "Only the workspace owner can delete automations."
          : "Could not delete that automation."
      );
    } finally {
      setBusyKey(null);
    }
  }

  const triggerLabel = (key: string) =>
    meta?.triggers.find((trigger) => trigger.key === key)?.label ?? key;

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
            Automations
          </h1>
          <p className="mt-1 text-sm text-muted">
            Let GeoCore do the chasing, the reminding and the paperwork.
          </p>
        </div>
        {isOwner && (
          <Button size="lg" onClick={() => setBuilding((open) => !open)}>
            <PlusIcon className="h-4 w-4" />
            {building ? "Close builder" : "Build your own"}
          </Button>
        )}
      </div>

      {/* Stated from the API, not from hardcoded copy — so it stays true
          the day outbound delivery is genuinely built. */}
      {meta && !meta.delivery.external_delivery_available && (
        <Card className="mb-6 border-info/25 bg-info/5">
          <CardContent className="flex items-start gap-3 py-4">
            <InfoIcon className="mt-0.5 h-[18px] w-[18px] shrink-0 text-info" />
            <p className="text-sm text-foreground">{meta.delivery.note}</p>
          </CardContent>
        </Card>
      )}

      {error && (
        <p className="mb-4 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">
          {error}
        </p>
      )}

      {building && isOwner && meta && (
        <div className="mb-6">
          <AutomationBuilder
            meta={meta}
            onCreated={() => {
              setBuilding(false);
              load();
            }}
          />
        </div>
      )}

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Your automations</CardTitle>
        </CardHeader>
        <CardContent className="p-0 pt-2">
          {automations === null && (
            <div className="space-y-2 p-5">
              {[0, 1].map((i) => (
                <div key={i} className="h-14 animate-pulse rounded-lg bg-surface-hover" />
              ))}
            </div>
          )}

          {automations?.length === 0 && (
            <EmptyState
              title="No automations yet"
              description={
                isOwner
                  ? "Turn on one of the ready-made ones below — it takes a click."
                  : "Your workspace owner can set these up."
              }
            />
          )}

          {automations && automations.length > 0 && (
            <ul className="divide-y divide-border">
              {automations.map((automation) => (
                <li key={automation.id} className="px-5 py-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate text-sm font-medium text-foreground">
                          {automation.name}
                        </p>
                        <Badge tone={automation.enabled ? "success" : "neutral"}>
                          {automation.enabled ? "On" : "Off"}
                        </Badge>
                      </div>
                      <p className="mt-1 text-xs text-muted">
                        When: {triggerLabel(automation.trigger_type)}
                      </p>
                      {/* Sprint 039 (Workstream E) — each action says what
                          it is AND which class it belongs to, so someone
                          scanning this list can see at a glance which
                          rules reach a customer. Labels come from the
                          backend catalogue; only the class wording and
                          colour are this app's. */}
                      <ul className="mt-2 flex flex-col gap-1.5">
                        {automation.actions.map((action, index) => {
                          const kind = actionKind(meta?.action_catalogue, action.type);
                          return (
                            <li
                              key={`${automation.id}-${index}`}
                              className="flex flex-wrap items-center gap-1.5"
                            >
                              <Badge tone="accent">
                                {actionLabel(meta?.action_catalogue, action.type)}
                              </Badge>
                              {kind && (
                                <Badge tone={ACTION_KIND_TONE[kind]}>
                                  {ACTION_KIND_LABEL[kind]}
                                </Badge>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    </div>

                    {isOwner && (
                      <div className="flex shrink-0 items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={busyKey === automation.id}
                          onClick={() => toggle(automation)}
                        >
                          {automation.enabled ? "Turn off" : "Turn on"}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={busyKey === automation.id}
                          onClick={() => remove(automation)}
                          aria-label={`Delete ${automation.name}`}
                        >
                          <TrashIcon className="h-4 w-4" />
                        </Button>
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Ready to turn on</CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {templates.map((template) => {
              const active = activeTemplateKeys.has(template.key);
              return (
                <div
                  key={template.key}
                  className={cn(
                    "flex flex-col gap-3 rounded-xl border p-4",
                    active ? "border-accent/40 bg-accent-subtle" : "border-border"
                  )}
                >
                  <div className="flex items-start gap-3">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-champagne-subtle text-champagne">
                      <ZapIcon className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground">{template.name}</p>
                      <p className="mt-0.5 text-sm text-muted">{template.description}</p>
                    </div>
                  </div>

                  {isOwner && (
                    <Button
                      variant={active ? "ghost" : "outline"}
                      size="sm"
                      className="self-start"
                      disabled={active || busyKey === template.key}
                      onClick={() => activate(template.key)}
                    >
                      {active ? "Already on" : busyKey === template.key ? "Turning on…" : "Turn on"}
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <AutomationRunsPanel />
    </div>
  );
}
