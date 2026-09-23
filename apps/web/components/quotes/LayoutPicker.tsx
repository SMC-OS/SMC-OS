"use client";

import { LAYOUT_LABELS, LAYOUT_OPTIONS, type LayoutOption } from "@/types/quote";
import { cn } from "@/lib/utils";

interface LayoutPickerProps {
  value: LayoutOption | "";
  onChange: (value: LayoutOption | "") => void;
  idPrefix: string;
}

/** Post-release remediation (§4) — a small, icon-backed visual picker
 * for the worktop run's shape. Deliberately simple line-drawing icons,
 * not a scaled diagram editor: selecting a shape only labels the item
 * for the quote's notes (see page.tsx), it never changes pricing. */
function ShapeIcon({ shape }: { shape: LayoutOption }) {
  const stroke = "currentColor";
  switch (shape) {
    case "straight":
      return (
        <svg viewBox="0 0 32 20" width="32" height="20" aria-hidden="true">
          <rect x="2" y="8" width="28" height="6" rx="1" fill="none" stroke={stroke} strokeWidth="2" />
        </svg>
      );
    case "l_shape":
      return (
        <svg viewBox="0 0 32 32" width="32" height="20" aria-hidden="true">
          <path
            d="M4 4 H14 V14 H28 V28 H4 Z"
            fill="none"
            stroke={stroke}
            strokeWidth="2"
            strokeLinejoin="round"
          />
        </svg>
      );
    case "u_shape":
      return (
        <svg viewBox="0 0 32 32" width="32" height="20" aria-hidden="true">
          <path
            d="M4 4 H12 V20 H20 V4 H28 V28 H4 Z"
            fill="none"
            stroke={stroke}
            strokeWidth="2"
            strokeLinejoin="round"
          />
        </svg>
      );
    case "island":
      return (
        <svg viewBox="0 0 32 32" width="32" height="20" aria-hidden="true">
          <rect x="3" y="4" width="26" height="6" rx="1" fill="none" stroke={stroke} strokeWidth="2" />
          <rect x="8" y="18" width="16" height="8" rx="1" fill="none" stroke={stroke} strokeWidth="2" />
        </svg>
      );
    case "peninsula":
      return (
        <svg viewBox="0 0 32 32" width="32" height="20" aria-hidden="true">
          <path
            d="M4 4 H28 V14 H16 V28 H10 V14 H4 Z"
            fill="none"
            stroke={stroke}
            strokeWidth="2"
            strokeLinejoin="round"
          />
        </svg>
      );
    default:
      return null;
  }
}

export function LayoutPicker({ value, onChange, idPrefix }: LayoutPickerProps) {
  return (
    <div role="radiogroup" aria-label="Layout" className="flex flex-wrap gap-2">
      {LAYOUT_OPTIONS.map((option) => {
        const selected = value === option;
        return (
          <button
            key={option}
            type="button"
            id={`${idPrefix}-layout-${option}`}
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(selected ? "" : option)}
            className={cn(
              "flex flex-col items-center gap-1 rounded-lg border px-2 py-1.5 text-[11px] leading-tight text-muted transition-colors",
              selected
                ? "border-accent bg-accent/10 text-accent"
                : "border-border bg-background hover:bg-surface-hover"
            )}
          >
            <ShapeIcon shape={option} />
            {LAYOUT_LABELS[option]}
          </button>
        );
      })}
    </div>
  );
}
