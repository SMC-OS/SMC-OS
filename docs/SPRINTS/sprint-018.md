# Sprint 018 — Production Runtime Hardening

Status: implementation and independent production-readiness verification complete.

## Delivered

- Explicit development, test, and production runtime modes with strict production validation.
- Production seeding suppression, configurable CORS, import-safe startup, and writable persistent upload-mount validation.
- Unauthenticated `/health` liveness and database-aware `/ready` readiness.
- Validated request IDs plus structured production request, readiness, startup, and unhandled-error logging with redaction.
- Non-root Python 3.12 production image whose default command starts Uvicorn only.
- Strict frontend production API-origin validation with Node 20 CI regression coverage.
- Provider-neutral release, rollback, health-check, and persistent-volume runbook.

## Integrated evidence

- Targeted Sprint 018 backend suite: 71 passed, 2 pre-existing deprecation warnings.
- Full backend suite: 249 passed, 0 failed, 278 warnings.
- Alembic: current and sole head `f81683afc3f4`; schema check found no new operations; downgrade-one/upgrade-head round trip passed and returned to head.
- Frontend: seven-case build matrix matched all expected success/failure exits; resolver regressions 7 passed; lint and TypeScript checks passed; safe strict production build passed.
- Container: image build passed; configured user `simo`, runtime UID 10001; no entrypoint; Uvicorn-only default command; separate image-based `alembic upgrade head` release command passed.
- Runtime smoke: container became healthy; `/health` returned 200; `/ready` returned 200 with database reachable; a marker in the mounted upload volume survived container restart.
- Independent final verification reproduced the 71-test targeted and 249-test full backend results, all production failure modes, the frontend test/lint/type/build matrix, the migration round trip, and the container restart smoke. No reproducible defect remained.
- Security/configuration review found no secret leakage, concrete sensitive-path logging, production seeding, startup migration, tenant-isolation change, or prohibited scope addition.
- `docs/ROADMAP.md` was not changed. `.agents/` and `.claude/` remain excluded local tooling.

## Known limitations and follow-ups

- Upload persistence requires an operator-provisioned writable volume and a shared-filesystem strategy before running more than one backend instance.
- Existing dependency deprecation warnings remain; they are not Sprint 018 regressions.
- One readiness request returned the specified safe 503 during concurrent local verification; direct database probes and two immediate isolated retries returned 200, so this was recorded as transient local contention rather than a reproducible defect.
- Hosting-provider selection, object storage, malware scanning, quotas, email/password reset, billing, rate limiting, WebSockets/SSE, and a full APM/metrics platform remain out of scope.
