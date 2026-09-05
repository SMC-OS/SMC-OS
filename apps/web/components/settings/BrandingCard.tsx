"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Field, Textarea } from "@/components/ui/Field";
import { UploadIcon } from "@/components/ui/icons";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";
import { ApiError, api } from "@/lib/api";
import type { TenantProfile } from "@/types/tenant";

/**
 * Branding — Sprint 036, Workstream I.
 *
 * Replaces the "Logo URL" text field. Asking a builder to host their logo
 * somewhere and paste a URL is not a feature they can use, and it puts a
 * customer-facing document's branding at the mercy of a third-party host
 * that may go away.
 *
 * The upload is authenticated and Owner-only, capped at 2MB, and accepts
 * PNG/JPG/WebP only — SVG is excluded despite being the obvious logo
 * format, because SVG is XML that can carry script and this file is
 * served back to browsers (the same allowlist reasoning as document
 * uploads, ADR-032).
 *
 * The preview shows what actually appears at the top of a customer's
 * quote or invoice, so nobody has to download a PDF to find out.
 */
export function BrandingCard() {
  const { profile: workspaceProfile, refresh } = useWorkspace();
  const [profile, setProfile] = useState<TenantProfile | null>(null);
  const [footer, setFooter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Bumped after every upload so the browser refetches the logo instead
  // of showing the previous one from cache at the same URL.
  const [cacheBust, setCacheBust] = useState(0);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .getCompanyProfile()
      .then((loaded) => {
        setProfile(loaded);
        setFooter(loaded.document_footer ?? "");
      })
      .catch(() => setError("Could not load your branding."));
  }, []);

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const updated = await api.uploadCompanyLogo(file);
      setProfile(updated);
      setCacheBust((value) => value + 1);
      setStatus("Logo updated.");
      refresh();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 403
            ? "Only workspace owners can change branding."
            : err.message
          : "Could not upload that logo."
      );
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function removeLogo() {
    setBusy(true);
    setError(null);
    try {
      setProfile(await api.deleteCompanyLogo());
      setStatus("Logo removed.");
      refresh();
    } catch {
      setError("Could not remove the logo.");
    } finally {
      setBusy(false);
    }
  }

  async function saveFooter(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const updated = await api.updateCompanyProfile({ document_footer: footer });
      setProfile(updated);
      setStatus("Document footer saved.");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 403
          ? "Only workspace owners can change branding."
          : "Could not save the footer."
      );
    } finally {
      setBusy(false);
    }
  }

  const letterhead =
    workspaceProfile?.trading_name ||
    workspaceProfile?.legal_name ||
    workspaceProfile?.name ||
    "Your company";

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Logo</CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          <p className="mb-4 text-sm text-muted">
            Appears at the top of every quote and invoice your customers receive.
            PNG, JPG or WebP, up to 2MB.
          </p>

          <div className="flex flex-wrap items-center gap-4">
            <div className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-border bg-surface-raised">
              {profile?.has_uploaded_logo ? (
                <Image
                  src={`${api.companyLogoUrl()}?v=${cacheBust}`}
                  alt="Your company logo"
                  width={80}
                  height={80}
                  className="h-full w-full object-contain"
                  // The logo is served from the API origin behind an
                  // authenticated route, which Next's optimiser cannot
                  // fetch on the server. Unoptimised is the correct
                  // choice, not a shortcut.
                  unoptimized
                />
              ) : (
                <span className="text-xs text-muted">No logo</span>
              )}
            </div>

            <div className="flex flex-wrap gap-2">
              <input
                ref={fileInput}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="sr-only"
                id="logo-upload"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void upload(file);
                }}
              />
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => fileInput.current?.click()}
              >
                <UploadIcon className="h-4 w-4" />
                {profile?.has_uploaded_logo ? "Replace logo" : "Upload logo"}
              </Button>

              {profile?.has_uploaded_logo && (
                <Button variant="ghost" disabled={busy} onClick={removeLogo}>
                  Remove
                </Button>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Document footer</CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          <form onSubmit={saveFooter} className="flex flex-col gap-4">
            <Field
              label="Footer text"
              htmlFor="documentFooter"
              hint="Printed at the bottom of every quote and invoice — payment terms, registered office, bank details."
            >
              <Textarea
                id="documentFooter"
                rows={3}
                value={footer}
                onChange={(e) => setFooter(e.target.value)}
              />
            </Field>
            <Button type="submit" disabled={busy} className="self-start">
              {busy ? "Saving…" : "Save footer"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Document preview</CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          <p className="mb-4 text-sm text-muted">
            Roughly what the top and bottom of a customer&rsquo;s quote looks like.
          </p>
          <div className="rounded-xl border border-border bg-white p-6 text-[#16211c]">
            <div className="flex items-center gap-3 border-b border-[#e3ded4] pb-4">
              {profile?.has_uploaded_logo && (
                <Image
                  src={`${api.companyLogoUrl()}?v=${cacheBust}`}
                  alt=""
                  width={48}
                  height={48}
                  className="h-12 w-12 object-contain"
                  unoptimized
                />
              )}
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold uppercase tracking-wide">
                  {letterhead}
                </p>
                {workspaceProfile?.city && (
                  <p className="truncate text-xs opacity-70">
                    {[workspaceProfile.address_line1, workspaceProfile.city]
                      .filter(Boolean)
                      .join(", ")}
                  </p>
                )}
              </div>
            </div>
            <p className="mt-4 text-sm font-medium">Bathroom refit, 14 Elm Road</p>
            <p className="mt-1 text-xs opacity-70">Customer: A. Example</p>
            {footer && (
              <p className="mt-6 border-t border-[#e3ded4] pt-3 text-xs opacity-70">
                {footer}
              </p>
            )}
          </div>
          <p className="mt-3 text-xs text-muted">
            The real document is generated server-side — download a quote PDF to see
            it exactly.
          </p>
        </CardContent>
      </Card>

      {error && (
        <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">
          {error}
        </p>
      )}
      {status && !error && <p className="text-sm text-success">{status}</p>}
    </div>
  );
}
