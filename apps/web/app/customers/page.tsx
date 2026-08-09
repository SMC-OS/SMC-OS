import { ModuleIndexPage } from "@/components/shell/ModuleIndexPage";

export default function CustomersPage() {
  return (
    <ModuleIndexPage
      title="Customers"
      description="The full CRM — customer profiles, quote history, and project links — ships in Sprint 004."
      sprint="Sprint 004"
      activityType="customer_added"
      emptyLabel="No customers logged yet — add one to see it here."
      ctaLabel="New Customer"
      ctaHref="/customers/new"
    />
  );
}
