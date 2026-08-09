import { ModuleIndexPage } from "@/components/shell/ModuleIndexPage";

export default function QuotesPage() {
  return (
    <ModuleIndexPage
      title="Quotes"
      description="Searchable quote history, status tracking, and PDF exports land with the database in Sprint 002."
      sprint="Sprint 002"
      activityType="quote_created"
      emptyLabel="No quotes logged yet — create one to see it here."
      ctaLabel="New Quote"
      ctaHref="/quotes/new"
    />
  );
}
