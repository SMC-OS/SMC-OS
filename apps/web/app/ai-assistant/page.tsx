"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { ApiError, api } from "@/lib/api";

export default function AiAssistantPage() {
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<unknown>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setSubmitting(true);
    setError(null);
    setResponse(null);

    try {
      const result = await api.processPrompt(text);
      setResponse(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  const agent =
    response && typeof response === "object" && !Array.isArray(response) && "agent" in response
      ? String((response as Record<string, unknown>).agent)
      : null;

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          AI Assistant
        </h1>
        <p className="mt-1 text-sm text-muted">
          Talks to the existing <code className="text-xs">POST /process</code>{" "}
          endpoint (<code className="text-xs">BrainManager</code>). Today this
          is keyword-based routing to Sales and Search — a real LLM-based
          router lands in Sprint 008.
        </p>
      </div>

      <Card>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={3}
              placeholder="Try: “How much is Calacatta Gold quartz?” or “Show all available marble”"
              className="w-full resize-none rounded-lg border border-border bg-background p-3 text-sm text-foreground outline-none placeholder:text-muted focus:border-accent"
            />
            {error && (
              <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
                {error}
              </p>
            )}
            <Button type="submit" disabled={submitting} className="self-start">
              {submitting ? "Thinking…" : "Send"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {response !== null && (
        <Card className="mt-6">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Response</CardTitle>
            {agent && <Badge tone="info">Routed to: {agent}</Badge>}
          </CardHeader>
          <CardContent className="pt-4">
            <pre className="overflow-x-auto rounded-lg bg-background p-3 text-xs text-foreground">
              {JSON.stringify(response, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
