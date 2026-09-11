"use client";

import { useId, useRef, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Field, Input, Select, Textarea } from "@/components/ui/Field";
import { AlertCircleIcon, MailIcon, SparklesIcon } from "@/components/ui/icons";
import { ApiError, api } from "@/lib/api";
import { STATUS_LABEL } from "@/lib/communications";
import type { Communication } from "@/types/communication";
import {
  DRAFT_KINDS,
  DRAFT_KIND_LABELS,
  REWRITE_INSTRUCTIONS,
  REWRITE_LABELS,
  TONES,
  type Draft,
  type DraftKind,
  type RewriteInstruction,
  type Tone,
} from "@/types/drafting";

/**
 * Compose, review and send a customer message (Sprint 039, Workstream C).
 *
 * **The human review step is this component.** GeoCore AI writes into the
 * same two fields a person would have typed into, and nothing leaves the
 * building until someone presses Send. There is no "draft and send"
 * shortcut, deliberately: the moment one exists, the review becomes
 * optional, and a model's guess about a date or a price is in a
 * customer's inbox.
 *
 * Three smaller decisions that follow from that:
 *
 *   * **Send is always enabled** (given a subject and a body), whether or
 *     not AI wrote the draft. Someone who wants to type their own message
 *     should not have to go near the AI.
 *   * **Drafting is hidden, not disabled, when no provider is
 *     configured.** A greyed-out button that always fails teaches nothing;
 *     the capabilities endpoint says whether drafting is real here.
 *   * **The draft says what it was grounded in**, so a reviewer can judge
 *     whether to trust it rather than guess what the model knew.
 */

/** A random key for one send attempt. `crypto.randomUUID` where the
 * browser has it (every target this app supports over HTTPS), with a
 * plain random fallback so a non-secure-context dev server still works. */
function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

interface Props {
  customerId: string;
  customerName?: string;
  /** Pre-selects the kind and links the resulting communication to the
   * record the user is looking at. */
  quoteId?: string;
  projectId?: string;
  defaultKind?: DraftKind;
  /** Whether GeoCore AI can draft in this deployment. */
  draftingAvailable: boolean;
  onSent?: (communication: Communication) => void;
  onClose?: () => void;
}

