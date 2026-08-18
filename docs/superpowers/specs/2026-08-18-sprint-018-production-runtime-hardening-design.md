# Sprint 018 — Production Runtime Hardening Design

**Date:** 2026-08-18
**Status:** Proposed for approval
**Scope:** Launch readiness and production runtime hardening only

## 1. Context

SIMO OS now has a credible multi-tenant SaaS product surface: authenticated workspaces and staff, tenant-isolated customers/projects/quotes, invoices, a client portal, documents, and two-way portal messaging. The backend and frontend pass their automated suites, but the runtime still assumes local development in several important places:

- no explicit application environment distinguishes development, test, and production;
- the backend has usable insecure defaults for JWT signing and the seeded Owner account;
- sample data and the seeded Owner are created during module import/startup;
- CORS allows every origin, method, and header;
- `/health` reports success without checking PostgreSQL;
- logs are unstructured and requests have no correlation identifier;
- no production backend container or startup contract exists;
- the frontend silently falls back to a loopback API URL during a production build;
- uploaded documents use local disk without a production persistent-volume contract;
- deployment, migration, rollback, and health verification procedures are not documented.

Sprint 018 closes those runtime gaps without changing product features, tenant semantics, billing, storage technology, or the stale roadmap.

## 2. Goals

Sprint 018 will:

1. Introduce an explicit `development | test | production` runtime mode.
2. Refuse to start or run a production release command with unsafe authentication or seed configuration.
3. Prevent all startup seeding in production while preserving convenient local and test behavior.
4. Restrict production CORS to an explicit configured origin allowlist.
5. Keep a dependency-free liveness endpoint and add database-aware readiness.
6. Emit structured JSON production logs with a request ID for every HTTP request and unhandled error.
7. Provide a provider-neutral production backend container and startup command.
8. Fail an explicitly production-targeted frontend build when its backend URL is missing or unsafe.
9. Make the persistence requirements and scaling limits of local document storage operationally explicit.
10. Document a migration-first release sequence, rollback policy, and health-check procedure.
11. Prove the production gates and health behavior with automated tests.

## 3. Non-goals

The following are explicitly outside Sprint 018:

- selecting or provisioning a hosting provider;
- S3 or any other object-storage migration;
- virus scanning or content sniffing;
- storage quotas;
- email delivery, password reset, or account recovery;
- billing, subscriptions, plans, trials, or making `tenants.status` load-bearing;
- rate limiting;
- WebSockets or SSE;
- a full APM, metrics, tracing, or alerting platform;
- application-feature changes, including reopening Sprint 017;
- reconciliation or modification of `docs/ROADMAP.md`;
- Sprint 019 planning or implementation.

## 4. Considered approaches

### 4.1 Recommended: provider-neutral hardening inside the existing stack

Use Pydantic Settings for environment policy, FastAPI middleware and standard-library logging for request observability, SQLAlchemy for readiness, and a conventional OCI/Docker backend image. This gives the repository a complete production contract without choosing a cloud provider or adding an observability vendor.

This approach is selected because it is testable locally, portable, and proportionate to the current system.

### 4.2 Rely on the eventual hosting platform

A platform could supply CORS configuration, health checks, log formatting, request IDs, migration jobs, and secret validation. This is rejected because hosting selection is out of scope and would leave core safety dependent on an undecided vendor.

### 4.3 Introduce an observability/configuration framework

A dedicated logging or telemetry stack could provide richer tracing and metrics. This is rejected for Sprint 018 because it adds operational dependencies before there is a concrete APM requirement. The selected design deliberately creates stable request-ID and JSON-log fields that a future platform can ingest.

## 5. Runtime environment and configuration contract

### 5.1 Environment mode

Backend settings gain `app_env`, represented by an enum with exactly:

- `development` — default when unset;
- `test` — explicit automated-test mode;
- `production` — strict production policy.

The environment variable is `APP_ENV`. Unknown values are configuration errors. There is no implicit production detection based on hostname, process command, or `NODE_ENV`.

Development remains convenient: the existing local database URL, JWT secret, seed credentials, loopback frontend API URL, and startup seeding continue to work when `APP_ENV` is unset or set to `development`.

Tests will explicitly set or override `APP_ENV=test` where isolation from development policy matters. Production behavior must never be inferred merely because pytest or a frontend build is running.

### 5.2 Production-only validation

Pydantic settings validation is the single source of truth. When `APP_ENV=production`, configuration is rejected if any of the following is true:

