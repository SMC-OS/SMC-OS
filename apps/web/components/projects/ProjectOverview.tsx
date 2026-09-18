import Link from "next/link";

import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Field";
import { formatDate, formatMoney } from "@/lib/utils";
import type { Customer } from "@/types/customer";
import type { Project } from "@/types/project";

/**
 * GeoCore Premium OS Plan 01 (Sprint 040, Task 8) — the Overview tab:
 * the job's own details (Sprint 036, Workstream F) plus enquiry-to-
 * customer conversion (Sprint 021), extracted from the old flat project
 * page unchanged in behaviour. Every field renders an em dash when
 * absent rather than being hidden — a start date you have not set is
 * information worth seeing on a project page.
 */
export function ProjectOverview({
  project,
  customer,
  currency,
  showConvertAction,
  showConvertForm,
  convertName,
  convertEmail,
  convertPhone,
  converting,
  onConvertNameChange,
  onConvertEmailChange,
  onConvertPhoneChange,
  onShowConvertForm,
  onConvertSubmit,
}: {
  project: Project;
  customer: Customer | null;
  currency: string;
  showConvertAction: boolean;
  showConvertForm: boolean;
  convertName: string;
  convertEmail: string;
  convertPhone: string;
  converting: boolean;
  onConvertNameChange: (value: string) => void;
  onConvertEmailChange: (value: string) => void;
  onConvertPhoneChange: (value: string) => void;
  onShowConvertForm: () => void;
  onConvertSubmit: (event: React.FormEvent) => void;
}) {
  return (
    <div>
      <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="min-w-0">
          <dt className="text-xs font-medium text-muted">Customer</dt>
          <dd className="truncate text-sm text-foreground">
            {customer ? (
              <Link href={`/customers/${customer.id}`} className="text-accent hover:underline">
                {customer.company_name || customer.name}
              </Link>
            ) : (
              "—"
            )}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-xs font-medium text-muted">Value</dt>
          <dd className="text-sm text-foreground">
            {project.estimated_value != null
              ? formatMoney(project.estimated_value, currency)
              : "—"}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-xs font-medium text-muted">Starts</dt>
          <dd className="text-sm text-foreground">{formatDate(project.start_date)}</dd>
        </div>
        <div className="min-w-0">
          <dt className="text-xs font-medium text-muted">Target completion</dt>
          <dd className="text-sm text-foreground">
            {formatDate(project.target_completion_date)}
          </dd>
        </div>
        <div className="min-w-0 sm:col-span-2">
          <dt className="text-xs font-medium text-muted">Site</dt>
          <dd className="text-sm text-foreground">
            {[
              project.site_address_line1,
              project.site_address_line2,
              project.site_city,
              project.site_postcode,
            ]
              .filter(Boolean)
              .join(", ") || "—"}
          </dd>
        </div>
        {project.description && (
          <div className="min-w-0 sm:col-span-2">
            <dt className="text-xs font-medium text-muted">Description</dt>
            <dd className="whitespace-pre-wrap text-sm text-foreground">
              {project.description}
            </dd>
          </div>
        )}
        <div className="min-w-0 sm:col-span-2">
          <dt className="text-xs font-medium text-muted">Notes</dt>
          <dd className="whitespace-pre-wrap text-sm text-foreground">{project.notes ?? "—"}</dd>
        </div>
      </dl>

      {showConvertAction && (
        <div className="mt-6 border-t border-border pt-4">
          {showConvertForm ? (
            <form onSubmit={onConvertSubmit} className="flex flex-col gap-4">
              <Field label="Full name" htmlFor="convert-name">
                <Input
                  id="convert-name"
                  required
                  value={convertName}
                  onChange={(e) => onConvertNameChange(e.target.value)}
                  placeholder="e.g. James Okafor"
                />
              </Field>
              <Field label="Email" htmlFor="convert-email">
                <Input
                  id="convert-email"
                  type="email"
                  value={convertEmail}
                  onChange={(e) => onConvertEmailChange(e.target.value)}
                  placeholder="james@example.com"
                />
              </Field>
              <Field label="Phone" htmlFor="convert-phone">
                <Input
                  id="convert-phone"
                  value={convertPhone}
                  onChange={(e) => onConvertPhoneChange(e.target.value)}
                  placeholder="07123 456789"
                />
              </Field>
              <Button type="submit" disabled={converting}>
                {converting ? "Saving…" : "Save customer"}
              </Button>
            </form>
          ) : (
            <Button onClick={onShowConvertForm} variant="outline">
              Convert to Customer
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
