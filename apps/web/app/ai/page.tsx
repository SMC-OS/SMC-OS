"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { SendIcon, SparklesIcon } from "@/components/ui/icons";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { AICapabilities, ChatMessage } from "@/types/ai";

interface DisplayMessage extends ChatMessage {
  id: string;
  engine?: "llm" | "builtin";
}

const SUGGESTIONS_WITH_LLM = [
  "What needs my attention today?",
  "Which quotes haven't been answered?",
  "What's starting this week?",
  "Summarise how the business is doing",
];

const SUGGESTIONS_BUILTIN = [
  "What does 20mm quartz cost?",
  "Show me marble",
  "Do we have Calacatta Gold?",
];

let messageId = 0;
function nextId() {
  messageId += 1;
  return `m-${messageId}`;
}

/**
 * GeoCore AI — Sprint 036, Workstream H.
 *
 * Replaces the old "AI Assistant" page, which rendered raw
 * JSON.stringify output in a <pre> and whose own body copy named
 * `POST /process`, `BrainManager` and a sprint number. Developer
 * internals are not product copy, and none of them appear anywhere here.
 *
 * The honesty mechanism is `engine`. Every reply says whether a real
 * model answered ("llm") or the deterministic catalogue assistant did
 * ("builtin"), and the empty state adapts to what is actually configured
 * in this deployment — a workspace with no AI provider connected is told
 * so plainly and offered the questions the built-in assistant can
 * genuinely answer, rather than being invited to ask things that will
 * disappoint it.
 *
 * Conversation state lives in this component. That is a stated v1
 * boundary, not an oversight: there is no conversations table yet, so a
 * conversation lasts as long as the tab. See sprint-036.md §10.
 */
function GeoCoreAIContent() {
  const router = useRouter();
  const params = useSearchParams();
  const { isAuthenticated, isReady } = useAuth();

  const [capabilities, setCapabilities] = useState<AICapabilities | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const askedFromUrl = useRef(false);

  useEffect(() => {
    if (!isReady) return;
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }
    api.getAICapabilities().then(setCapabilities).catch(() => {});
  }, [isReady, isAuthenticated, router]);

  // A prompt can arrive as ?q= from the dashboard cards. Sent once —
  // the ref guard stops a re-render (or React's development double-mount)
  // from asking the same question twice.
  useEffect(() => {
    const question = params.get("q");
    if (!question || askedFromUrl.current || !isAuthenticated) return;
    askedFromUrl.current = true;
    void send(question);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params, isAuthenticated]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, thinking]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || thinking) return;

    const outgoing: DisplayMessage = { id: nextId(), role: "user", content: trimmed };
    const history = [...messages, outgoing];

    setMessages(history);
    setInput("");
    setThinking(true);
    setError(null);

    try {
      const response = await api.chatWithAI(
        // Only the last few turns are sent: the request is bounded
        // server-side at 20 messages, and a long tail of history crowds
        // out the workspace context that makes the answer useful.
        history.slice(-10).map(({ role, content }) => ({ role, content }))
      );
      setMessages((current) => [
        ...current,
        {
          id: nextId(),
          role: "assistant",
          content: response.reply,
          engine: response.engine,
        },
      ]);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? "GeoCore AI couldn't answer just then. Try again in a moment."
          : "Something went wrong."
      );
    } finally {
      setThinking(false);
    }
  }

  if (!isReady || !isAuthenticated) return null;

  const suggestions = capabilities?.llm_configured
    ? SUGGESTIONS_WITH_LLM
    : SUGGESTIONS_BUILTIN;

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col">
      <div className="mb-4 flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent text-accent-foreground">
          <SparklesIcon className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight text-foreground sm:text-2xl">
            GeoCore AI
          </h1>
          <p className="truncate text-sm text-muted">
            {capabilities?.llm_configured
              ? "Ask about your quotes, projects and what needs doing."
              : "Ask about materials and prices from your catalogue."}
          </p>
        </div>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto pb-4">
        {messages.length === 0 && (
          <Card>
            <CardContent className="py-8 text-center">
              <p className="text-sm font-medium text-foreground">
                What would you like to know?
              </p>
              {capabilities && !capabilities.llm_configured && (
                <p className="mx-auto mt-2 max-w-md text-sm text-muted">
                  No AI provider is connected to this workspace yet, so GeoCore AI is
                  answering with its built-in catalogue assistant. It can look up
                  materials and prices; connecting a provider unlocks answers about
                  your quotes, projects and schedule.
                </p>
              )}

              <div className="mt-5 flex flex-wrap justify-center gap-2">
                {suggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => send(suggestion)}
                    className="rounded-full border border-border px-3.5 py-1.5 text-sm text-foreground transition-colors hover:border-accent hover:bg-accent-subtle hover:text-accent"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {messages.map((message) => (
          <div
            key={message.id}
            className={cn(
              "flex",
              message.role === "user" ? "justify-end" : "justify-start"
            )}
          >
            <div
              className={cn(
                "max-w-[85%] rounded-2xl px-4 py-3 text-sm sm:max-w-[75%]",
                message.role === "user"
                  ? "bg-accent text-accent-foreground"
                  : "border border-border bg-surface text-foreground"
              )}
            >
              <p className="whitespace-pre-wrap">{message.content}</p>
              {message.role === "assistant" && message.engine === "builtin" && (
                <Badge tone="neutral" className="mt-2">
                  Built-in assistant
                </Badge>
              )}
            </div>
          </div>
        ))}

        {thinking && (
          <div className="flex justify-start">
            <div
              className="rounded-2xl border border-border bg-surface px-4 py-3"
              role="status"
              aria-live="polite"
            >
              <span className="sr-only">GeoCore AI is thinking</span>
              <span className="flex gap-1" aria-hidden="true">
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    className="h-2 w-2 animate-pulse rounded-full bg-muted"
                    style={{ animationDelay: `${i * 150}ms` }}
                  />
                ))}
              </span>
            </div>
          </div>
        )}

        {error && (
          <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">
            {error}
          </p>
        )}

        <div ref={endRef} />
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void send(input);
        }}
        className="sticky bottom-0 flex items-end gap-2 border-t border-border bg-background pt-3"
      >
        <label htmlFor="ai-input" className="sr-only">
          Ask GeoCore AI
        </label>
        <textarea
          id="ai-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(event) => {
            // Enter sends, Shift+Enter makes a new line — the convention
            // in every chat interface, and the one people will try first.
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send(input);
            }
          }}
          rows={1}
          placeholder="Ask about your business…"
          className="max-h-32 min-h-[44px] flex-1 resize-none rounded-xl border border-border bg-surface px-3.5 py-3 text-sm text-foreground outline-none placeholder:text-muted focus:border-accent"
        />
        <Button type="submit" size="icon" disabled={thinking || !input.trim()} aria-label="Send">
          <SendIcon className="h-[18px] w-[18px]" />
        </Button>
      </form>

      <p className="pb-1 pt-2 text-center text-xs text-muted">
        GeoCore AI answers questions. It can&rsquo;t create, edit or send anything for you.
      </p>
    </div>
  );
}

export default function GeoCoreAIPage() {
  return (
    <Suspense fallback={null}>
      <GeoCoreAIContent />
    </Suspense>
  );
}
