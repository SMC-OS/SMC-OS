"use client";

import { useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Field, Input, Select, Textarea } from "@/components/ui/Field";
import { PlusIcon, TrashIcon } from "@/components/ui/icons";
import { ApiError, api } from "@/lib/api";
import { ACTION_LABELS } from "@/types/automation";
import type { AutomationAction, AutomationMeta } from "@/types/automation";

interface ActionRow extends AutomationAction {
  key: string;
}

let nextKey = 0;
function blankAction(type = "create_task"): ActionRow {
  nextKey += 1;
  return { key: `action-${nextKey}`, type, config: { title: "", due_in_days: 1 } };
}

/**
 * Build your own automation — Sprint 036, Workstream G.
 *
 * Deliberately narrow. It offers exactly the triggers and actions the
 * engine implements (both fetched from the backend, never hardcoded
 * here), so the builder cannot compose a rule the engine will refuse.
 *
 * Conditions are not exposed in this first version, and that is a
 * decision rather than an omission: an unconditional rule with a clear
 * trigger is understandable at a glance, and a condition editor is where
 * a rules builder becomes a programming language nobody asked for. The
 * API accepts conditions today, so a rule can carry them the moment
 * there is a UI worth giving them — see docs/SPRINTS/sprint-036.md §10.
 */
export function AutomationBuilder({
  meta,
  onCreated,
}: {
  meta: AutomationMeta;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [trigger, setTrigger] = useState(meta.triggers[0]?.key ?? "");
  const [actions, setActions] = useState<ActionRow[]>([blankAction()]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedTrigger = useMemo(
    () => meta.triggers.find((option) => option.key === trigger),
    [meta.triggers, trigger]
  );

  // create_project_from_quote only makes sense on quote.approved — the
  // handoff endpoint refuses anything that is not approved, so offering
  // it elsewhere would build a rule guaranteed to record failures.
  const availableActions = meta.actions.filter(
    (action) =>
      action !== "create_project_from_quote" || trigger === "quote.approved"
  );

  function updateAction(key: string, patch: Partial<ActionRow>) {
    setActions((rows) =>
      rows.map((row) => (row.key === key ? { ...row, ...patch } : row))
    );
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      await api.createAutomation({
        name: name.trim(),
        trigger_type: trigger,
        conditions: [],
        actions: actions.map((action) => ({
          type: action.type,
          config: action.config,
        })),
      });
      onCreated();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 403
            ? "Only the workspace owner can create automations."
            : "Check the automation — every action needs a title."
          : "Something went wrong."
      );
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>New automation</CardTitle>
      </CardHeader>
      <CardContent className="pt-4">
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <Field label="Name" htmlFor="automationName" required>
            <Input
              id="automationName"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Chase every approved job"
            />
          </Field>

          <Field
            label="When this happens"
            htmlFor="trigger"
            hint={selectedTrigger?.description}
          >
            <Select
              id="trigger"
              value={trigger}
              onChange={(e) => setTrigger(e.target.value)}
            >
              {meta.triggers.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>

          <div>
            <div className="mb-2 flex items-center justify-between gap-3">
              <p className="text-sm font-medium text-foreground">Do this</p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setActions((rows) => [...rows, blankAction()])}
              >
                <PlusIcon className="h-4 w-4" />
                Add
              </Button>
            </div>

            <div className="flex flex-col gap-3">
              {actions.map((action, index) => (
                <div
                  key={action.key}
                  className="rounded-xl border border-border bg-surface-raised p-4"
                >
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <span className="text-xs font-medium uppercase tracking-wide text-muted">
                      Action {index + 1}
                    </span>
                    {actions.length > 1 && (
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Remove action ${index + 1}`}
                        onClick={() =>
                          setActions((rows) => rows.filter((row) => row.key !== action.key))
                        }
                      >
                        <TrashIcon className="h-4 w-4" />
                      </Button>
                    )}
                  </div>

                  <div className="flex flex-col gap-4">
                    <Field label="Action" htmlFor={`type-${action.key}`}>
                      <Select
                        id={`type-${action.key}`}
                        value={action.type}
                        onChange={(e) => updateAction(action.key, { type: e.target.value })}
                      >
                        {availableActions.map((type) => (
                          <option key={type} value={type}>
                            {ACTION_LABELS[type] ?? type}
                          </option>
                        ))}
                      </Select>
                    </Field>

                    {action.type !== "create_project_from_quote" && (
                      <>
                        <Field
                          label="Title"
                          htmlFor={`title-${action.key}`}
                          required
                          hint="Use {customer_name}, {title} or {name} to fill in details from the record."
                        >
                          <Input
                            id={`title-${action.key}`}
                            required
                            value={action.config.title ?? ""}
                            onChange={(e) =>
                              updateAction(action.key, {
                                config: { ...action.config, title: e.target.value },
                              })
                            }
                            placeholder="Follow up {customer_name}"
                          />
                        </Field>

                        <Field label="Message" htmlFor={`body-${action.key}`}>
                          <Textarea
                            id={`body-${action.key}`}
                            rows={2}
                            value={action.config.body ?? action.config.message ?? ""}
                            onChange={(e) =>
                              updateAction(action.key, {
                                config: { ...action.config, body: e.target.value },
                              })
                            }
                          />
                        </Field>

                        {action.type !== "create_notification" && (
                          <Field label="Due in (days)" htmlFor={`due-${action.key}`}>
                            <Input
                              id={`due-${action.key}`}
                              type="number"
                              min={0}
                              max={365}
                              value={action.config.due_in_days ?? 1}
                              onChange={(e) =>
                                updateAction(action.key, {
                                  config: {
                                    ...action.config,
                                    due_in_days: Number(e.target.value) || 0,
                                  },
                                })
                              }
                            />
                          </Field>
                        )}
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {error && (
            <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">
              {error}
            </p>
          )}

          <Button type="submit" disabled={submitting} className="self-start">
            {submitting ? "Saving…" : "Create automation"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
