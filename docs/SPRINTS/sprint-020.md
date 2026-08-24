# Sprint 020 — End-to-End Quote Approval & Project Handoff

## Objective

A permitted tenant staff user can create a quote for an existing customer, approve it through a deliberate backend-enforced lifecycle, and hand it off to the existing Project pipeline through the real UI and API. The resulting project remains tenant-scoped, traceable to its quote and customer, and usable after a refetch.

## Implemented contract

This document is the Sprint 020 delivery contract. It describes the intended implementation until the verification sections are populated with fresh evidence.

### Existing foundations reused

- `Customer`, `Quote`, and `Project` remain the existing tenant-owned records.
- Quotes continue to be created by `POST /api/v1/quote`; an authenticated caller's tenant is attached by the established optional-auth behaviour.
- Projects retain the existing pipeline and its `booked` operational state.
- `get_current_user` / `require_role` remain the sole authorization framework. Both existing operational roles (`Owner`, `Staff`) may manage approval and handoff; portal routes have no staff JWT and cannot use either operation.
- Existing tenant-filtered CRUD lookups, ActivityLog, API client, and quote/project detail pages are extended rather than replaced.

### Quote lifecycle

New persisted quotes start as `draft`, the single editable/pre-approval state presently supported by the existing create-only quote surface. `approved` is the terminal approval state for this sprint. Approval is a command operation, not a generic status patch. It records `approved_at` and the approving staff user where the schema supports it.

An anonymous or unlinked quote may remain a historical calculated quote, but cannot enter the customer-to-project handoff: approval and handoff require a quote linked to an accessible tenant customer.

### Approval operation

`POST /api/v1/quotes/{quote_id}/approve`:

- is staff-authenticated and tenant-scoped;
- accepts only a linked `draft` quote;
- persists approval state and audit attribution;
- writes one meaningful `quote_approved` activity event with safe identifiers only;
- returns the refreshed quote;
- returns a stable conflict for an already-approved quote and a not-found response for inaccessible tenant data.

### Project handoff operation

`POST /api/v1/quotes/{quote_id}/handoff`:

- is staff-authenticated and tenant-scoped;
- requires an approved quote linked to the caller's customer;
- creates one existing `Project` in `booked` state, retaining its customer and a traceable `quote_id` relationship;
- writes one `quote_handed_off` activity event;
- returns the resulting project;
- is idempotent: a repeat handoff returns the already-linked project and never creates another.

The project-side unique quote relationship is the database-enforced duplicate prevention mechanism. Existing projects have a nullable `quote_id` so historical data remains valid.

### Database contract

One additive Alembic revision may add only the columns and constraints necessary for this contract:

- quote `status`, `approved_at`, and `approved_by_user_id`;
- project `quote_id`, foreign-keyed to `quotes.id` and uniquely constrained.

The migration preserves existing rows by assigning the safe pre-approval default to historical quotes, retains tenant FKs, and is verified by an upgrade/downgrade/upgrade round trip.

### UI contract

The real quote detail page renders state, approval and handoff actions only when valid. It provides pending/disabled and error feedback, refreshes its real API state after each transition, and links directly to the resulting Project after handoff. It does not introduce a parallel quote/customer creation flow or a mocked state transition.

## Mandatory invariants

- Tenant A cannot read, approve, or hand off Tenant B's quote, nor attach Tenant B's customer or project.
- A portal token cannot acquire staff approval/handoff authority.
- Invalid transitions are rejected server-side.
- Repeated approval has stable domain behaviour; repeated handoff cannot create duplicate Projects.
- Approval and handoff records activity using safe, useful identifiers without quote contents or secrets.
- The frontend calls the real API and persisted backend state survives refetch/reload.

## Verification requirements

TDD covers approval, invalid/repeated transitions, RBAC, tenant isolation, activity events, rollback where testable, project linkage, and duplicate protection. Frontend tests cover visible/hidden actions, success, errors, pending state, and project navigation using the existing repository conventions where available. A real browser E2E journey must exercise Customer → Quote → Approve → Handoff → Project through the frontend.

Before staging, run backend, migration, frontend lint/type/build/tests, E2E, existing auth/RBAC/quote/project tests, Sprint 019 non-destructive regression, `git diff --check`, and a secret scan. Stage only approved Sprint 020 files after review; never stage unrelated local evidence or environment files.

## Explicitly out of scope

- Appointment/calendar functionality.
- A new enquiry subsystem or unrelated CRM work.
- A general quote update/delete editor, sending/email delivery, customer self-service approval, billing, payment collection, or a new permissions framework.
- A new notification subsystem. Existing activity is mandatory; a notification is added only if an existing recipient/action convention makes it an obvious narrow extension.
- Sprint 019 recovery changes or any Sprint 021 work.

## Implementation evidence

Pending implementation and verification. This section must be updated only with fresh command/test/staging evidence.
