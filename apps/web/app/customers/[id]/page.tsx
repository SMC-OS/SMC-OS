"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Avatar } from "@/components/ui/Avatar";
import { Card, CardContent } from "@/components/ui/Card";
import { ApiError, api } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";
import type { Customer } from "@/types/customer";

export default function CustomerDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { isAuthenticated, isReady } = useAuth();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isReady) return;
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }
    api
      .getCustomer(params.id)
      .then(setCustomer)
      .catch((err) =>
        setError(
          err instanceof ApiError && err.status === 404
            ? "Customer not found."
            : "Something went wrong."
        )
      );
  }, [isReady, isAuthenticated, router, params.id]);

  if (!isReady || !isAuthenticated) return null;

  return (
    <div className="mx-auto max-w-xl">
      <div className="mb-6">
        <Link href="/customers" className="text-sm text-muted hover:text-foreground">
          &larr; Customers
        </Link>
      </div>

      {error && (
        <Card>
          <CardContent>
            <p className="text-sm text-danger">{error}</p>
          </CardContent>
        </Card>
      )}

      {!error && !customer && (
        <p className="text-sm text-muted">Loading…</p>
      )}

      {customer && (
        <Card>
          <CardContent>
            <div className="flex items-center gap-3">
              <Avatar name={customer.name} className="h-12 w-12 text-base" />
              <div>
                <h1 className="text-xl font-semibold tracking-tight text-foreground">
                  {customer.name}
                </h1>
                <p className="text-xs text-muted">
                  Added {formatRelativeTime(customer.created_at)}
                </p>
              </div>
            </div>

            <dl className="mt-6 space-y-3 border-t border-border pt-4">
              <div>
                <dt className="text-xs font-medium text-muted">Email</dt>
                <dd className="text-sm text-foreground">
                  {customer.email ?? "—"}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-muted">Phone</dt>
                <dd className="text-sm text-foreground">
                  {customer.phone ?? "—"}
                </dd>
              </div>
            </dl>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
