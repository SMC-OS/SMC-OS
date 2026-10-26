import { formatCurrency, formatMoney } from "@/lib/utils";

export function CurrencyTotals({ amounts, value, currency = "GBP" }: {
  amounts?: Record<string, number>; value: number; currency?: string;
}) {
  const entries = amounts && Object.keys(amounts).length ? Object.entries(amounts) : [[currency, value] as const];
  return <span className="flex flex-col gap-1">
    {entries.map(([code, amount]) => <span key={code} className="block">
      <span>{Number.isInteger(amount) ? formatCurrency(amount, code) : formatMoney(amount, code)}</span>
      {entries.length > 1 && <span className="ml-1 text-xs font-normal text-muted">{code}</span>}
    </span>)}
  </span>;
}
