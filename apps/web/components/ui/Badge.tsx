import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "accent" | "champagne";

const toneClasses: Record<Tone, string> = {
  neutral: "bg-surface-hover text-muted",
  success: "bg-success/12 text-success",
  warning: "bg-warning/12 text-warning",
  danger: "bg-danger/12 text-danger",
  info: "bg-info/12 text-info",
  accent: "bg-accent-subtle text-accent",
  // Sprint 036: the champagne tone exists for emphasis a colour-coded
  // status badge shouldn't claim — "Approved" is success, "Premium" is
  // champagne. Used sparingly on purpose.
  champagne: "bg-champagne-subtle text-champagne",
};

export function Badge({
  className,
  tone = "neutral",
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium",
        toneClasses[tone],
        className
      )}
      {...props}
    />
  );
}
