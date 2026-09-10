"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { CommunicationTimeline } from "@/components/communications/CommunicationTimeline";
import { Card, CardContent } from "@/components/ui/Card";
import { InfoIcon } from "@/components/ui/icons";

/**
 * Communications (Sprint 039, Workstream A).
 *
 * Sprint 038 shipped a complete, production-verified outbound email
 * ledger — every send, every retry, every bounce and every delivery
 * confirmation from a real provider webhook — and no screen in the
 * product ever showed a single row of it. This is that screen.
 *
 * The distinction it exists to make visible: **"sent" is not "arrived".**
 * A provider accepting a message and a message reaching an inbox are two
 * different facts, and a business chasing an unanswered quote deserves to
 * know which one it has.
 */
export default function CommunicationsPage() {
  const router = useRouter();
  const { isAuthenticated, isReady } = useAuth();

  useEffect(() => {
    if (!isReady) return;
    if (!isAuthenticated) router.replace("/login");
  }, [isReady, isAuthenticated, router]);

  if (!isReady || !isAuthenticated) return null;

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
          Communications
        </h1>
        <p className="mt-1 text-sm text-muted">
          Every email GeoCore has sent for you, and whether it arrived.
        </p>
      </div>

      <Card className="mb-4 border-info/25 bg-info/5">
        <CardContent className="flex items-start gap-3 py-4">
          <InfoIcon className="mt-0.5 h-[18px] w-[18px] shrink-0 text-info" />
          <p className="text-sm text-foreground">
            <span className="font-medium">Sent</span> means your mail provider
            accepted the message. <span className="font-medium">Delivered</span>{" "}
            means it reached the inbox and the provider confirmed it. They are
            not the same thing, so GeoCore never shows one as the other.
          </p>
        </CardContent>
      </Card>

      <CommunicationTimeline
        limit={100}
        emptyTitle="No emails sent yet"
        emptyDescription="When you email a quote, invite a colleague or an automation contacts a customer, it will be recorded here."
      />
    </div>
  );
}
