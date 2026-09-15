"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";

/**
 * Sprint 039 V1 — Try Demo / Demo Workspace.
 *
 * Entirely self-contained: no network calls, no browser storage, no
 * auth context. Every value here is local component state seeded once
 * at render time, so "reset" is just restoring that seed — there is
 * nothing external to clean up, and nothing here can leak into or read
 * from a real tenant.
 */

const TABS = [
  "Projects",
  "Customers",
  "Quotes",
  "Tasks",
  "Calendar",
  "Automations",
  "Communications",
  "Settings",
] as const;

type Tab = (typeof TABS)[number];

const PROJECTS = [
  { name: "Kitchen renovation — Richmond", stage: "In progress" },
  { name: "Bathroom renovation — Clapham", stage: "Scheduled" },
  { name: "Rear extension & refurbishment", stage: "Quoted" },
  { name: "Quartz worktop — Islington", stage: "Awaiting approval" },
];

const CUSTOMERS = [
  { name: "Sarah Whitfield", detail: "Richmond kitchen renovation" },
  { name: "The Clapham Family Trust", detail: "Bathroom renovation" },
  { name: "Marcus Oduya", detail: "Rear extension & refurbishment" },
  { name: "Islington Stoneworks Ltd", detail: "Quartz worktop install" },
];

const QUOTES = [
  { id: "Q-1048", title: "Kitchen renovation — Richmond", total: "£18,400" },
  { id: "Q-1051", title: "Bathroom renovation — Clapham", total: "£9,750" },
  { id: "Q-1055", title: "Quartz worktop — Islington", total: "£3,200" },
];

const CALENDAR_EVENTS = [
  "Mon 09:00 — Site survey, rear extension",
  "Wed 13:00 — Worktop template appointment, Islington",
  "Fri 10:30 — Kitchen handover, Richmond",
];

const AUTOMATIONS = [
  "Send quote follow-up after 3 days of no reply",
  "Notify project lead when a task is marked complete",
  "Remind customer 24 hours before a site visit",
];

export default function DemoPage() {
  const [activeTab, setActiveTab] = useState<Tab>("Projects");
  const [taskComplete, setTaskComplete] = useState(false);

  function reset() {
    setActiveTab("Projects");
    setTaskComplete(false);
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            Demo Workspace
          </h1>
          <p className="mt-1 text-sm text-muted">
            This is an entirely synthetic demo workspace — no real customers,
            quotes, projects or messages. Nothing you do here is sent
            anywhere or saved anywhere.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={reset}>
          Reset demo workspace
        </Button>
      </div>

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
            {QUOTES.map((quote) => (
              <Card key={quote.id}>
                <CardContent className="flex items-center justify-between py-3">
                  <span className="text-sm text-foreground">
                    <span className="font-medium">{quote.id}</span> — {quote.title}
                  </span>
                  <span className="text-xs text-muted">{quote.total}</span>
                </CardContent>
              </Card>
            ))}
          </ul>
        )}

        {activeTab === "Tasks" && (
          <ul className="flex flex-col gap-2">
            <Card>
              <CardContent className="py-3 text-sm text-foreground">
                {taskComplete ? "Demo task complete" : "Demo task ready"} — follow up
                on Q-1048
              </CardContent>
            </Card>
          </ul>
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
            <CardContent className="py-3 text-sm text-foreground">
              Quote follow-up drafted (not sent)
            </CardContent>
          </Card>
        )}

        {activeTab === "Settings" && (
          <div className="flex flex-col gap-3">
            <Card>
              <CardContent className="flex flex-col gap-2 py-3">
                <Button variant="outline" disabled>
                  Send email unavailable in demo
                </Button>
                <Button variant="outline" disabled>
                  Invite unavailable in demo
                </Button>
                <Button variant="outline" disabled>
                  Billing unavailable in demo
                </Button>
              </CardContent>
            </Card>
            <p className="text-sm text-muted">
              AI is temporarily unavailable in the demo workspace.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
