"use client";

import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { CheckCircleIcon } from "@/components/ui/icons";
import { ApiError, api } from "@/lib/api";

export default function NewCustomerPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      await api.logActivity({
        type: "customer_added",
        title: "New customer added",
        description: [name, email, phone].filter(Boolean).join(" — "),
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
        <Link href="/customers" className="text-sm text-muted hover:text-foreground">
          &larr; Customers
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          New Customer
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
                Full customer records — with quote and project history —
                arrive with the CRM in Sprint 004. For now this shows up on
                the dashboard so the team can see it happened.
              </p>
              <div className="flex gap-2">
                <Link href="/">
                  <Button variant="outline">Back to dashboard</Button>
                </Link>
                <Button onClick={() => { setDone(false); setName(""); setEmail(""); setPhone(""); }}>
                  Add another
                </Button>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <Field label="Full name" htmlFor="name">
                <Input
                  id="name"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. James Okafor"
                />
              </Field>
              <Field label="Email" htmlFor="email">
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="james@example.com"
                />
              </Field>
              <Field label="Phone" htmlFor="phone">
                <Input
                  id="phone"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="07123 456789"
                />
              </Field>

              {error && (
                <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
                  {error}
                </p>
              )}

              <Badge tone="info" className="w-fit">
                Not saved as a permanent record yet — full CRM lands in Sprint 004
              </Badge>

              <Button type="submit" disabled={submitting}>
                {submitting ? "Saving…" : "Save customer"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
