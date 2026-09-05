# Customer Portal — what exists, and what a marketplace would need

**Status:** Sprint 036, Workstream L. Documentation and boundary review.
**Scope:** this document records what the contractor ↔ customer surface is
today, what Sprint 036 changed underneath it, and what would genuinely be
required to go further. It deliberately proposes no new customer-facing
functionality, and nothing described under §4 is built or advertised
anywhere in the product.

---

## 1. What already exists (and works)

Discovery for Sprint 036 found that GeoCore already has a working
customer portal. It was not new work for this sprint, and it is worth
stating plainly because "customer portal foundation" reads like something
missing:

| Capability | Since | Where |
| --- | --- | --- |
| Tokenised, revocable, expiring portal link per customer | Sprint 013 (ADR-030) | `app/portal/`, `portal_links` |
| Customer views their own quotes | Sprint 013 | `GET /portal-links/token/{token}` |
| Customer downloads the quote/invoice PDF | Sprint 013 | `.../invoice/{quote_id}` |
| Customer sees documents staff uploaded | Sprint 016 (ADR-032) | `.../documents` |
| Two-way messaging, customer ↔ staff | Sprint 017 (ADR-033) | `.../messages` |
| Staff create, list and revoke links | Sprint 013/014 | Customer detail page |

The security model is a **capability token**, not an account: the link is
the credential, it is stored hashed, it is revocable, it expires, and it
is scoped to exactly one customer of exactly one tenant. There is no
customer login, no customer password and no customer user row — which is
why `messages.sender_user_id` is nullable and `sender_type` is the source
of truth for which side sent a message.

## 2. What Sprint 036 changed underneath it

Nothing about the portal's own routes changed. Three things it renders
did:

1. **A quote can now be a general construction quote.** The portal's PDF
   path shares `build_line_items()` with the staff path, and that function
   branches on each line's own `line_kind` — so a bathroom refit renders
   as "Strip out existing bathroom, 2.5 day @ £320.00" and a worktop
   still renders as "Worktop — Calacatta Oro (20mm), 1 x 2400mm x 600mm".
   No portal code needed to know.
2. **Documents are denominated in the issuing workspace's own currency**,
   captured on the quote at creation, so a customer's copy never
   re-denominates if the business later changes currency.
3. **A quote can be marked as sent.** GeoCore does not transmit it — the
   contractor sends the PDF or shares the portal link themselves — but
   the state now exists, which is what the unanswered-quote follow-up
   automation keys off.

## 3. What the architecture does not prevent

Recording this is the actual deliverable of Workstream L: nothing in the
current design blocks a richer customer-facing surface later.

- **Per-customer scoping is already the shape of the data.** Documents,
  messages and portal links are all customer-level rather than
  project-level (ADR-030's reasoning: one customer's list serves all
  their concurrent jobs). A portal that shows project progress needs
  `projects` filtered by `customer_id`, which `crud.list_projects_by_customer`
  already does for the staff-side customer context page.
- **Dated work is already aggregated.** `app/calendar/` builds one
  tenant-scoped feed of project dates, site visits, task due dates and
  quote expiries. A customer-facing "when are you coming" view is that
  same aggregation filtered to one customer, not a new subsystem.
- **Approval is already a first-class server-side transition.**
  `quote_service.approve()` is idempotent-adjacent (it refuses anything
  not in draft/sent) and logs an ActivityEvent. A customer approving from
  the portal would call the same service through a token-scoped route —
  it does not need a parallel approval path.
- **The token model extends without redesign.** A portal token today
  grants read plus message-write for one customer. Granting quote
  approval means adding one route with the same token resolution, not a
  new authentication system.

## 4. What is NOT built, and what each would actually require

None of this exists. None of it is referenced anywhere in the product UI.
It is listed so that a future sprint starts from a real assessment rather
than an optimistic one.

| Wanted | What it actually needs |
| --- | --- |
| Customer approves a quote from the portal | A token-scoped `POST .../quotes/{id}/approve`; an audit trail that records *the customer* approved (today `approved_by_user_id` is a staff user FK and is NOT NULL-able only by convention); and a decision about whether a link-holder approving a £48,000 job is sufficient authorisation, which is a commercial question, not a technical one. |
| Project progress for the customer | A view of `Project.status` that is meaningful to a homeowner. The current pipeline is `enquiry → quoted → booked → templated → fabricated → installed → complete` — stone fabrication stages that mean nothing on a roofing job (see §10 of the Sprint 036 doc; renaming it is deferred, deliberately). A customer-facing progress view should not ship on top of a vocabulary the product is about to change. |
| Appointments the customer can see or request | Reading is straightforward (appointments are project-scoped, projects are customer-scoped). *Requesting* introduces a write from an unauthenticated party against a staff calendar — which needs rate limiting, a proposal/confirmation state, and abuse handling that the token model alone does not provide. |
| Photos and documents the customer uploads | `app/documents/` currently accepts uploads only from authenticated staff. Accepting them through a capability token means an unauthenticated upload path: content-type sniffing beyond the extension allowlist, per-token quotas, and a storage backend that is not a local volume (ADR-032's accepted limitation — the current `UPLOAD_DIR` does not survive a redeploy to a different host and does not scale past one instance). |
| Customer accounts, one customer across several contractors | This is the marketplace question, and it is a different product. It requires a customer identity that is not owned by a tenant, which inverts the tenancy model every query in this codebase is built on (ADR-029). It is not an extension of the portal; it is a second application sharing a database. |

## 5. The rule that stays

**Nothing unimplemented is advertised.** The product does not show a
customer-portal feature it cannot perform, does not offer a disabled
"customer approval" control, and does not tell a contractor their
customer can do something they cannot. That rule is why this document
exists as documentation rather than as a half-built feature flag.
