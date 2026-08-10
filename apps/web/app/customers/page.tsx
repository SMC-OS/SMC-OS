"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Avatar } from "@/components/ui/Avatar";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { PlusIcon } from "@/components/ui/icons";
import { ApiError, api } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";
import type { Customer } from "@/types/customer";

export default function CustomersPage() {
  const router = useRouter();
  const { isAuthenticated, isReady } = useAuth();
  const [customers, setCustomers] = useState<Customer[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isReady) return;
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }
    api
      .getCustomers()
      .then(setCustomers)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Something went wrong.")
      );
  }, [isReady, isAuthenticated, router]);

  if (!isReady || !isAuthenticated) return null;

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            Customers
          </h1>
          <p className="mt-1 text-sm text-muted">Every customer on file.</p>
        </div>
        <Link href="/customers/new">
          <Button>
            <PlusIcon className="h-4 w-4" />
            New Customer
          </Button>
        </Link>
      </div>

      <Card>
        <CardContent className="p-0">
          {error && <p className="p-5 text-sm text-danger">{error}</p>}
          {!error && customers === null && (
            <p className="p-5 text-center text-sm text-muted">Loading…</p>
          )}
          {!error && customers?.length === 0 && (
            <p className="p-5 text-center text-sm text-muted">
              No customers yet — add one to see it here.
            </p>
          )}
          {customers && customers.length > 0 && (
            <ul className="divide-y divide-border">
              {customers.map((customer) => (
                <li key={customer.id}>
                  <Link
                    href={`/customers/${customer.id}`}
                    className="flex items-center gap-3 px-5 py-3 hover:bg-surface-hover"
                  >
                    <Avatar name={customer.name} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground">
                        {customer.name}
                      </p>
                      {customer.email && (
                        <p className="truncate text-xs text-muted">{customer.email}</p>
                      )}
                    </div>
                    <span className="shrink-0 text-xs text-muted">
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
