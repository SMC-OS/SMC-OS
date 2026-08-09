import type { ComponentType, SVGProps } from "react";

import { Card } from "@/components/ui/Card";
import { useCountUp } from "@/hooks/useCountUp";
import { cn, formatCurrencyGBP } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: number;
  format?: "number" | "currency";
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  loading?: boolean;
}

export function StatCard({
  label,
  value,
  format = "number",
  icon: StatIcon,
  loading = false,
}: StatCardProps) {
  const animated = useCountUp(value);

  const display =
    format === "currency"
      ? formatCurrencyGBP(animated)
      : animated.toLocaleString("en-GB");

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between">
        <p className="text-sm font-medium text-muted">{label}</p>
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/10 text-accent">
          <StatIcon className="h-[18px] w-[18px]" />
        </div>
      </div>

      <p
        className={cn(
          "mt-3 text-3xl font-semibold tracking-tight text-foreground transition-opacity",
          loading && "opacity-40"
        )}
      >
        {display}
      </p>
    </Card>
  );
}

export function StatCardSkeleton() {
  return (
    <Card className="p-5">
      <div className="h-4 w-24 animate-pulse rounded bg-surface-hover" />
      <div className="mt-4 h-8 w-20 animate-pulse rounded bg-surface-hover" />
    </Card>
  );
}