- `JWT_SECRET_KEY` is missing, blank, shorter than 32 characters, or equals the repository's development default;
- `SEED_ADMIN_EMAIL` is missing, blank, or equals the repository's development default;
- `SEED_ADMIN_PASSWORD` is missing, blank, shorter than 12 characters, or equals the repository's development default;
- startup seeding is enabled;
- `CORS_ALLOWED_ORIGINS` is empty;
- a CORS origin is `*`, is not an absolute `http`/`https` origin, or includes a path, query, fragment, or credentials;
- `UPLOAD_DIR` is missing or blank;
- `DATABASE_URL` is missing or still points at the repository's default local database;

Production permits `http://localhost` nowhere in the configured CORS list. Non-loopback `http` origins are also rejected; production browser origins must use HTTPS.

Validation errors must name the setting and violated rule but must never print secret values or embed the database password. Pydantic input values are hidden in validation errors, and the runtime-check command emits a sanitized summary rather than serializing a raw `ValidationError`. The same settings validation runs when importing the backend application and when Alembic imports its environment, so an unsafe production configuration cannot start the app or run a release migration.

### 5.3 Explicit configuration check

Provide a small read-only command, invoked as:

```text
python -m app.core.runtime_check
```

It loads the same `Settings`, exits non-zero on failure, and prints only a sanitized success summary (`app_env`, database host/name if safely redacted, CORS-origin count, upload directory, and seeding enabled/disabled). It does not connect to the database, run migrations, create directories, or seed rows.

The release runbook uses this command as step one. App startup still loads and validates settings independently; the command is an observable preflight, not the only enforcement point.

### 5.4 Seed policy

Add a `seed_data_enabled` boolean setting exposed as `SEED_DATA_ENABLED`:

- default `true` in development and test, preserving current local behavior and existing tests;
- required `false` in production;
- if explicitly set, the explicit value is honored outside production;
- production plus `true` is a startup/configuration error rather than silently ignoring the request.

All four startup seed functions—activity, notifications, users, and materials—must be behind the same policy. Production startup calls none of them. Sprint 018 does not split reference-material seeding from demo/account seeding; production data loading is an explicit operator concern outside automatic app startup.

The current seed functions remain idempotent for development/test. Their business contents are unchanged.

## 6. Application startup lifecycle

`app/main.py` will use FastAPI's lifespan mechanism for runtime initialization. Importing modules must not perform database writes.

Startup sequence:

1. Settings are constructed and validated.
2. Logging is configured for the selected environment.
3. The upload directory is validated. Development/test may create a missing directory; production requires the mounted directory to exist already and be writable, so a missing volume cannot be silently replaced by ephemeral container storage.
4. If `seed_data_enabled` is true, the existing seed functions run once in the current order.
5. The application begins serving requests.

Production startup does not:

- run Alembic;
- create application data;
- downgrade or otherwise mutate the schema;
- wait indefinitely for PostgreSQL;
- select or configure a hosting provider.

If required startup initialization fails, the process exits non-zero before it can become ready. Secrets are never logged.

## 7. CORS policy

Add `cors_allowed_origins`, configured through comma-separated `CORS_ALLOWED_ORIGINS` and normalized into a list by Settings.

Defaults:

- development/test: `http://localhost:3000` and `http://127.0.0.1:3000` are allowed;
- production: no default; one or more explicit HTTPS origins are required.

FastAPI's `CORSMiddleware` receives only this parsed list. `allow_credentials=True` remains because bearer-authenticated browser requests and future cookie-compatible behavior must not be accidentally broken. Methods and headers may remain broad, but only approved origins can receive CORS permission. This sprint does not attempt to use CORS as API authentication; tenant/auth enforcement remains server-side.

Tests will exercise actual preflight requests for an allowed and a denied origin rather than only inspecting settings values.

## 8. Health endpoints

### 8.1 Liveness: `GET /health`

The existing unversioned route remains the liveness endpoint and preserves its response contract:

```json
{"status":"healthy"}
```

It performs no database, filesystem, network, or migration check. It answers only whether the application process can serve HTTP. This preserves existing clients and makes it safe for frequent container liveness probes.

### 8.2 Readiness: `GET /ready`

Add an unversioned, unauthenticated readiness endpoint. It executes a bounded `SELECT 1` through the existing SQLAlchemy engine.

- success: HTTP 200 with `{"status":"ready","database":"reachable"}`;
- database unavailable or timed out: HTTP 503 with `{"status":"not_ready","database":"unreachable"}`.

