"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { CheckCircleIcon } from "@/components/ui/icons";
import { PasswordField } from "@/components/ui/PasswordField";
import { PasswordRequirements } from "@/components/ui/PasswordRequirements";
import { ApiError, api } from "@/lib/api";
import { setToken } from "@/lib/auth-storage";
import { passwordPolicyError } from "@/lib/passwordPolicy";

type Errors = { current?: string; next?: string; confirm?: string; form?: string };

/**
 * Settings > Security "Change password" (POST /auth/password/change).
 *
 * Always the signed-in user's own password: nothing here names an
 * account. The backend is the authority for every rule — this form only
 * catches the obvious mistakes before a round trip. A successful change
 * signs every other session out, and the response carries a fresh token
 * so this browser stays signed in.
 */
export function ChangePasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<Errors>({});
  const [submitting, setSubmitting] = useState(false);
  const [succeeded, setSucceeded] = useState<null | { emailed: boolean }>(null);

  function validate(): Errors {
    const found: Errors = {};
    if (!current) found.current = "Enter your current password.";
    const policy = next ? passwordPolicyError(next) : "Enter a new password.";
    if (policy) found.next = policy;
    else if (next === current) found.next = "Choose a new password that is different from your current one.";
    if (!confirm) found.confirm = "Confirm your new password.";
    else if (confirm !== next) found.confirm = "The new passwords don't match.";
    return found;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSucceeded(null);
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setSubmitting(true);
    try {
      const response = await api.changePassword(current, next);
      setToken(response.access_token);
      setCurrent("");
      setNext("");
      setConfirm("");
      setSucceeded({ emailed: response.user.email_verified_at != null });
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      if (status === 400) {
        setErrors({ current: "Your current password is incorrect." });
      } else if (status === 422) {
        setErrors({ next: "This password doesn't meet the requirements below." });
      } else if (status === 429) {
        setErrors({ form: "Too many incorrect attempts. Please wait a few minutes and try again." });
      } else {
        setErrors({ form: "Something went wrong changing your password. Please try again." });
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Change password</CardTitle>
      </CardHeader>
      <CardContent className="pt-4">
        <form noValidate onSubmit={handleSubmit} className="flex max-w-md flex-col gap-4" aria-label="Change password">
          <PasswordField
            id="current-password"
            label="Current password"
            autoComplete="current-password"
            value={current}
            onChange={setCurrent}
            error={errors.current}
            disabled={submitting}
            required
          />
          <div className="flex flex-col gap-2">
            <PasswordField
              id="new-password"
              label="New password"
              autoComplete="new-password"
              value={next}
              onChange={setNext}
              error={errors.next}
              disabled={submitting}
              required
            />
            <PasswordRequirements password={next} />
          </div>
          <PasswordField
            id="confirm-new-password"
            label="Confirm new password"
            autoComplete="new-password"
            value={confirm}
            onChange={setConfirm}
            error={errors.confirm}
            disabled={submitting}
            required
          />

          {errors.form && (
            <p role="alert" className="text-sm text-danger">
              {errors.form}
            </p>
          )}
          {succeeded && (
            <p role="status" className="flex items-start gap-2 text-sm text-success">
              <CheckCircleIcon className="mt-0.5 h-4 w-4 shrink-0" />
              {succeeded.emailed
                ? "Your password has been changed. Other devices have been signed out, and a confirmation has been sent to your email address."
                : "Your password has been changed. Other devices have been signed out."}
            </p>
          )}

          <p className="text-xs text-muted">
            Changing your password signs you out on every other device. You stay signed in here.
          </p>
          <div>
            <Button type="submit" disabled={submitting} className="w-full sm:w-auto">
              {submitting ? "Changing password…" : "Change password"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
