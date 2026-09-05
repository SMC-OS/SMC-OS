"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, EmptyState } from "@/components/ui/Card";
import { Input } from "@/components/ui/Field";
import { MapPinIcon, PlusIcon, SearchIcon } from "@/components/ui/icons";
import { ApiError, api } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";
import type { Customer } from "@/types/customer";

export default function CustomersPage() {
  const router = useRouter();
  const { isAuthenticated, isReady } = useAuth();
  const [customers, setCustomers] = useState<Customer[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!isReady) return;
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }
    api
      // A higher limit than the old default of 20: a construction
      // business with fifty customers was silently seeing thirty of them.
      // Real server-side pagination is follow-up work (Sprint 036 §10);
      // this is honest about being a bounded list rather than pretending.
      .getCustomers(200)
      .then(setCustomers)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Something went wrong.")
      );
  }, [isReady, isAuthenticated, router]);

  // Client-side filtering over an already-loaded list. Deliberately not a
  // server search: there is no search endpoint, and adding a debounced
  // round trip that filters the same 200 rows the browser already holds
  // would be slower and no more correct.
  const filtered = useMemo(() => {
    if (!customers) return null;
    const needle = query.trim().toLowerCase();
    if (!needle) return customers;
    return customers.filter((customer) =>
      [customer.name, customer.company_name, customer.email, customer.city, customer.postcode]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(needle))
    );
  }, [customers, query]);

  if (!isReady || !isAuthenticated) return null;

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
            Customers
          </h1>
          <p className="mt-1 text-sm text-muted">
            Homeowners, landlords and main contractors — everyone you work for.
          </p>
        </div>
        <Link href="/customers/new">
          <Button size="lg">
            <PlusIcon className="h-4 w-4" />
            New customer
          </Button>
        </Link>
      </div>

      {customers && customers.length > 0 && (
        <div className="relative mb-4">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <Input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by name, company, email or postcode"
            aria-label="Search customers"
            className="pl-9"
          />
        </div>
      )}

      <Card>
        <CardContent className="p-0">
          {error && <p className="p-5 text-sm text-danger">{error}</p>}

          {!error && customers === null && (
            <div className="space-y-2 p-5">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-14 animate-pulse rounded-lg bg-surface-hover" />
              ))}
            </div>
          )}

          {!error && customers?.length === 0 && (
            <EmptyState
              title="No customers yet"
              description="Add the people and companies you work for. Quotes, projects and documents all hang off a customer record."
              action={
                <Link href="/customers/new">
                  <Button>Add your first customer</Button>
                </Link>
              }
            />
          )}

          {filtered?.length === 0 && customers && customers.length > 0 && (
            <EmptyState
              title="No matches"
              description={`Nothing matches “${query}”.`}
            />
          )}

          {filtered && filtered.length > 0 && (
            <ul className="divide-y divide-border">
              {filtered.map((customer) => (
                <li key={customer.id}>
                  <Link
                    href={`/customers/${customer.id}`}
                    className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-surface-hover sm:px-5"
                  >
                    <Avatar name={customer.company_name || customer.name} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground">
                        {customer.company_name || customer.name}
                      </p>
                      <p className="truncate text-xs text-muted">
                        {customer.company_name ? `${customer.name} · ` : ""}
                        {customer.email ?? customer.phone ?? "No contact details"}
                      </p>
                    </div>

                    {(customer.city || customer.postcode) && (
                      <span className="hidden shrink-0 items-center gap-1 text-xs text-muted sm:flex">
                        <MapPinIcon className="h-3.5 w-3.5" />
                        {customer.city ?? customer.postcode}
                      </span>
                    )}

                    {customer.customer_type === "company" && (
                      <Badge tone="accent" className="hidden sm:inline-flex">
                        Company
                      </Badge>
                    )}

                    <span className="hidden shrink-0 text-xs text-muted md:block">
                      {formatRelativeTime(customer.created_at)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
