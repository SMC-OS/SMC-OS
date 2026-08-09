import { ModuleIndexPage } from "@/components/shell/ModuleIndexPage";

export default function ProjectsPage() {
  return (
    <ModuleIndexPage
      title="Projects"
      description="The full job pipeline — enquiry through installation — ships alongside CRM in Sprint 004/006."
      sprint="Sprint 006"
      activityType="project_created"
      emptyLabel="No projects logged yet — add one to see it here."
      ctaLabel="New Project"
      ctaHref="/projects/new"
    />
  );
}
