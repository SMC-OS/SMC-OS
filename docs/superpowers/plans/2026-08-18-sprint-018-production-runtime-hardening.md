# Sprint 018 Production Runtime Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing SIMO OS backend and frontend safe to configure, start, observe, health-check, containerize, migrate, and roll back in a provider-neutral production environment without changing product behavior.

**Architecture:** Extend the existing Pydantic Settings layer with an explicit runtime environment and fail-fast production policy, then construct FastAPI through an app factory/lifespan so startup work is testable and import-safe. Add focused health, logging, and request-context modules; keep migrations as an operator-owned release command; package the backend in a non-root OCI image; and make the Next.js production API origin an explicit build contract.

**Tech Stack:** Python 3.12, FastAPI, Pydantic Settings 2.15, SQLAlchemy 2.0, PostgreSQL 16, Alembic, pytest/TestClient, Python standard-library logging/contextvars, Next.js 16, TypeScript 5.9, pnpm/Turborepo, Docker/OCI.

**Spec:** `docs/superpowers/specs/2026-08-18-sprint-018-production-runtime-hardening-design.md`

## Global Constraints

- The approved design is authoritative; do not reopen brainstorming or alter its runtime contracts.
- Runtime modes are exactly `development`, `test`, and `production`; `APP_ENV` defaults to `development`.
- Production must reject unsafe JWT/seed defaults, enabled seeding, unsafe CORS, a local-default database URL, and a missing/relative upload directory before serving or migrating.
- Production database migrations run only as a separate release command/job: `alembic upgrade head`.
- Backend `ENTRYPOINT`, `CMD`, lifespan, and seed code must never invoke Alembic.
- Production startup must perform no seed writes; development/test seeding remains convenient and idempotent.
- `/health` remains unversioned, unauthenticated, dependency-free, and response-compatible; `/ready` is unversioned, unauthenticated, PostgreSQL-aware, bounded to two seconds, and never exposes database details.
- Production logs are JSON lines; request IDs are accepted only with the approved character/length policy and returned in `X-Request-ID`.
- Logs must not contain secrets, authorization headers, bodies, query strings, or concrete portal/invitation token paths.
- Production backend containers run as non-root, start only Uvicorn, and require an existing writable persistent `UPLOAD_DIR` mount.
- An explicit frontend production build requires an absolute HTTPS `NEXT_PUBLIC_API_URL` origin; development/test retain the loopback fallback.
- Do not add a hosting provider, object storage, malware scanning, quotas, email/recovery, billing, rate limiting, WebSockets/SSE, APM/metrics, roadmap reconciliation, or Sprint 019 work.
- Do not modify `docs/ROADMAP.md`. Keep `.agents/` and `.claude/` excluded.
- Every production-code change follows red-green-refactor TDD. A targeted failing test must be observed before its minimal implementation.
- During implementation, verification agents are read-only. Commit/push only when the user explicitly authorizes it.

---

## File map and ownership

### Backend configuration and lifecycle

- Modify `app/core/config.py`: `AppEnvironment`, strict Settings fields/validators, safe development defaults.
- Create `app/core/runtime_check.py`: sanitized read-only configuration preflight CLI.
- Create `app/core/startup.py`: upload-directory preparation and conditional seed orchestration.
- Modify `app/main.py`: `create_app()`, FastAPI lifespan, middleware/router assembly; remove import-time seed calls.
- Modify `.env.example`: document every Sprint 018 backend environment variable and release-safe values.

### Health and observability

- Create `app/core/health.py`: liveness/readiness router and injectable database probe.
- Create `app/core/logging.py`: production JSON formatter, development formatter, context-local request ID, stable log events.
- Create `app/core/middleware.py`: request-ID validation/generation and one completion log per request.
- Modify `app/core/errors.py`: structured unhandled-error logging while preserving response bodies.

### Container and frontend

- Create `Dockerfile`: non-root Python 3.12 backend runtime; no migration entrypoint.
- Create `.dockerignore`: exclude secrets, tooling, dependencies, caches, uploads, `.agents`, and `.claude`.
- Create `apps/web/lib/runtime-config.ts`: pure production API-origin validator.
- Modify `apps/web/next.config.ts`: validate production deployment intent during config evaluation.
- Modify `apps/web/lib/api.ts`: consume the validated/defaulted shared API origin.
- Modify `apps/web/.env.local.example`: document frontend `APP_ENV` and production URL requirements.

### Tests and documentation

- Create `tests/test_runtime_config.py`: environment, secret/default, CORS, upload, and sanitization tests.
- Create `tests/test_runtime_startup.py`: no import writes, seed policy, startup failure, upload mount, and no-Alembic tests.
- Create `tests/test_runtime_http.py`: CORS, liveness/readiness, request IDs, structured logging, and redaction tests.
- Create `docs/PRODUCTION_RUNBOOK.md`: exact release, rollback, migration, volume, and health procedures.
- Modify `docs/DECISIONS.md`, `docs/SYSTEM_ARCHITECTURE.md`, `docs/API_SPEC.md`, and `docs/CHANGELOG.md` after behavior is verified.
- Create `docs/SPRINTS/sprint-018.md` only at implementation completion, recording actual evidence rather than planned results.

## Dependency and parallel-execution map

