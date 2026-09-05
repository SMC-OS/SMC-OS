"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { ProjectForm } from "@/components/projects/ProjectForm";
import { api } from "@/lib/api";
import type { ProjectCreate } from "@/types/project";

function NewProjectContent() {
  const router = useRouter();
  const params = useSearchParams();
  const { isAuthenticated, isReady } = useAuth();

  useEffect(() => {
    if (isReady && !isAuthenticated) router.replace("/login");
  }, [isReady, isAuthenticated, router]);

  if (!isReady || !isAuthenticated) return null;

  async function handleSubmit(values: ProjectCreate) {
    const project = await api.createProject(values);
    router.push(`/projects/${project.id}`);
  }

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-6">
        <Link href="/projects" className="tap-link text-sm text-muted hover:text-foreground">
          &larr; Projects
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          New project
        </h1>
        <p className="mt-1 text-sm text-muted">
          Approving a quote creates a project automatically — use this for work that
          didn&rsquo;t start as a quote.
        </p>
      </div>

      <ProjectForm
        submitLabel="Save project"
        initialCustomerId={params.get("customer") ?? undefined}
        onSubmit={handleSubmit}
      />
    </div>
  );
}

export default function NewProjectPage() {
  return (
    <Suspense fallback={null}>
      <NewProjectContent />
    </Suspense>
  );
}