The failure is logged with request ID and exception class, but the response never exposes a connection string, host, credentials, stack trace, or raw database error.

Readiness checks connectivity, not Alembic revision. Schema state is verified explicitly during the release job after `alembic upgrade head`; the application does not query or mutate migration state on every readiness probe.

The readiness probe has a two-second maximum duration, centralized as `READINESS_TIMEOUT_SECONDS=2`. Connection acquisition and `SELECT 1` execution must both fit within that bound; exhaustion or timeout returns the same safe 503 response as any other database failure. Tests simulate timeout without sleeping against a real outage.

Neither health endpoint returns application version, environment variables, tenant data, or secrets.

## 9. Structured logging and request IDs

### 9.1 Log format

Production application logs are one JSON object per line to stdout/stderr. No log files are written inside the container. Stable events introduced this sprint are `http_request_completed`, `unhandled_exception`, `readiness_failed`, and `startup_failed`. The required fields are:

- `timestamp` — UTC RFC 3339;
- `level`;
- `logger`;
- `event` — stable machine-readable event name;
- `message` — concise human-readable text;
- `request_id` when request-scoped;
- `method`, `path`, `status_code`, and `duration_ms` for request completion;
- `exception_type` for unhandled failures.

Development retains readable console logs. Both formats use the same event names. Query strings are excluded from routine request logs because portal and invitation tokens appear in URL paths/query-adjacent request data elsewhere in the system; authorization headers and request/response bodies are never logged.

### 9.2 Request-ID middleware

Middleware runs for every HTTP request, including health checks and error responses:

1. Read `X-Request-ID` if supplied.
2. Accept it only when it is 1–128 characters and contains ASCII letters, digits, `.`, `_`, or `-`.
3. Generate a UUID when the header is missing or invalid.
4. Store the value on `request.state.request_id` and in a context-local logging field.
5. Return the identifier in the `X-Request-ID` response header.
6. Emit one request-completed log with status and duration.

The context-local value is reset after every request so concurrent requests cannot leak identifiers into one another. Client-provided values are correlation aids, not trusted identity or authorization data.

### 9.3 Error logging

The existing exception-response contracts stay unchanged. Unexpected exceptions still return only:

```json
{"detail":"Internal server error"}
```

The catch-all error handler emits a structured `unhandled_exception` record containing the request ID, method, path, and exception stack trace. Validation and known 4xx responses are represented by the normal request-completed record and are not logged with stack traces.

Request IDs are exposed through the response header rather than changing every JSON error schema.

## 10. Production backend container

Add a provider-neutral backend `Dockerfile` at the repository root and a `.dockerignore`.

Container requirements:

- Python 3.12 slim runtime, matching CI;
- install dependencies from the existing pinned `requirements.txt`;
- copy only files needed to run FastAPI and Alembic;
- run as a dedicated non-root user;
- write application data only beneath configured writable paths;
- expose port 8000;
- default command starts Uvicorn for `app.main:app` on `0.0.0.0:8000`;
- do not include `.env`, `.git`, local virtual environments, `node_modules`, test caches, local uploads, `.agents`, or `.claude` in the image;
- do not run Alembic in `ENTRYPOINT`, `CMD`, or an application lifespan hook;
- do not bake secrets or environment-specific URLs into image layers.

The same image supports two operator-controlled commands:

- release job: `alembic upgrade head`;
- application: the default Uvicorn command.

The image includes a Docker health check against `/health`. Deployment readiness must use `/ready`; container liveness does not substitute for the deployment readiness gate. No provider-specific manifest is added.

Sprint 018 does not add Gunicorn or multiple Uvicorn workers. Horizontal process count belongs to the deployment platform, and local document storage constrains the service to one writer unless every instance mounts the same supported persistent filesystem.

## 11. Frontend production API URL validation

The frontend will use the same explicit `APP_ENV` build-time signal:

- development/test or unset: retain the current `http://127.0.0.1:8000` fallback;
- production: `NEXT_PUBLIC_API_URL` is required and must be an absolute HTTPS origin with no path, query, fragment, or credentials;
- production loopback, wildcard, and plain-HTTP URLs are rejected during Next.js configuration evaluation, causing `pnpm build` to fail before an unusable artifact is produced.

The validated URL remains the single source consumed by `apps/web/lib/api.ts`; individual pages continue to make no direct configuration decisions.

