"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";

/**
 * GeoCore synthetic demo workspace.
 *
 * This page is intentionally self-contained:
 * - no network calls
 * - no browser storage
 * - no auth context
 * - no real customer, quote, project, AI, email, invite or billing action
 *
 * Every interaction exists only in local React state and disappears on reset
 * or page reload.
 */

const TABS = [
  "Projects",
  "Customers",
  "Quotes",
  "Tasks",
  "Calendar",
  "Automations",
  "Communications",
  "GeoCore AI",
  "Settings",
] as const;

type Tab = (typeof TABS)[number];
type DemoQuoteKind = "stone" | "construction";

const PROJECTS = [
  { name: "Kitchen renovation - Richmond", stage: "In progress" },
  { name: "Bathroom renovation - Clapham", stage: "Scheduled" },
  { name: "Rear extension & refurbishment", stage: "Quoted" },
  { name: "Quartz worktop - Islington", stage: "Awaiting approval" },
];

const CUSTOMERS = [
  { name: "Sarah Whitfield", detail: "Richmond kitchen renovation" },
  { name: "The Clapham Family Trust", detail: "Bathroom renovation" },
  { name: "Marcus Oduya", detail: "Rear extension & refurbishment" },
  { name: "Islington Stoneworks Ltd", detail: "Quartz worktop install" },
];

const QUOTES = [
  { id: "Q-1048", title: "Kitchen renovation - Richmond", total: "£18,400" },
  { id: "Q-1051", title: "Bathroom renovation - Clapham", total: "£9,750" },
  { id: "Q-1055", title: "Quartz worktop - Islington", total: "£3,200" },
];

const CALENDAR_EVENTS = [
  "Mon 09:00 - Site survey, rear extension",
  "Wed 13:00 - Worktop template appointment, Islington",
  "Fri 10:30 - Kitchen handover, Richmond",
];

const AUTOMATIONS = [
  "Send quote follow-up after 3 days of no reply",
  "Notify project lead when a task is marked complete",
  "Remind customer 24 hours before a site visit",
];

const WORKFLOW_STEPS = [
  "Customer",
  "Quote",
  "Approval",
  "Project",
  "Handover",
] as const;

