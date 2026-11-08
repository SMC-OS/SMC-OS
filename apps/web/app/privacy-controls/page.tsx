"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/auth/AuthProvider";
import { PrivacyCard } from "@/components/settings/PrivacyCard";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";

export default function PrivacyControlsPage() {
  const { isReady, isAuthenticated, verificationRequired, role } = useAuth();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (isReady && !isAuthenticated) router.replace("/login");
  }, [isReady, isAuthenticated, router]);
  if (!isReady || !isAuthenticated || verificationRequired) return null;
  async function download() {
    setBusy(true);
    setError(null);
    try {
      await api.downloadWorkspaceExport();
    } catch {
      setError(
        "Could not download your export. Please retry or contact privacy@geocore.one.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <h1 className="text-2xl font-semibold">Privacy &amp; data controls</h1>
      <p>
        These controls remain available when your trial or subscription ends.
      </p>
      <PrivacyCard />
      {role === "Owner" && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">Workspace data export</h2>
          <p>
            This self-service ZIP contains customer, project, quote and document
            metadata. It does not include uploaded file contents or every
            operational record. Contact privacy@geocore.one for assistance with
            additional access, correction or deletion requests.
          </p>
          <Button type="button" disabled={busy} onClick={download}>
            {busy ? "Downloading…" : "Download workspace metadata"}
          </Button>
          {error && <p role="alert">{error}</p>}
        </section>
      )}
      <p>
        For a privacy request, contact{" "}
        <a className="underline" href="mailto:privacy@geocore.one">
          privacy@geocore.one
        </a>
        . Do not email passwords or unnecessary sensitive documents.
      </p>
      <Link className="underline" href="/pricing">
        Plans and billing
      </Link>
    </main>
  );
}
