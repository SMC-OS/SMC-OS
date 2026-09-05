"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { GeneralQuoteBuilder } from "@/components/quotes/GeneralQuoteBuilder";
import { Card, CardContent } from "@/components/ui/Card";
import { LayersIcon } from "@/components/ui/icons";

/**
 * New quote — Sprint 036, Workstream E.
 *
 * The general construction quote is the default, because GeoCore quotes
 * building, renovation, extensions, kitchens, bathrooms, roofing,
 * flooring, decorating, plumbing, electrics, carpentry and stone. The
 * specialist stone and worktop form still exists at /quotes/new/stone,
 * unchanged, and is offered here rather than hidden — it is a genuinely
 * better tool for that job, because it prices from the material
 * catalogue by slab area rather than by hand.
 */
function NewQuoteContent() {
  const router = useRouter();
  const params = useSearchParams();
  const { isAuthenticated, isReady } = useAuth();

  useEffect(() => {
    if (isReady && !isAuthenticated) router.replace("/login");
  }, [isReady, isAuthenticated, router]);

  if (!isReady || !isAuthenticated) return null;

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6">
        <Link href="/quotes" className="tap-link text-sm text-muted hover:text-foreground">
          &larr; Quotes
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
          New quote
        </h1>
        <p className="mt-1 text-sm text-muted">
          Price the job line by line — labour, materials, plant, anything.
        </p>
      </div>

      <Link href="/quotes/new/stone" className="mb-6 block">
        <Card className="transition-colors hover:border-border-strong hover:bg-surface-hover">
          <CardContent className="flex items-center gap-3 py-4">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-champagne-subtle text-champagne">
              <LayersIcon className="h-[18px] w-[18px]" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-medium text-foreground">
                Quoting stone or worktops?
              </p>
              <p className="text-sm text-muted">
                Use the specialist template — it prices by slab from your material
                catalogue.
              </p>
            </div>
          </CardContent>
        </Card>
      </Link>

      <GeneralQuoteBuilder initialCustomerId={params.get("customer") ?? undefined} />
    </div>
  );
}

export default function NewQuotePage() {
  // useSearchParams needs a Suspense boundary in the App Router — without
  // one, this page opts the whole route into client-side rendering at
  // build time and Next.js fails the production build.
  return (
    <Suspense fallback={null}>
      <NewQuoteContent />
    </Suspense>
  );
}
