"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { SparklesIcon } from "@/components/ui/icons";
import { api } from "@/lib/api";
import type { AICapabilities } from "@/types/ai";

/**
 * The GeoCore AI entry point on the dashboard (Sprint 036, Workstream H).
 *
 * Deliberately does NOT generate an insight here. Producing a paragraph
 * of "AI analysis" on page load would cost a model call on every dashboard
 * view, and — more importantly — would produce something that looks
 * authoritative whether or not there is anything to say. This offers the
 * questions instead, and the answer comes from a real conversation the
 * person chose to start.
 *
 * The copy adapts to what is genuinely configured: with no AI provider
 * connected, it says so and points at the catalogue assistant rather than
 * advertising analysis the deployment cannot perform.
 */
const PROMPTS = [
  "What needs my attention today?",
  "Which quotes haven't been answered?",
  "What's starting this week?",
];

export function AIInsightCard() {
  const [capabilities, setCapabilities] = useState<AICapabilities | null>(null);

  useEffect(() => {
    api
      .getAICapabilities()
      .then(setCapabilities)
      .catch(() => setCapabilities(null));
  }, []);

  const configured = capabilities?.llm_configured ?? false;

  return (
    <Card className="border-accent/25 bg-accent-subtle">
      <CardContent>
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
            <SparklesIcon className="h-[18px] w-[18px]" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-foreground">GeoCore AI</p>
            <p className="mt-0.5 text-sm text-muted">
              {configured
                ? "Ask about your quotes, projects and what needs doing."
                : "Ask about materials and prices from your catalogue. Connect an AI provider for full answers about your quotes and projects."}
            </p>

            <div className="mt-3 flex flex-wrap gap-2">
              {(configured ? PROMPTS : ["What does 20mm quartz cost?"]).map((prompt) => (
                <Link
                  key={prompt}
                  href={`/ai?q=${encodeURIComponent(prompt)}`}
                  className="inline-flex min-h-10 items-center rounded-full border border-accent/30 bg-surface px-3.5 py-2 text-xs font-medium text-accent transition-colors hover:bg-accent hover:text-accent-foreground"
                >
                  {prompt}
                </Link>
              ))}
            </div>

            <Link href="/ai" className="mt-3 inline-block">
              <Button size="sm" variant="outline">
                Open GeoCore AI
              </Button>
            </Link>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
