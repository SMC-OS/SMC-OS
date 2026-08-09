"use client";

import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { CheckCircleIcon } from "@/components/ui/icons";
import { ApiError, api } from "@/lib/api";

export default function NewProjectPage() {
  const [name, setName] = useState("");
  const [customer, setCustomer] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      await api.logActivity({
        type: "project_created",
        title: "Project started",
        description: [name, customer && `for ${customer}`, notes]
          .filter(Boolean)
          .join(" — "),
      });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl">
      <div className="mb-6">
        <Link href="/projects" className="text-sm text-muted hover:text-foreground">
          &larr; Projects
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          New Project
        </h1>
      </div>

      <Card>
        <CardContent>
          {done ? (
            <div className="flex flex-col items-start gap-3 py-2">
              <CheckCircleIcon className="h-8 w-8 text-success" />
              <p className="text-sm font-medium text-foreground">
                Logged to Recent Activity.
              </p>
              <p className="text-sm text-muted">
                The full job pipeline (enquiry &rarr; quoted &rarr; booked
                &rarr; templated &rarr; fabricated &rarr; installed &rarr;
                complete) ships in Sprint 006. For now this shows up on the
                dashboard so the team can see it happened.
              </p>
              <div className="flex gap-2">
                <Link href="/">
                  <Button variant="outline">Back to dashboard</Button>
                </Link>
                <Button
                  onClick={() => {
                    setDone(false);
                    setName("");
                    setCustomer("");
                    setNotes("");
                  }}
                >
                  Add another
                </Button>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <Field label="Project name" htmlFor="name">
                <Input
                  id="name"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Riverside Kitchen Renovation"
                />
              </Field>
              <Field label="Customer" htmlFor="customer">
                <Input
                  id="customer"
                  value={customer}
                  onChange={(e) => setCustomer(e.target.value)}
                  placeholder="e.g. Chen family"
                />
              </Field>
              <Field label="Notes" htmlFor="notes">
                <Input
                  id="notes"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Optional"
                />
              </Field>

              {error && (
                <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
                  {error}
                </p>
              )}

              <Badge tone="info" className="w-fit">
                Not saved as a permanent record yet — full Projects module lands in Sprint 006
              </Badge>

              <Button type="submit" disabled={submitting}>
                {submitting ? "Saving…" : "Save project"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
