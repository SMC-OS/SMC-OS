import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "outline" | "danger";
type Size = "sm" | "md" | "lg" | "icon";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const variantClasses: Record<Variant, string> = {
  // Sprint 036: a real hover colour rather than opacity. Fading the
  // primary against a warm ground desaturates it into mud; moving to a
  // deliberately-chosen darker forest keeps it looking intentional.
  primary: "bg-accent text-accent-foreground hover:bg-accent-hover shadow-[var(--shadow-sm)]",
  secondary: "bg-surface-hover text-foreground hover:bg-border",
  ghost: "text-foreground hover:bg-surface-hover",
  outline: "border border-border text-foreground hover:border-border-strong hover:bg-surface-hover",
  danger: "bg-danger text-white hover:opacity-90",
};

const sizeClasses: Record<Size, string> = {
  // Every size is at least 36px tall, and `lg` exists specifically for
  // the primary action on a phone, where 44px is the accepted minimum
  // comfortable touch target.
  sm: "h-9 px-3 text-sm",
  md: "h-10 px-4 text-sm",
  lg: "h-11 px-5 text-sm",
  icon: "h-10 w-10",
};

export function Button({
  className,
  variant = "primary",
  size = "md",
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      // Defaulting to type="button" rather than the HTML default of
      // "submit": a button inside a form that was only meant to toggle a
      // panel should never submit it. Every real submit button in this
      // app passes type="submit" explicitly.
      type={type}
      className={cn(
        "inline-flex shrink-0 items-center justify-center gap-2 rounded-lg font-medium transition-colors duration-150",
        "disabled:cursor-not-allowed disabled:opacity-50",
        variantClasses[variant],
        sizeClasses[size],
        className
      )}
      {...props}
    />
  );
}
