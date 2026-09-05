"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { CustomerForm } from "@/components/customers/CustomerForm";
import { api } from "@/lib/api";
import type { CustomerCreate } from "@/types/customer";

export default function NewCustomerPage() {
  const router = useRouter();
  const { isAuthenticated, isReady } = useAuth();

  useEffect(() => {
    if (isReady && !isAuthenticated) router.replace("/login");
  }, [isReady, isAuthenticated, router]);

  if (!isReady || !isAuthenticated) return null;

  async function handleSubmit(values: CustomerCreate) {
    const customer = await api.createCustomer(values);
    router.push(`/customers/${customer.id}`);
  }

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-6">
        <Link href="/customers" className="text-sm text-muted hover:text-foreground">
          &larr; Customers
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          New customer
        </h1>
        <p className="mt-1 text-sm text-muted">
          Only a name is required — everything else can be filled in later.
        </p>
      </div>

      <CustomerForm submitLabel="Save customer" onSubmit={handleSubmit} />
    </div>
  );
}
