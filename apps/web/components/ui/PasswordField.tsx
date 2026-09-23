"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Field";

/**
 * Sprint 039 V1 auth UX. Every password control in the product renders
 * through this component so show/hide state, autocomplete semantics and
 * accessible labelling stay consistent — and so that a signup form with
 * a password *and* a confirmation can toggle each field independently
 * without one control's state leaking into the other.
 */
export function PasswordField({
  id,
  label,
  value,
  onChange,
  autoComplete,
  required,
  autoFocus,
  error,
  disabled,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: "current-password" | "new-password";
  required?: boolean;
  autoFocus?: boolean;
  error?: string;
  disabled?: boolean;
}) {
  const [visible, setVisible] = useState(false);

  return (
    <Field label={label} htmlFor={id} error={error}>
      <div className="relative">
        <Input
          id={id}
          type={visible ? "text" : "password"}
          required={required}
          autoFocus={autoFocus}
          autoComplete={autoComplete}
          disabled={disabled}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="pr-24"
        />
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setVisible((v) => !v)}
          aria-controls={id}
          className="absolute inset-y-0 right-1 h-8 self-center px-2 text-xs"
        >
          {visible ? "Hide password" : "Show password"}
        </Button>
      </div>
    </Field>
  );
}