```text
Baseline
  └─ Task 1 configuration contract
      └─ Task 2 startup/seeding/upload lifecycle
          └─ Task 3 app factory + CORS
              └─ Task 4 health endpoints
                  └─ Task 5 request IDs + structured logging
                      ├─ Task 6 Docker/container contract ─────┐
                      ├─ Task 7 frontend URL validation ──────┤ parallel wave
                      └─ Task 8 runbook + canonical docs ─────┘
                              └─ Task 9 integrated regression gates
                                  └─ Task 10 parallel final verification
                                      └─ Task 11 final evidence/scope review
```

Tasks 1–5 are sequential because they establish and repeatedly touch `Settings`, `create_app()`, lifespan, middleware ordering, and error handling. Tasks 6–8 can run concurrently after Task 5: they own disjoint files and consume frozen contracts. Task 9 is sequential integration. Task 10 dispatches four read-only verification agents in parallel. Task 11 reconciles their actual outputs and is sequential.

---

### Task 0: Baseline and red-test harness

**Files:**
- Read: approved spec and every file in the file map
- Do not modify production files

**Interfaces:**
- Consumes: committed Sprint 017 state at `b28ac240f307001985c123df4a7d3690a2d810e5`
- Produces: captured baseline and a confirmed clean index before implementation

- [ ] **Step 1: Confirm the repository boundary**

Run:

```powershell
git status --short
git branch -vv
git log -1 --oneline
git diff -- docs/ROADMAP.md
```

Expected: `main` and `origin/main` point at Sprint 017; only `.agents/`, `.claude/`, the approved Sprint 018 spec, and this plan may be untracked; ROADMAP diff is empty.

- [ ] **Step 2: Capture baseline verification**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
pnpm lint
pnpm check-types
pnpm build
```

Expected: the accepted Sprint 017 baseline remains green before Sprint 018 code changes.

- [ ] **Step 3: Read the approved contracts before editing**

Run:

```powershell
Get-Content -Raw docs/superpowers/specs/2026-08-18-sprint-018-production-runtime-hardening-design.md
Get-Content -Raw app/core/config.py
Get-Content -Raw app/main.py
Get-Content -Raw app/core/errors.py
```

Expected: no implementation action occurs until the executor can state the environment, migration, health, logging, and volume invariants.

---

### Task 1: Runtime environment and production configuration model

**Files:**
- Modify: `app/core/config.py`
- Create: `app/core/runtime_check.py`
- Create: `tests/test_runtime_config.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: Pydantic `BaseSettings` and existing `settings = Settings()` import contract
- Produces: `AppEnvironment`, `Settings.app_env`, `Settings.seed_data_enabled`, `Settings.cors_allowed_origins`, `Settings.readiness_timeout_seconds`, production validation, and `python -m app.core.runtime_check`

- [ ] **Step 1: Write failing development and parsing tests**

Add tests that instantiate settings without the repository `.env`:

```python
from app.core.config import AppEnvironment, Settings


def make_settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


def test_development_defaults_remain_convenient():
    configured = make_settings()
    assert configured.app_env is AppEnvironment.DEVELOPMENT
    assert configured.seed_data_enabled is True
    assert configured.cors_allowed_origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_unknown_app_environment_is_rejected():
    with pytest.raises(ValidationError):
        make_settings(app_env="staging")
```

- [ ] **Step 2: Run the focused tests and observe RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_runtime_config.py -q
```

Expected: collection/import fails because `AppEnvironment` and the new fields do not exist.

- [ ] **Step 3: Implement the environment and normalized CORS fields**

Add the exact public contract:

```python
class AppEnvironment(str, Enum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_env: AppEnvironment = AppEnvironment.DEVELOPMENT
    seed_data_enabled: bool = True
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )
    readiness_timeout_seconds: float = 2.0
```

Use a `field_validator(..., mode="before")` that accepts either a comma-separated string or list, strips entries, and rejects empty entries. Keep all existing setting names and defaults unchanged outside production.

- [ ] **Step 4: Write the complete failing production-policy matrix**

Use one valid base and mutate one field per test:

```python
SAFE_PRODUCTION = {
    "app_env": "production",
    "database_url": "postgresql+psycopg://simo:strong-password@db.internal/simo_os",
    "jwt_secret_key": "x" * 32,
    "seed_admin_email": "bootstrap@example.invalid",
    "seed_admin_password": "safe-bootstrap-password",
    "seed_data_enabled": False,
    "cors_allowed_origins": ["https://app.example.com"],
    "upload_dir": "/var/lib/simo-os/uploads",
}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("jwt_secret_key", "dev-only-insecure-secret-change-me"),
        ("jwt_secret_key", "short"),
        ("seed_admin_email", "owner@simo-os.local"),
        ("seed_admin_password", "change-me-on-first-login"),
        ("seed_data_enabled", True),
        ("cors_allowed_origins", []),
        ("cors_allowed_origins", ["*"]),
        ("cors_allowed_origins", ["http://app.example.com"]),
        ("cors_allowed_origins", ["https://app.example.com/path"]),
        ("database_url", "postgresql+psycopg://simo:simo@localhost:5432/simo_os"),
        ("upload_dir", "./uploads"),
    ],
)
def test_production_rejects_unsafe_configuration(field, value):
    values = {**SAFE_PRODUCTION, field: value}
    with pytest.raises(ValidationError):
        make_settings(**values)
