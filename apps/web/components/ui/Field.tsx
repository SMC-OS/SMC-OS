import type {
  InputHTMLAttributes,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

import { cn } from "@/lib/utils";

/**
 * Sprint 036 (Workstream B/M). Every control here shares one focus
 * treatment, one height and one radius, and every one is labelled.
 *
 * The accessibility rules this component enforces rather than leaves to
 * each call site:
 *   - the label's htmlFor always matches the control's id (the props make
 *     it awkward to do otherwise);
 *   - a hint or an error is wired to the control through aria-describedby
 *     rather than merely rendered near it;
 *   - an error sets aria-invalid, so a screen reader announces the state
 *     and not just the colour.
 */
export function Field({
  label,
  htmlFor,
  hint,
  error,
  required,
  className,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  error?: string;
  required?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <label htmlFor={htmlFor} className="text-sm font-medium text-foreground">
        {label}
        {required && (
          <span className="ml-1 text-danger" aria-hidden="true">
            *
          </span>
        )}
      </label>
      {children}
      {hint && !error && (
        <p id={`${htmlFor}-hint`} className="text-xs text-muted">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${htmlFor}-error`} className="text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

const controlClasses =
  "w-full min-w-0 rounded-lg border border-border bg-surface px-3 text-sm text-foreground outline-none " +
  "placeholder:text-muted transition-colors hover:border-border-strong " +
  "focus:border-accent disabled:cursor-not-allowed disabled:opacity-60";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(controlClasses, "h-10", className)} {...props} />;
}

export function Textarea({
  className,
  rows = 4,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea rows={rows} className={cn(controlClasses, "resize-y py-2.5", className)} {...props} />
  );
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        controlClasses,
        "h-10 appearance-none bg-[length:16px] bg-[right_0.75rem_center] bg-no-repeat pr-9",
        className
      )}
      // The chevron is an inline data URI rather than an icon component
      // so it can be a real CSS background on a native <select> — a
      // custom dropdown would lose the platform picker, which on a phone
      // is significantly better than anything we would build.
      style={{
        backgroundImage:
          "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%235c6b63' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E\")",
        ...props.style,
      }}
      {...props}
    />
  );
}

export function Checkbox({
  label,
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-center gap-2.5 text-sm text-foreground",
        className
      )}
    >
      <input
        type="checkbox"
        className="h-4 w-4 shrink-0 rounded border-border accent-[var(--accent)]"
        {...props}
      />
      {label}
    </label>
  );
}

/**
 * A labelled group of mutually-exclusive choices rendered as buttons —
 * used for the quote-kind picker and the onboarding trade selection.
 * Built on real radio inputs rather than divs with click handlers, so
 * arrow-key navigation, form participation and screen-reader semantics
 * all work without reimplementing them.
 */
export function ChoiceChip({
  name,
  value,
  checked,
  onChange,
  children,
  className,
}: {
  name: string;
  value: string;
  checked: boolean;
  onChange: (value: string) => void;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-sm font-medium transition-colors",
        checked
          ? "border-accent bg-accent-subtle text-accent"
          : "border-border text-foreground hover:border-border-strong hover:bg-surface-hover",
        className
      )}
    >
      <input
        type="radio"
        name={name}
        value={value}
        checked={checked}
        onChange={() => onChange(value)}
        className="sr-only"
      />
      {children}
    </label>
  );
}

/** The multi-select counterpart of ChoiceChip (onboarding trades). */
export function ToggleChip({
  checked,
  onChange,
  children,
  className,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-sm font-medium transition-colors",
        checked
          ? "border-accent bg-accent-subtle text-accent"
          : "border-border text-foreground hover:border-border-strong hover:bg-surface-hover",
        className
      )}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="sr-only"
      />
      {children}
    </label>
  );
}