export function MessageComposer({
  customerId,
  customerName,
  quoteId,
  projectId,
  defaultKind = "general",
  draftingAvailable,
  onSent,
  onClose,
}: Props) {
  // One stable id prefix per rendered composer, so two composers on the
  // same page (a quote's and its customer's) never share a label target.
  const fieldId = useId();

  const [kind, setKind] = useState<DraftKind>(defaultKind);
  const [tone, setTone] = useState<Tone>("friendly");
  const [notes, setNotes] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [groundedIn, setGroundedIn] = useState<string[] | null>(null);

  const [drafting, setDrafting] = useState(false);
  const [rewriting, setRewriting] = useState<RewriteInstruction | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<Communication | null>(null);

  // Created on the first Send press and reused for every press after it,
  // so a double click resolves to the same communication rather than
  // sending two emails. Deliberately not generated during render: a
  // random value produced while rendering is impure (the repo's eslint
  // config rejects it, and React may render twice), and generating it in
  // the event handler is both legal and more accurate — the key belongs
  // to the send attempt, not to the panel being open.
  const idempotencyKeyRef = useRef<string | null>(null);

  const canSend = subject.trim().length > 0 && body.trim().length > 0;

  function describeError(err: unknown, fallback: string) {
    if (err instanceof ApiError && err.status === 503) {
      return "GeoCore AI isn't connected to this workspace, so it can't draft messages. You can still write and send one yourself.";
    }
    if (err instanceof ApiError && err.status === 422) {
      return "That customer has no email address on file. Add one on their record first.";
    }
    return err instanceof ApiError ? err.message : fallback;
  }

  function applyDraft(draft: Draft) {
    setSubject(draft.subject);
    setBody(draft.body);
    setGroundedIn(draft.grounded_in);
  }

  async function draft() {
    setDrafting(true);
    setError(null);
    try {
      applyDraft(
        await api.draftMessage({
          kind,
          customer_id: customerId,
          quote_id: quoteId,
          project_id: projectId,
          tone,
          notes: notes.trim() || undefined,
        })
      );
    } catch (err) {
      setError(describeError(err, "Couldn't draft that message."));
    } finally {
      setDrafting(false);
    }
  }

  async function rewrite(instruction: RewriteInstruction) {
    setRewriting(instruction);
    setError(null);
    try {
      applyDraft(await api.rewriteMessage(subject, body, instruction));
    } catch (err) {
      setError(describeError(err, "Couldn't rewrite that message."));
    } finally {
      setRewriting(null);
    }
  }

  async function send() {
    setSending(true);
    setError(null);
    try {
      idempotencyKeyRef.current ??= newIdempotencyKey();
      const communication = await api.sendCustomerMessage({
        customer_id: customerId,
        kind,
        subject,
        body,
        quote_id: quoteId,
        project_id: projectId,
        idempotency_key: idempotencyKeyRef.current,
      });
      // The communication row is authoritative about what happened —
      // never a cheerful "Sent!" regardless of outcome.
      setSent(communication);
      onSent?.(communication);
    } catch (err) {
      setError(describeError(err, "Couldn't send that message."));
    } finally {
      setSending(false);
    }
  }

  if (sent) {
    const delivered = sent.status === "sent" || sent.status === "delivered";
    return (
      <Card>
        <CardContent className="flex flex-col gap-3 py-5">
          <div className="flex items-center gap-2">
            <MailIcon className="h-4 w-4 text-muted" />
            <p className="text-sm font-medium text-foreground">
              {delivered
                ? `Sent to ${customerName ?? "your customer"}`
                : "Not sent"}
            </p>
            <Badge tone={delivered ? "info" : "danger"}>
              {STATUS_LABEL[sent.status]}
            </Badge>
          </div>
          <p className="text-sm text-muted">
            {delivered
              ? "Your mail provider accepted it. You'll see it confirmed as delivered in this customer's communication history once their mail server accepts it too."
              : sent.failure_detail ?? "The message could not be sent."}
          </p>
          {onClose && (
            <div>
              <Button variant="outline" size="sm" onClick={onClose}>
                Close
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 py-5">
        <div className="flex items-center gap-2">
          <MailIcon className="h-4 w-4 text-muted" />
          <h3 className="text-[13px] font-semibold uppercase tracking-wide text-muted">
            Message {customerName ?? "your customer"}
          </h3>
        </div>

        {error && (
          <p className="flex items-start gap-2 text-sm text-danger">
            <AlertCircleIcon className="mt-0.5 h-4 w-4 shrink-0" />
            {error}
          </p>
        )}

        {/* Stacks at 390px and becomes two columns from `sm` up. */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="What's this about" htmlFor={`${fieldId}-kind`}>
            <Select id={`${fieldId}-kind`} value={kind} onChange={(e) => setKind(e.target.value as DraftKind)}>
              {DRAFT_KINDS.map((option) => (
                <option key={option} value={option}>
                  {DRAFT_KIND_LABELS[option]}
                </option>
              ))}
            </Select>
          </Field>

          {draftingAvailable && (
            <Field label="Tone" htmlFor={`${fieldId}-tone`}>
              <Select id={`${fieldId}-tone`} value={tone} onChange={(e) => setTone(e.target.value as Tone)}>
                {TONES.map((option) => (
                  <option key={option} value={option}>
                    {option.charAt(0).toUpperCase() + option.slice(1)}
                  </option>
                ))}
              </Select>
            </Field>
          )}
        </div>

        {draftingAvailable && (
          <div className="flex flex-col gap-2 rounded-xl border border-border bg-surface-hover/40 p-3">
            <Field label="Anything GeoCore AI should mention? (optional)" htmlFor={`${fieldId}-notes`}>
              <Input
                id={`${fieldId}-notes`}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="e.g. the scaffolding goes up Monday"
                maxLength={500}
              />
            </Field>
            <div>
              <Button size="sm" onClick={draft} disabled={drafting}>
                <SparklesIcon className="h-3.5 w-3.5" />
                {drafting ? "Drafting…" : "Draft with GeoCore AI"}
              </Button>
            </div>
            <p className="text-xs text-muted">
              GeoCore AI writes a draft into the fields below. It never sends
              anything — you read it, change whatever you like, and send it
              yourself.
            </p>
          </div>
        )}

        <Field label="Subject" htmlFor={`${fieldId}-subject`}>
          <Input
            id={`${fieldId}-subject`}
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            maxLength={300}
            placeholder="What the email says it's about"
          />
        </Field>

        <Field label="Message" htmlFor={`${fieldId}-body`}>
          <Textarea
            id={`${fieldId}-body`}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={10}
            maxLength={8000}
            placeholder="Write your message, or let GeoCore AI draft one for you to edit."
          />
        </Field>

        {groundedIn && groundedIn.length > 0 && (
          <p className="text-xs text-muted">
            GeoCore AI was shown: {groundedIn.join(", ")}. Check anything it
            says about dates or money before you send.
          </p>
        )}

        {draftingAvailable && body.trim().length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted">Rewrite:</span>
            {REWRITE_INSTRUCTIONS.map((instruction) => (
              <Button
                key={instruction}
                size="sm"
                variant="outline"
                onClick={() => rewrite(instruction)}
                disabled={rewriting !== null}
              >
                {rewriting === instruction ? "…" : REWRITE_LABELS[instruction]}
              </Button>
            ))}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
          <Button onClick={send} disabled={!canSend || sending}>
            <MailIcon className="h-4 w-4" />
            {sending ? "Sending…" : "Send to customer"}
          </Button>
          {onClose && (
            <Button variant="ghost" onClick={onClose} disabled={sending}>
              Cancel
            </Button>
          )}
          {!canSend && (
            <span className="text-xs text-muted">
              Add a subject and a message to send.
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