```

Also assert production accepts `SAFE_PRODUCTION`, `readiness_timeout_seconds` must be positive and no greater than 10, and each CORS value is an origin with scheme/host only.

- [ ] **Step 5: Run production-policy tests and observe RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_runtime_config.py -q
```

Expected: the unsafe production cases are accepted because the cross-field validator does not exist.

- [ ] **Step 6: Implement minimal fail-fast validation**

Add a model-level validator that calls focused private helpers:

```python
@model_validator(mode="after")
def validate_runtime_contract(self) -> "Settings":
    if self.app_env is not AppEnvironment.PRODUCTION:
        return self
    self._validate_production_secrets()
    self._validate_production_cors()
    self._validate_production_storage_and_database()
    return self
```

Use `urllib.parse.urlsplit` for origins and `sqlalchemy.engine.make_url` for database inspection. Never interpolate a secret or full database URL into an error. Require production `UPLOAD_DIR` to be absolute but defer filesystem existence/writability to startup.

- [ ] **Step 7: Add failing sanitized CLI tests**

Run the module through `subprocess.run` with an isolated environment and assert:

```python
assert result.returncode != 0
assert "JWT_SECRET_KEY" in result.stderr
assert supplied_secret not in result.stderr
```

For `SAFE_PRODUCTION`, assert exit 0 and a JSON/single-line summary containing `production`, origin count `1`, seeding `false`, and no password/JWT value. Assert the command never calls SQLAlchemy, Alembic, seed functions, or `Path.mkdir` by keeping the module dependent only on `Settings` and URL redaction.

- [ ] **Step 8: Implement `runtime_check.main()` and document variables**

The module must end with:

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

Catch `ValidationError`, print sanitized rule messages to stderr, return `1`; return `0` after a safe summary. Update `.env.example` with `APP_ENV`, `SEED_DATA_ENABLED`, `CORS_ALLOWED_ORIGINS`, `READINESS_TIMEOUT_SECONDS`, and the production absolute `UPLOAD_DIR` rule.

- [ ] **Step 9: Verify Task 1 GREEN**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_runtime_config.py -q
$env:APP_ENV='development'; .venv\Scripts\python.exe -m app.core.runtime_check
Remove-Item Env:APP_ENV
```

Expected: all configuration tests pass; development preflight succeeds without changing files or database rows.

---

### Task 2: Startup lifecycle, production seed suppression, and upload mount

**Files:**
- Create: `app/core/startup.py`
- Modify: `app/main.py`
- Create: `tests/test_runtime_startup.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: `Settings`, `AppEnvironment`, existing `seed_activity`, `seed_notifications`, `seed_users`, `seed_materials`
- Produces: `prepare_upload_directory(settings) -> Path`, `run_seeders(settings, seeders) -> None`, `create_lifespan(settings, seeders)`, import-safe `create_app(settings_override=None)`

- [ ] **Step 1: Write failing upload-directory tests**

Use `tmp_path` and assert:

```python
def test_development_creates_missing_upload_directory(tmp_path):
    target = tmp_path / "new-uploads"
    result = prepare_upload_directory(make_development(upload_dir=str(target)))
    assert result == target.resolve()
    assert target.is_dir()


def test_production_requires_existing_writable_mount(tmp_path):
    target = tmp_path / "missing"
    with pytest.raises(RuntimeError, match="UPLOAD_DIR"):
        prepare_upload_directory(make_production(upload_dir=str(target)))
    assert not target.exists()
```

Monkeypatch the writable probe to assert a non-writable existing production path fails without deleting or rewriting files already present.

- [ ] **Step 2: Run the startup tests and observe RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_runtime_startup.py -q
```

Expected: import fails because `app.core.startup` does not exist.

- [ ] **Step 3: Implement upload preparation**

Resolve the path without requiring it to exist. In development/test create parents with `mkdir(parents=True, exist_ok=True)`. In production require the absolute directory to exist and be a directory. Verify writability by creating and deleting one uniquely named zero-byte probe inside the directory; use `try/finally` so failure never leaves the probe behind. Do not inspect or alter any existing document.

- [ ] **Step 4: Write failing seeder-policy tests**

Pass four `Mock` callables and prove:

```python
def test_development_invokes_every_seeder_once():
    seeders = tuple(Mock() for _ in range(4))
    run_seeders(make_development(seed_data_enabled=True), seeders)
    assert [fn.call_count for fn in seeders] == [1, 1, 1, 1]


def test_disabled_seeding_invokes_nothing():
    seeders = tuple(Mock() for _ in range(4))
    run_seeders(make_development(seed_data_enabled=False), seeders)
    assert [fn.call_count for fn in seeders] == [0, 0, 0, 0]
