"use client";

import { EXTRA_LABELS, EXTRA_OPTIONS, type ExtraOption } from "@/types/quote";
import { cn } from "@/lib/utils";

interface ExtrasPickerProps {
  value: ExtraOption[];
  onChange: (value: ExtraOption[]) => void;
  idPrefix: string;
}

/** Post-release remediation (§4) — common worktop add-ons, recorded on
 * the item's notes for a transparent itemised quote. Not priced
 * separately (see types/quote.ts's EXTRA_OPTIONS comment). */
export function ExtrasPicker({ value, onChange, idPrefix }: ExtrasPickerProps) {
  function toggle(option: ExtraOption) {
    onChange(value.includes(option) ? value.filter((v) => v !== option) : [...value, option]);
  }

  return (
    <div className="flex flex-wrap gap-2">
      {EXTRA_OPTIONS.map((option) => {
        const checked = value.includes(option);
        const inputId = `${idPrefix}-extra-${option}`;
        return (
          <label
            key={option}
            htmlFor={inputId}
            className={cn(
              "flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors",
              checked
                ? "border-accent bg-accent/10 text-accent"
                : "border-border bg-background text-muted hover:bg-surface-hover"
            )}
          >
            <input
              id={inputId}
              type="checkbox"
              className="sr-only"
              checked={checked}
              onChange={() => toggle(option)}
            />
            {EXTRA_LABELS[option]}
          </label>
        );
      })}
    </div>
  );
}