CI's ordinary production-optimized Next.js compilation remains convenient by leaving `APP_ENV` unset/test unless CI is specifically testing the strict production contract. A dedicated test/build invocation will set `APP_ENV=production` and supply a safe example URL. This separates Next.js optimization mode (`NODE_ENV=production`) from SIMO OS deployment intent (`APP_ENV=production`).

No frontend container or provider deployment manifest is added in this sprint; the requested container scope is the backend runtime.

## 12. Persistent upload-volume contract

Sprint 018 retains local filesystem document storage. In production:

- `UPLOAD_DIR` must be an absolute path;
- the path must be backed by a persistent volume that survives container replacement and application rollback;
- the application user must have read/write access;
- operators must verify persistence with an upload/restart/download smoke test before admitting real customer documents;
- backups and restore procedures for that volume are an operator responsibility and must be called out in the runbook;
- ephemeral container filesystems are unsupported for production documents.

Because local disk remains the storage technology, the supported Sprint 018 topology is one backend application instance, or multiple instances sharing the same correctly mounted filesystem. Sprint 018 does not claim safe multi-instance document operation when each instance has independent local disk.

The application validates that `UPLOAD_DIR` is usable at startup without deleting or rewriting existing files. Existing document filenames, database rows, download behavior, limits, and tenant/customer isolation are unchanged.

## 13. Release and rollback runbook

Add `docs/PRODUCTION_RUNBOOK.md` covering prerequisites, release, rollback, and verification.

### 13.1 Release sequence

The normative production order is:

1. Supply production environment variables and mounted storage.
2. Run `python -m app.core.runtime_check` and require exit code 0.
3. Run `alembic upgrade head` as a one-off release command/job using the new application image.
4. Verify the command succeeded and `alembic current` reports the expected sole head.
5. Start or restart backend application containers. Containers do not run migrations.
6. Check `/health` until liveness succeeds.
7. Check `/ready` until database readiness succeeds.
8. Verify a minimal authenticated API request and document-volume persistence.
9. Only then route production traffic to the new release.

Any failure before step 9 blocks traffic promotion. Logs and commands must be captured by the deployment system, but no specific system is selected.

### 13.2 Application rollback

Rolling back the application means deploying the previous application image with the same production configuration and volume. It does not automatically run `alembic downgrade`.

An application rollback is allowed only when the previous version is compatible with the current schema. Every future migration should document backward-compatibility expectations during its own design/review.

### 13.3 Database rollback

Database downgrade is a separate, explicit operator action. It may be run only when:

- the exact migration is known to have a safe and tested downgrade;
- data-loss implications are understood and accepted;
- the application has been stopped or otherwise prevented from writing incompatible data;
- a current database backup exists and restore access has been verified.

The runbook does not present database downgrade as the default response to a failed release. Forward fixes or application rollback with a compatible schema are preferred.

### 13.4 Health-check interpretation

- `/health` failing: process/runtime failure; restart or inspect application startup logs.
- `/health` passing and `/ready` failing: application is running but PostgreSQL is unavailable; do not send traffic.
- both passing but migration verification failing: do not send traffic; readiness does not certify schema revision.
- both passing after promotion: continue with the authenticated and persistent-volume smoke checks.

## 14. Testing strategy

Sprint 018 adds focused tests without requiring a real production deployment.

### 14.1 Configuration tests

Use isolated `Settings` construction with explicit environment dictionaries; do not mutate the process-global settings singleton across unrelated tests.

Cover:

- development defaults remain accepted;
- all three environment values parse and an unknown value fails;
- production accepts a complete safe configuration;
- production rejects the default/blank JWT secret;
- production rejects enabled seeding and insecure/default seed credentials;
- production rejects absent/wildcard/HTTP/loopback/malformed CORS origins;
- production rejects the default local database URL and a relative upload directory;
- validation errors do not contain supplied secret values;
- runtime-check success and failure exit codes are deterministic and sanitized.

### 14.2 Seeding and startup tests

Move startup behavior behind testable functions/lifespan boundaries and prove:

- development/test with seeding enabled invokes each existing seed function once;
- production configuration cannot enable seeding;
- production startup invokes no seed function;
- a startup initialization failure prevents the lifespan from reaching the serving state;
- importing `app.main` no longer writes database rows;
- app startup never invokes an Alembic command.

Mocks/spies are used for call-contract tests; existing integration tests continue proving the real development seed path.

### 14.3 CORS tests

Using `TestClient`, send real browser preflight requests and prove:

- an allowlisted origin receives the expected CORS response;
- a non-allowlisted origin receives no permissive allow-origin header;
- wildcard production configuration is rejected before app startup.