```

Production-plus-enabled is already rejected by Task 1. Construct a safe production Settings and assert all seeder counts stay zero.

- [ ] **Step 5: Implement conditional seed orchestration**

`run_seeders` must return immediately when disabled and otherwise invoke the injected tuple in the existing order. It must contain no Alembic import, subprocess call, shell call, or migration API.

- [ ] **Step 6: Write failing lifespan and import-safety tests**

Patch `prepare_upload_directory` and `run_seeders`, enter `TestClient` as a context manager, and assert both run during lifespan rather than module import. Add a subprocess test that imports `app.main` with seed functions patched to raise if called; import must succeed. Patch initialization to raise and assert entering `TestClient` raises before a request can be served.

- [ ] **Step 7: Implement `create_app()` and lifespan**

Refactor `app.main` to this boundary:

```python
def create_app(settings_override: Settings | None = None) -> FastAPI:
    runtime_settings = settings_override or settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        prepare_upload_directory(runtime_settings)
        run_seeders(runtime_settings, DEFAULT_SEEDERS)
        yield

    application = FastAPI(..., lifespan=lifespan)
    # middleware, handlers, and routers are assembled here
    return application


app = create_app()
```

Remove the four module-level seed calls. Update `tests/conftest.py` so the shared client fixture uses `with TestClient(app) as test_client: yield test_client`, ensuring lifespan runs predictably.

- [ ] **Step 8: Prove startup never invokes Alembic**

Add an AST-based guardrail test asserting `app/core/startup.py` and `app/main.py` import neither `alembic` nor `subprocess` and contain no call whose qualified name starts with `alembic.`. Avoid a raw substring assertion because documentation may legitimately describe the separate release policy. This guardrail is not a substitute for container inspection.

- [ ] **Step 9: Verify Task 2 GREEN and existing auth setup**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_runtime_startup.py tests/test_health.py tests/test_auth.py -q
```

Expected: lifecycle tests pass; seeded development/test login behavior remains compatible.

---

### Task 3: App factory and configurable CORS

**Files:**
- Modify: `app/main.py`
- Extend: `tests/test_runtime_http.py`

**Interfaces:**
- Consumes: `create_app(settings_override)`, `Settings.cors_allowed_origins`
- Produces: one test-constructible FastAPI application whose CORS middleware uses only the configured origins

- [ ] **Step 1: Write failing real-preflight tests**

Build a development Settings with only `https://allowed.example` and send:

```python
headers = {
    "Origin": "https://allowed.example",
    "Access-Control-Request-Method": "GET",
}
response = client.options("/api/v1/customers", headers=headers)
assert response.headers["access-control-allow-origin"] == "https://allowed.example"
```

Repeat from `https://denied.example` and assert no permissive `access-control-allow-origin` header. Retain a configuration-level test that production `*` fails before `create_app()`.