export default function DemoPage() {
  const [activeTab, setActiveTab] = useState<Tab>("Projects");
  const [taskComplete, setTaskComplete] = useState(false);

  // 0 initial
  // 1 customer created
  // 2 quote created
  // 3 quote sent
  // 4 quote approved
  // 5 project created
  // 6 handover complete
  const [workflowStage, setWorkflowStage] = useState(0);
  const [quoteKind, setQuoteKind] = useState<DemoQuoteKind | null>(null);

  const [aiResult, setAiResult] = useState("");
  const [emailSimulated, setEmailSimulated] = useState(false);
  const [inviteSimulated, setInviteSimulated] = useState(false);

  const demoQuote =
    quoteKind === "stone"
      ? {
          id: "DEMO-S-001",
          title: "Quartz worktop - Demo",
          total: "£4,250",
        }
      : quoteKind === "construction"
        ? {
            id: "DEMO-C-001",
            title: "Rear extension - Demo",
            total: "£18,400",
          }
        : null;

  function reset() {
    setActiveTab("Projects");
    setTaskComplete(false);
    setWorkflowStage(0);
    setQuoteKind(null);
    setAiResult("");
    setEmailSimulated(false);
    setInviteSimulated(false);
  }

  function workflowReached(step: (typeof WORKFLOW_STEPS)[number]) {
    if (step === "Customer") return workflowStage >= 1;
    if (step === "Quote") return workflowStage >= 2;
    if (step === "Approval") return workflowStage >= 4;
    if (step === "Project") return workflowStage >= 5;
    return workflowStage >= 6;
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            Demo Workspace
          </h1>
          <p className="mt-1 text-sm text-muted">
            This is an entirely synthetic demo workspace - no real customers,
            quotes, projects or messages. Nothing you do here is sent or saved.
          </p>
        </div>

        <Button variant="outline" size="sm" onClick={reset}>
          Reset demo workspace
        </Button>
      </div>

      <Card className="mb-4">
        <CardContent className="py-4">
          <p className="mb-3 text-sm font-medium text-foreground">
            Customer to handover demo
          </p>

          <div
            aria-label="Demo workflow progress"
            className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-5"
          >
            {WORKFLOW_STEPS.map((step) => (
              <div
                key={step}
                className="rounded-lg border border-border px-2 py-2 text-center text-xs"
              >
                <span className={workflowReached(step) ? "text-foreground" : "text-muted"}>
                  {workflowReached(step) ? "✓ " : ""}
                  {step}
                </span>
              </div>
            ))}
          </div>

          {workflowStage === 0 && (
            <Button onClick={() => setWorkflowStage(1)}>
              Create demo customer
            </Button>
          )}

          {workflowStage === 1 && (
            <div className="flex flex-wrap gap-2">
              <Button
                onClick={() => {
                  setQuoteKind("stone");
                  setWorkflowStage(2);
                }}
              >
                Create stone quote
              </Button>

              <Button
                variant="outline"
                onClick={() => {
                  setQuoteKind("construction");
                  setWorkflowStage(2);
                }}
              >
                Create construction quote
              </Button>
            </div>
          )}

          {workflowStage === 2 && (
            <Button onClick={() => setWorkflowStage(3)}>
              Send quote (simulated)
            </Button>
          )}

          {workflowStage === 3 && (
            <Button onClick={() => setWorkflowStage(4)}>
              Approve quote
            </Button>
          )}

          {workflowStage === 4 && (
            <Button onClick={() => setWorkflowStage(5)}>
              Convert to project
            </Button>
          )}

          {workflowStage === 5 && (
            <Button onClick={() => setWorkflowStage(6)}>
              Complete handover
            </Button>
          )}

          {workflowStage >= 6 && (
            <p className="text-sm font-medium text-foreground">
              Handover complete ✓
            </p>
          )}

          {workflowStage >= 1 && (
            <p className="mt-3 text-xs text-muted">
              Customer: GeoCore Demo Customer
              {demoQuote ? ` | Quote: ${demoQuote.id}` : ""}
            </p>
          )}
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardContent className="flex items-center justify-between gap-3 py-4">
          <p className="text-sm text-foreground">
            {taskComplete ? "Demo task complete" : "Demo task ready"}
          </p>

          <Button
            size="sm"
            disabled={taskComplete}
            onClick={() => setTaskComplete(true)}
          >
            Mark demo task complete
          </Button>
        </CardContent>
      </Card>

      <div
        role="tablist"
        aria-label="Demo Workspace sections"
        className="mb-4 flex flex-wrap gap-1 border-b border-border"
      >
        {TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={activeTab === tab}
            onClick={() => setActiveTab(tab)}
            className={
              "rounded-t-lg px-3 py-2 text-sm font-medium transition-colors " +
              (activeTab === tab
                ? "border-b-2 border-accent text-accent"
                : "text-muted hover:text-foreground")
            }
          >
            {tab}
          </button>
        ))}
      </div>

      <div role="tabpanel">
        {activeTab === "Projects" && (
          <ul className="flex flex-col gap-2">
            {workflowStage >= 5 && demoQuote && (
              <Card>
                <CardContent className="flex items-center justify-between py-3">
                  <span className="text-sm font-medium text-foreground">
                    {demoQuote.title}
                  </span>
                  <span className="text-xs text-muted">
                    {workflowStage >= 6 ? "Completed" : "In progress"}
                  </span>
                </CardContent>
              </Card>
            )}

            {PROJECTS.map((project) => (
              <Card key={project.name}>
                <CardContent className="flex items-center justify-between py-3">
                  <span className="text-sm text-foreground">{project.name}</span>
                  <span className="text-xs text-muted">{project.stage}</span>
                </CardContent>
              </Card>
            ))}
          </ul>
        )}

        {activeTab === "Customers" && (
          <ul className="flex flex-col gap-2">
            {workflowStage >= 1 && (
              <Card>
                <CardContent className="flex items-center justify-between py-3">
                  <span className="text-sm font-medium text-foreground">
                    GeoCore Demo Customer
                  </span>
                  <span className="text-xs text-muted">
                    Synthetic demo record
                  </span>
                </CardContent>
              </Card>
            )}

            {CUSTOMERS.map((customer) => (
              <Card key={customer.name}>
                <CardContent className="flex items-center justify-between py-3">
                  <span className="text-sm text-foreground">{customer.name}</span>
                  <span className="text-xs text-muted">{customer.detail}</span>
                </CardContent>
              </Card>
            ))}
          </ul>
        )}

        {activeTab === "Quotes" && (
          <ul className="flex flex-col gap-2">
            {workflowStage >= 2 && demoQuote && (
              <Card>
                <CardContent className="flex items-center justify-between py-3">
                  <span className="text-sm text-foreground">
                    <span className="font-medium">{demoQuote.id}</span>
                    {" - "}
                    {demoQuote.title}
                  </span>
                  <span className="text-xs text-muted">{demoQuote.total}</span>
                </CardContent>
              </Card>
            )}

            {QUOTES.map((quote) => (
              <Card key={quote.id}>
                <CardContent className="flex items-center justify-between py-3">
                  <span className="text-sm text-foreground">
                    <span className="font-medium">{quote.id}</span>
                    {" - "}
                    {quote.title}
                  </span>
                  <span className="text-xs text-muted">{quote.total}</span>
                </CardContent>
              </Card>
            ))}
          </ul>
        )}

        {activeTab === "Tasks" && (
          <Card>
            <CardContent className="py-3 text-sm text-foreground">
              {taskComplete ? "Demo task complete" : "Demo task ready"} - follow up
              on Q-1048
            </CardContent>
          </Card>
        )}

        {activeTab === "Calendar" && (
          <ul className="flex flex-col gap-2">
            {CALENDAR_EVENTS.map((event) => (
              <Card key={event}>
                <CardContent className="py-3 text-sm text-foreground">
                  {event}
                </CardContent>
              </Card>
            ))}
          </ul>
        )}

        {activeTab === "Automations" && (
          <ul className="flex flex-col gap-2">
            {AUTOMATIONS.map((automation) => (
              <Card key={automation}>
                <CardContent className="py-3 text-sm text-foreground">
                  {automation}
                </CardContent>
              </Card>
            ))}
          </ul>
        )}

        {activeTab === "Communications" && (
          <Card>
            <CardContent className="flex flex-col gap-3 py-4">
              <p className="text-sm text-foreground">
                Quote follow-up drafted (not sent)
              </p>

              <Button
                variant="outline"
                onClick={() => setEmailSimulated(true)}
              >
                Simulate customer email
              </Button>

              {emailSimulated && (
                <p className="text-sm text-muted">
                  Demo only - no real email was delivered.
                </p>
              )}
            </CardContent>
          </Card>
        )}

        {activeTab === "GeoCore AI" && (
          <Card>
            <CardContent className="flex flex-col gap-3 py-4">
              <p className="text-sm text-muted">
                GeoCore AI runs locally in this demo. Nothing is sent to the
                production AI service.
              </p>

              <Button
                disabled={!demoQuote}
                onClick={() => {
                  if (!demoQuote) return;
                  setAiResult(
                    `Prepared a follow-up task for ${demoQuote.id}. Demo only - nothing was sent or saved.`,
                  );
                }}
              >
                Ask GeoCore AI to prepare quote follow-up
              </Button>

              {aiResult && (
                <p className="text-sm text-foreground">{aiResult}</p>
              )}
            </CardContent>
          </Card>
        )}

        {activeTab === "Settings" && (
          <div className="flex flex-col gap-3">
            <Card>
              <CardContent className="flex flex-col gap-3 py-4">
                <Button
                  variant="outline"
                  onClick={() => setInviteSimulated(true)}
                >
                  Simulate team invite
                </Button>

                {inviteSimulated && (
                  <p className="text-sm text-muted">
                    Demo only - no invitation was delivered.
                  </p>
                )}

                <Button variant="outline" disabled>
                  Billing unavailable in demo
                </Button>
              </CardContent>
            </Card>

            <p className="text-sm text-muted">
              Demo actions are isolated from your real GeoCore workspace.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
