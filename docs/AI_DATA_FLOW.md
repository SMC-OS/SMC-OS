# AI Data Flow

The browser sends the user&rsquo;s question and recent conversation only to the
GeoCore API. Provider API keys stay in server configuration and are never
returned by an API route or embedded in browser code.

For conversational AI, GeoCore sends the configured OpenAI or Gemini provider:

- system instructions;
- the user&rsquo;s recent question/history (bounded to ten turns in the UI); and
- a tenant-scoped, bounded workspace summary: counts, quote/project/task
  statuses and titles.

The summary deliberately excludes customer emails, phone numbers, addresses,
document content, uploaded bytes, credentials, authentication tokens and
message bodies. Structured AI requests use the same provider adapters and
their feature-specific messages only. This is the Phase 2 minimisation
boundary; Phase 3 policy copy must describe the configured provider(s).