- [ ] **Step 2: Run focused CORS tests and observe RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_runtime_http.py -k cors -q
```

Expected: the denied origin is allowed because `app.main` still uses `allow_origins=["*"]`.

- [ ] **Step 3: Wire configured CORS into `create_app()`**

Replace the wildcard with:

```python
application.add_middleware(
    CORSMiddleware,
    allow_origins=runtime_settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Do not add origin reflection, regular-expression origins, or route-specific CORS.

- [ ] **Step 4: Verify CORS GREEN**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_runtime_http.py -k cors -q
```

Expected: allowed and denied preflight cases pass.

---

### Task 4: Liveness and database-aware readiness

**Files:**
- Create: `app/core/health.py`
- Modify: `app/main.py`
- Extend: `tests/test_runtime_http.py`
- Modify: `docs/API_SPEC.md` only in Task 8 after behavior is final

**Interfaces:**
- Consumes: SQLAlchemy `engine`, `Settings.readiness_timeout_seconds`, request-ID context established in Task 5 without requiring it
- Produces: `create_health_router(readiness_probe) -> APIRouter`, async `probe_database(timeout_seconds) -> None`, `GET /health`, `GET /ready`

- [ ] **Step 1: Write failing endpoint-contract tests**

Inject an async success probe and failing probe:

```python
async def ready_probe(timeout_seconds: float) -> None:
    assert timeout_seconds == 2.0


async def failed_probe(timeout_seconds: float) -> None:
    raise TimeoutError("secret db host")
```

Assert `/health` always returns `200 {"status":"healthy"}` without calling either probe. Assert `/ready` returns the approved 200 body for success and exact safe 503 body for failure, with no raw exception string.

- [ ] **Step 2: Run health tests and observe RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_runtime_http.py -k "health or ready" -q
```

Expected: `/ready` returns 404 and no injectable router exists.

- [ ] **Step 3: Implement the health router**

Move the existing `/health` function unchanged into `app/core/health.py`. Add `/ready` with explicit `JSONResponse(status_code=503, ...)` on `SQLAlchemyError`, `TimeoutError`, or database-driver error. Log event `readiness_failed` without the exception message.

Implement the real probe by running `SELECT 1` against the existing engine in a worker thread and wrapping the await in `asyncio.timeout(timeout_seconds)`. Always close the connection in the worker. A timed-out probe may finish cleanup in its worker, but the HTTP response must return within two seconds and no executor or connection is retained by the request.

- [ ] **Step 4: Prove authentication and redaction behavior**

Assert neither endpoint requires an `Authorization` header. Capture `simo_os` logs for failure and assert `readiness_failed` and exception type appear while the supplied secret host/error text does not.

- [ ] **Step 5: Verify health GREEN**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_runtime_http.py -k "health or ready" -q
```

Expected: all liveness/readiness contract tests pass.

---

### Task 5: Request IDs and structured request/error logging

**Files:**
- Create: `app/core/logging.py`
- Create: `app/core/middleware.py`
- Modify: `app/core/errors.py`
- Modify: `app/main.py`
- Extend: `tests/test_runtime_http.py`

**Interfaces:**
- Consumes: `Settings.app_env`, FastAPI `Request`, existing exception handlers
- Produces: `request_id_context: ContextVar[str | None]`, `configure_logging(app_env)`, `RequestContextMiddleware`, stable JSON fields/events

- [ ] **Step 1: Write failing request-ID tests**

Assert:

```python
generated = client.get("/health").headers["x-request-id"]
assert UUID(generated)

preserved = client.get("/health", headers={"X-Request-ID": "deploy-018_1"})
assert preserved.headers["x-request-id"] == "deploy-018_1"
```

Parameterize blank, 129-character, whitespace, slash, Unicode, and newline-bearing values and assert each is replaced by a UUID. Add two sequential requests to prove a prior ID does not leak.

- [ ] **Step 2: Run request-ID tests and observe RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_runtime_http.py -k request_id -q
```

Expected: no `X-Request-ID` header exists.

- [ ] **Step 3: Implement request context middleware**

Use the exact acceptance pattern and context cleanup:

```python
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

request_id = incoming if incoming and REQUEST_ID_PATTERN.fullmatch(incoming) else str(uuid.uuid4())
token = request_id_context.set(request_id)
try:
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
finally:
    request_id_context.reset(token)
```

Measure duration with `time.perf_counter()`. Obtain the matched route template from `request.scope.get("route").path` after downstream routing. If unavailable, set `path=None`; never fall back to `request.url.path`.

- [ ] **Step 4: Write failing structured-log and redaction tests**

Construct a production app and capture one successful request plus a test-only route that raises `RuntimeError("database-password-value")`. Parse each production log line with `json.loads` and assert required fields and stable events. Send an authorization header, JSON body, query string, and a concrete portal-token path; assert none of those values occur in serialized logs and the route template does. Force upload-directory initialization to fail and assert one `startup_failed` record contains the exception type but not its message.

Assert the 500 response remains `{"detail":"Internal server error"}` and includes `X-Request-ID`.

- [ ] **Step 5: Run structured-log tests and observe RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_runtime_http.py -k "logging or redaction or unhandled" -q
```

Expected: logs are plain text and lack required fields/context.

- [ ] **Step 6: Implement logging configuration and formatter**

Create a standard-library `JsonFormatter` that serializes only an allowlist of fields and uses UTC RFC 3339 timestamps. Configure the `simo_os` logger once per app construction without multiplying handlers across tests. Development uses a concise console formatter but retains event and request ID values.

Request completion logs contain `http_request_completed`, `request_id`, method, route template or null, status, and rounded duration. They contain no query/body/header dictionaries.

Call `configure_logging(runtime_settings.app_env)` as the first lifespan action, before upload validation or seeding. Wrap the remaining initialization in `try/except`; emit `startup_failed` with only `exception_type` and `exc_info=True`, then re-raise so the process exits before serving. This establishes the approved startup sequence and makes initialization failures observable without exposing `str(exc)`.

- [ ] **Step 7: Integrate structured error logging**

Change the catch-all handler to emit `unhandled_exception` with `exc_info=True`, `exception_type=type(exc).__name__`, request ID, method, and safe route template. Do not interpolate `str(exc)`. Preserve every existing error response body/status.

Ensure middleware adds `X-Request-ID` even when downstream raises; if Starlette bypasses the normal response path, register a safe outer error boundary or have the exception handler set the header from context. Test ordering determines the minimal correct implementation.

- [ ] **Step 8: Verify Task 5 GREEN and legacy errors**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_runtime_http.py tests/test_health.py tests/test_quotes_api.py -q
```

Expected: request/logging tests pass and existing 400/422/500 contracts remain compatible.

---

### Task 6: Production backend image and startup contract

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Extend: `tests/test_runtime_startup.py` with static container-contract assertions

**Interfaces:**
- Consumes: `python -m app.core.runtime_check`, `app.main:app`, `UPLOAD_DIR`, separate `alembic upgrade head` release command
- Produces: one non-root Python 3.12 OCI image whose default process is Uvicorn only

**Parallelization:** Safe after Task 5; owns Docker files and startup-contract tests only.

- [ ] **Step 1: Write failing static contract tests**

Assert `Dockerfile` and `.dockerignore` exist; Dockerfile contains Python 3.12 slim, a non-root `USER`, port 8000, Uvicorn `app.main:app`, and `/health`; and contains no `alembic upgrade`, `alembic downgrade`, `.env` copy, or seed command. Assert `.dockerignore` includes `.env`, `.git`, `.venv`, `node_modules`, uploads, `.agents`, and `.claude`.

- [ ] **Step 2: Run static tests and observe RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_runtime_startup.py -k docker -q
```

Expected: Docker files are absent.

- [ ] **Step 3: Add minimal production container files**

Use a single-runtime-stage Dockerfile unless measured image/build needs justify a builder. Required shape:

```dockerfile
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 simo
COPY --chown=simo:simo app ./app
COPY --chown=simo:simo alembic ./alembic
COPY --chown=simo:simo alembic.ini ./
USER simo
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Do not add an entrypoint script. The deployment system overrides CMD with `alembic upgrade head` for the one-off release job.

- [ ] **Step 4: Verify static contract GREEN**

Run the focused pytest command from Step 2. Expected: pass.

- [ ] **Step 5: Build and inspect the image**

Run:

```powershell
docker build -t simo-os:sprint-018 .
docker image inspect simo-os:sprint-018
docker run --rm --entrypoint python simo-os:sprint-018 -c "import os; print(os.getuid())"
```

Expected: build succeeds; configured user is non-root and runtime UID is not 0.

- [ ] **Step 6: Prove the default command contains no migration**

Inspect `.Config.Entrypoint` and `.Config.Cmd`; expected command contains only Uvicorn/app binding. Do not start the production container until Task 10 supplies a migrated database and persistent mount.

---

### Task 7: Frontend production API-origin validation

**Files:**
- Create: `apps/web/lib/runtime-config.ts`
- Modify: `apps/web/next.config.ts`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/.env.local.example`

**Interfaces:**
- Consumes: build-time `APP_ENV`, `NEXT_PUBLIC_API_URL`
- Produces: `resolveApiBaseUrl(appEnv, candidate) -> string`, strict production build failure, unchanged local fallback

**Parallelization:** Safe after Task 5; owns frontend-only files.

- [ ] **Step 1: Establish RED build probes**

Run an explicit production-intent build without an API URL:

```powershell
$env:APP_ENV='production'
Remove-Item Env:NEXT_PUBLIC_API_URL -ErrorAction SilentlyContinue
pnpm --filter web build
```

Expected before implementation: build incorrectly succeeds by falling back to loopback. Clear environment variables after each probe.

- [ ] **Step 2: Implement the pure resolver**

Create:

```typescript
export function resolveApiBaseUrl(
  appEnv = process.env.APP_ENV,
  candidate = process.env.NEXT_PUBLIC_API_URL,
): string {
  if (appEnv !== "production") return candidate ?? "http://127.0.0.1:8000";
  if (!candidate) throw new Error("NEXT_PUBLIC_API_URL is required when APP_ENV=production");
  const url = new URL(candidate);
  if (candidate.includes("*") || url.protocol !== "https:" || url.username || url.password || url.pathname !== "/" || url.search || url.hash) {
    throw new Error("NEXT_PUBLIC_API_URL must be an absolute HTTPS origin");
  }
  if (url.hostname === "localhost" || url.hostname === "127.0.0.1" || url.hostname === "::1") {
    throw new Error("NEXT_PUBLIC_API_URL cannot be loopback in production");
  }
  return url.origin;
}
```

Reject `*` through URL parsing/host validation. Do not log the candidate.

- [ ] **Step 3: Wire both build and runtime consumers**

At module evaluation, `apps/web/next.config.ts` calls `resolveApiBaseUrl()` so an invalid production target stops the build. `apps/web/lib/api.ts` exports `API_BASE_URL = resolveApiBaseUrl()` instead of duplicating fallback logic.

- [ ] **Step 4: Verify RED turns GREEN across the matrix**

Run separate builds for:

```text
APP_ENV unset, URL unset                         -> success
APP_ENV=production, URL unset                    -> failure
APP_ENV=production, URL=http://api.example.com   -> failure
APP_ENV=production, URL=https://localhost        -> failure
APP_ENV=production, URL=https://*.example.com    -> failure
APP_ENV=production, URL=https://api.example.com/v1 -> failure
APP_ENV=production, URL=https://api.example.com  -> success
```

Capture non-zero/zero exit codes, not only console strings. Always clear process environment afterward.

- [ ] **Step 5: Document and verify frontend configuration**

Update `apps/web/.env.local.example` with local defaults and production examples. Run:

```powershell
pnpm lint
pnpm check-types
$env:APP_ENV='production'; $env:NEXT_PUBLIC_API_URL='https://api.example.com'; pnpm build
Remove-Item Env:APP_ENV; Remove-Item Env:NEXT_PUBLIC_API_URL
```

Expected: lint, available type checks, and strict production build pass.

---

### Task 8: Production runbook and canonical documentation

**Files:**
- Create: `docs/PRODUCTION_RUNBOOK.md`
- Modify: `docs/DECISIONS.md`
- Modify: `docs/SYSTEM_ARCHITECTURE.md`
- Modify: `docs/API_SPEC.md`
- Modify: `docs/CHANGELOG.md`
- Do not modify: `docs/ROADMAP.md`

**Interfaces:**
- Consumes: verified commands, settings names, health response bodies, container command, migration head from Tasks 1–7
- Produces: operator-ready release/rollback contract and ADR-034

**Parallelization:** Safe after Task 5 for drafting, but final command/output details must be reconciled after Tasks 6–7 verification.

- [ ] **Step 1: Write the runbook with exact release gates**

Include the normative sequence verbatim in operational form:

```text
1. Mount persistent UPLOAD_DIR and supply production environment.
2. python -m app.core.runtime_check
3. alembic upgrade head          # one-off release job only
4. alembic current; alembic heads; confirm the same sole head
5. start/restart Uvicorn containers
6. GET /health -> 200
7. GET /ready -> 200
8. authenticated API smoke test + upload/restart/download persistence test
9. promote traffic
```

State that any failure blocks promotion. Include environment inventory without secret values, volume ownership/backup/restore prerequisites, one-instance/shared-filesystem limitation, and exact interpretations for health combinations.

- [ ] **Step 2: Document application rollback separately**

State that application rollback deploys the previous image without changing the database and is permitted only when that image is schema-compatible. Include stop conditions and verification commands.

- [ ] **Step 3: Document explicit database downgrade policy**

State that no automated downgrade exists. An operator may run `alembic downgrade -1` only after confirming the exact migration is safely reversible, stopping incompatible writers, accepting data implications, and verifying a current restorable backup. Prefer forward fix or schema-compatible app rollback.

- [ ] **Step 4: Add ADR-034 and update architecture/API/changelog**

ADR-034 records: explicit environment mode, strict production validation, no production seeding, migration-as-release-job, liveness/readiness split, JSON/request-ID logging, non-root provider-neutral container, and persistent-volume constraint. API docs preserve `/health`, add `/ready`, and document `X-Request-ID` without changing JSON errors. Architecture reflects lifespan/import safety and container boundaries. Changelog describes user/operator impact.

- [ ] **Step 5: Verify documentation consistency and ROADMAP exclusion**

Run:

```powershell
rg -n "alembic upgrade head|/health|/ready|APP_ENV|SEED_DATA_ENABLED|UPLOAD_DIR|X-Request-ID" docs/PRODUCTION_RUNBOOK.md docs/DECISIONS.md docs/SYSTEM_ARCHITECTURE.md docs/API_SPEC.md
git diff -- docs/ROADMAP.md
```

Expected: all contracts are present and ROADMAP diff is empty.

---

### Task 9: Integrated Sprint 018 automated regression gates

**Files:**
- Consolidate: `tests/test_runtime_config.py`
- Consolidate: `tests/test_runtime_startup.py`
- Consolidate: `tests/test_runtime_http.py`
- Create after actual verification: `docs/SPRINTS/sprint-018.md`

**Interfaces:**
- Consumes: all Sprint 018 implementation contracts
- Produces: one deterministic targeted suite and recorded actual completion evidence

- [ ] **Step 1: Run the entire targeted Sprint 018 suite**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_runtime_config.py tests/test_runtime_startup.py tests/test_runtime_http.py -q
```

Expected: all targeted tests pass with no network dependency and no sleep-based timeout test.

- [ ] **Step 2: Prove production configuration failures in subprocesses**

Execute `python -m app.core.runtime_check` separately for unsafe JWT, default seed credentials, enabled seeding, wildcard CORS, local database URL, and relative upload path. Expected: each exits non-zero, names the violated setting, and emits no supplied secret.

- [ ] **Step 3: Prove development compatibility**

With `APP_ENV=development`, start `TestClient` through lifespan, authenticate with the configured development seed owner, call `/health`, `/ready`, and one existing protected route. Expected: seed-backed development workflow remains usable and existing API shape is unchanged.

- [ ] **Step 4: Run the full backend suite**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```

Expected: zero failures. Investigate only genuine Sprint 018 regressions using systematic debugging and TDD; do not broaden scope.

- [ ] **Step 5: Run migration verification without changing startup policy**

Run:

```powershell
.venv\Scripts\alembic.exe current
.venv\Scripts\alembic.exe heads
.venv\Scripts\alembic.exe check
```

Expected: current equals the sole head and check reports no new upgrade operations. Run the standard downgrade-one/upgrade-head round trip only against the approved local test database, then reconfirm head. This operator command is verification; no application/container startup invokes it.

- [ ] **Step 6: Run frontend verification**

Run lint, workspace type check, ordinary build, strict production failure matrix, and strict safe production build. Record exact task counts, routes, warnings, and exit codes.

- [ ] **Step 7: Create the completion record from evidence**

Only after Steps 1–6 pass, create `docs/SPRINTS/sprint-018.md` with delivered scope, exact test counts, migration/head result, frontend and container output, security findings, known limitations, and follow-ups. Do not claim unrun checks.

---

### Task 10: Parallel final production-readiness verification

**Files:**
- Read-only verification; agents must not edit files

**Interfaces:**
- Consumes: complete uncommitted Sprint 018 working tree
- Produces: four independent evidence reports for the final gate

**Parallelization:** Use `superpowers:dispatching-parallel-agents` after Task 9. With the four-slot limit, dispatch Agents A–C concurrently while the primary agent performs Audit D in parallel; forbid all verification streams from editing code or docs.

- [ ] **Agent A — Backend/configuration verification**

Run targeted Sprint 018 tests and full pytest. Independently exercise the unsafe-production subprocess matrix, development-mode compatibility, seed suppression, import safety, CORS, `/health`, `/ready`, request-ID, logging format, and redaction. Report exact pass/fail/warning counts and genuine defects only.

- [ ] **Agent B — Database/container verification**

Run Alembic current, heads, check, approved local downgrade-one/upgrade-head round trip, and final head confirmation. Build `simo-os:sprint-018`; inspect non-root UID and CMD/entrypoint; run the one-off migration command; start the default container against migrated PostgreSQL and a mounted temporary upload directory; verify `/health` and `/ready`; restart the container and verify a marker file persists. Confirm no startup migration/seed invocation.

- [ ] **Agent C — Frontend verification**

Run `pnpm lint`, `pnpm check-types`, ordinary `pnpm build`, all unsafe production URL build probes, and the safe HTTPS production build. Report exact outcomes and confirm the default remains loopback only outside explicit production intent.

- [ ] **Agent D — Security/configuration/scope audit**

Inspect secret redaction, Pydantic hidden inputs, CORS parsing, request-ID validation/context cleanup, route-template logging, readiness information exposure, production seed suppression, non-root/container exclusions, persistent-volume contract, and migration separation. Run `git diff --check`, `git status --short`, `git diff -- docs/ROADMAP.md`, and list every changed file. Confirm no hosting, S3, malware, quota, email, billing, rate-limit, WebSocket/SSE, APM, roadmap, Sprint 017, or Sprint 019 scope entered.

- [ ] **Step 5: If and only if a real defect exists, repair narrowly**

Use `superpowers:systematic-debugging`, write one failing regression test, observe RED, make the smallest spec-conformant change, observe GREEN, then rerun the affected targeted test followed by Tasks 9 and 10 as required. Documentation-only output discrepancies do not authorize product redesign.

---

### Task 11: Final verification-before-completion gate

**Files:**
- Read all changed files and verification reports
- Modify only `docs/SPRINTS/sprint-018.md` if actual evidence needs correction

**Interfaces:**
- Consumes: Agent A–D outputs and local command evidence
- Produces: final user-facing Sprint 018 release report; no commit or push without approval

- [ ] **Step 1: Invoke `superpowers:verification-before-completion`**

Independently verify every claimed output from raw command results. Do not summarize an agent's assertion as passed unless the command, exit code, and relevant count/output are present.

- [ ] **Step 2: Reconcile the acceptance checklist**

Confirm all 14 spec acceptance criteria map to passing evidence. Explicitly record:

```text
targeted Sprint 018 tests
full pytest count/warnings/failures
Alembic current/sole head/check/round trip
unsafe production config matrix
development compatibility
CORS allowed/denied behavior
liveness/readiness 200/503 behavior
request-ID/logging/redaction behavior
frontend lint/type/ordinary build/strict production build
Docker build/non-root/default CMD/release command/startup smoke
persistent-volume restart result
git diff --check
security/configuration audit
scope-creep audit and ROADMAP exclusion
```

- [ ] **Step 3: Inspect final repository scope**

Run:

```powershell
git status --short
git diff --name-only
git diff --check
git diff -- docs/ROADMAP.md
git diff -- Dockerfile .dockerignore app apps/web tests docs
```

Expected: only approved Sprint 018 files plus excluded `.agents/`/`.claude/`; ROADMAP untouched; no generated image/build/upload/test artifacts tracked.

- [ ] **Step 4: Report and stop**

Report exact changed files, tests, migrations, frontend, container, health, logging, security, volume, scope, warnings, blockers, and git status. Do not commit or push. Wait for explicit approval.

## Expected execution checkpoints

1. **Sequential foundation:** Tasks 0–5.
2. **Parallel implementation wave:** Tasks 6, 7, and 8 after Task 5, using separate agents only if each receives exclusive file ownership and the approved design/this plan.
3. **Sequential integration:** Task 9 after merging the parallel wave into the shared working tree.
4. **Parallel read-only verification:** Task 10 Agents A–D.
5. **Sequential release gate:** Task 11.

No agent may modify `.agents/`, `.claude/`, `docs/ROADMAP.md`, Sprint 017 implementation, or any out-of-scope subsystem.

## Plan self-review against the approved design

| Approved design section | Implementation coverage |
|---|---|
| §1 Context / §2 Goals | Global constraints, file map, Tasks 1–11 |
| §3 Non-goals | Global exclusions; Agent D and Task 11 scope audits |
| §4 Selected approach | Existing-stack modules in file map; no vendor/APM dependency |
| §5 Runtime/configuration | Task 1 production matrix, sanitized CLI, `.env.example` |
| §5.4 Seed policy | Task 2 injected seeder tests and production suppression |
| §6 Startup lifecycle | Task 2 app factory/lifespan/import safety; Task 5 logging-first startup failure |
| §7 CORS | Task 3 real allowed/denied preflight tests |
| §8 Health | Task 4 exact `/health` and `/ready` contracts and two-second bound |
| §9 Logging/request IDs | Task 5 JSON schema, stable events, context cleanup, route-template redaction |
| §10 Backend container | Task 6 non-root image, Uvicorn-only CMD, liveness health check |
| §11 Frontend URL | Task 7 pure validator and six-case strict build matrix |
| §12 Upload volume | Tasks 2, 6, 8, and 10 mount/startup/restart-persistence checks |
| §13 Release/rollback | Task 8 exact one-off migration order and separate downgrade policy |
| §14 Testing | Tests embedded red/green in Tasks 1–7; integrated Task 9; parallel Task 10 |
| §15 Documentation | Task 8 canonical docs; Task 9 evidence-based sprint record |
| §16 Security/isolation | Task 5 redaction; Agent D audit; no auth/tenant feature changes |
| §17 Acceptance criteria | Tasks 9–11 evidence checklist and final verification gate |

Self-review result: every approved section has an owning task and verification gate. Interface names are consistent across producers/consumers. Placeholder scan is clean. The plan introduces no design discrepancy; it only makes execution details concrete, including `ADR-034`, `docs/PRODUCTION_RUNBOOK.md`, the app-factory seams, and the four-stream verification allocation.