### 14.4 Health tests

Cover:

- `/health` returns its existing 200 payload even when the readiness database probe is mocked unavailable;
- `/ready` returns 200 for a successful probe;
- `/ready` returns 503 for connection/query failure;
- readiness failure responses and logs do not expose connection details;
- neither endpoint requires authentication.

### 14.5 Logging and request-ID tests

Cover:

- a missing ID is generated and returned;
- a valid incoming ID is preserved;
- invalid or oversized IDs are replaced;
- normal and unhandled-error requests emit the required structured fields;
- concurrent/context cleanup prevents an ID from leaking to the next request;
- authorization headers, request bodies, query strings, and secrets are absent from captured logs;
- the 500 JSON response remains unchanged while carrying `X-Request-ID`.

### 14.6 Container and frontend verification

Verify:

- the backend image builds;
- the container runs as non-root;
- its default command starts the app without running Alembic;
- `.env`, local uploads, `.agents`, and `.claude` are absent from build context/image;
- the container responds on `/health` and `/ready` when connected to a migrated test database and writable volume;
- a normal local frontend build still succeeds without `APP_ENV=production`;
- an explicit production build fails when `NEXT_PUBLIC_API_URL` is missing or unsafe;
- an explicit production build succeeds with a valid HTTPS API origin.

The existing full backend suite, Alembic check and round-trip, frontend lint/type/build, `git diff --check`, tenant-isolation review, and scope review remain release gates.

## 15. Documentation impact

Sprint 018 implementation will update only documentation affected by the runtime contract:

- `docs/DECISIONS.md` — ADR for explicit environment policy, separate migration release step, health semantics, and provider-neutral structured logging;
- `docs/SYSTEM_ARCHITECTURE.md` — runtime lifecycle, health endpoints, logging middleware, and container boundary;
- `docs/API_SPEC.md` — `/ready`, preserved `/health`, and request-ID response header behavior;
- `docs/CHANGELOG.md` — launch-readiness summary;
- `.env.example` and `apps/web/.env.local.example` — documented safe configuration contract;
- a new production operations runbook;
- `docs/SPRINTS/sprint-018.md` at implementation completion.

`docs/ROADMAP.md` is explicitly not modified.

## 16. Security and tenant-isolation impact

Sprint 018 changes runtime infrastructure, not resource authorization:

- existing JWT, role, portal-token, and tenant filters remain intact;
- request IDs carry no authority and are never used in database queries;
- readiness exposes only reachable/unreachable state and no database metadata;
- logs exclude credentials, authorization headers, bodies, query strings, and tenant/customer data by default;
- CORS narrows browser access but is not treated as an authentication boundary;
- production seeding cannot create a predictable Owner account;
- container execution is non-root and uploaded files live only in the configured mounted path;
- no new public write endpoint is introduced.

The implementation review must confirm that existing portal URLs and tokens are not accidentally captured in logged paths. Because portal tokens are path parameters, routine logging must use the matched route template when available (for example, `/api/v1/portal-links/token/{token}/messages`) rather than the concrete raw path. If no route template is available during an early failure, the logger must omit the path rather than log a possibly sensitive concrete URL.

## 17. Acceptance criteria

Sprint 018 is complete when all of the following are true:

1. Development works with current defaults and automatic seed behavior unless explicitly disabled.
2. `APP_ENV=production` with any known insecure default fails before serving or migrating.
3. A safe production configuration passes the same validation for runtime and Alembic.
4. Production startup performs zero seed writes and zero migration commands.
5. Production CORS grants access only to configured HTTPS origins.
6. `/health` remains dependency-free and backward-compatible.
7. `/ready` reflects PostgreSQL reachability with safe 200/503 responses.
8. Every response carries a valid `X-Request-ID`; production request/error logs are structured JSON and redact sensitive data.
9. The backend image builds, runs as non-root, and starts only the application.
10. An explicit production frontend build cannot use a missing, loopback, wildcard, path-bearing, or plain-HTTP API URL.
11. Production upload storage requires an absolute, writable persistent mount, documented and smoke-tested.
12. The runbook describes and verifies the exact migration-first release order and explicit database rollback policy.
13. Targeted Sprint 018 tests, the full backend suite, Alembic checks/round-trip, frontend lint/type/build, container smoke test, and diff/scope/security reviews pass.
14. No out-of-scope feature, roadmap change, hosting-provider choice, commit, or push is included before approval.
