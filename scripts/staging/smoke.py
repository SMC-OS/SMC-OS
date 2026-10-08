"""Secret-safe, operator-run Sprint 019 staging smoke harness.

No HTTP request is made at import time. A real run creates fresh synthetic
records only, keeps credentials in memory, and writes sanitized evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx


SMOKE_GATES = (
    "https_reachability", "liveness", "readiness", "postgresql", "migration",
    "no_seeding", "signup_login_auth", "customer", "project", "quote_invoice",
    "staff_document", "restart_persistence", "portal_token", "portal_documents",
    "portal_messaging", "token_enforcement", "tenant_isolation",
    # Sprint 027 (docs/SPRINTS/sprint-027.md §6.9/§8) — this smoke matrix
    # was Sprint 019-vintage and never exercised Sprints 020-025's own
    # journeys (quote approve/handoff had *no* staging smoke coverage at
    # all before this). Additive only — every gate above is unchanged.
    "quote_approve_handoff", "appointment", "project_assignment_status",
    "follow_up_notification", "command_centre",
    "cors_allowed",
    "cors_denied", "logs_request_ids", "repository_secret_scan", "backup_restore",
)
SENSITIVE_KEY = re.compile(r"(?:authorization|token|password|secret|email|database|credential)", re.I)
DEFAULT_TIMEOUT_SECONDS = 15.0


class SmokeHttpError(Exception):
    def __init__(self, method: str, route: str, status_code: int) -> None:
        self.method, self.route, self.status_code = method, route, status_code


class FixtureVerificationError(Exception):
    """The operator fixture could not verify the run's synthetic users."""


_ID_SEGMENT = re.compile(r"^(?:[0-9a-fA-F-]{32,36}|[A-Za-z0-9_-]{20,})$")


def safe_route(path: str) -> str:
    """A route fit for a report: no query string, and every id / portal token
    segment replaced, so evidence never carries a credential or a record id."""
    segments = path.split("?", 1)[0].split("/")
    return "/".join("{id}" if _ID_SEGMENT.match(segment) else segment for segment in segments)


def validate_public_https_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
        or parsed.path not in ("", "/") or parsed.query or parsed.fragment
        or parsed.hostname.lower() == "localhost" or parsed.hostname.startswith("127.")
        or parsed.hostname == "::1"
    ):
        raise ValueError("origin must be a non-loopback HTTPS origin without credentials or a path")
    return f"https://{parsed.netloc}"


def redact_value(value: str) -> str:
    value = re.sub(r"(?i)(authorization:\s*bearer\s+)[^\s]+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)\b(token|password|secret|database_url|email)=[^\s]+", r"\1=[REDACTED]", value)
    return re.sub(r"(postgres(?:ql)?://)[^\s@]+@", r"\1[REDACTED]@", value, flags=re.I)


def sanitize_evidence(value: Any) -> Any:
    """Recursively remove credentials and PII before terminal/report output."""
    if isinstance(value, dict):
        return {str(k): "[REDACTED]" if SENSITIVE_KEY.search(str(k)) else sanitize_evidence(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_evidence(item) for item in value]
    return redact_value(value) if isinstance(value, str) else value


class SmokeRunner:
    def __init__(self, web_url: str, api_url: str, *, allow_restart: bool, timeout: float, quote_material: str | None = None, quote_thickness: str | None = None, fixture_verifier: Callable[[str], None] | None = None) -> None:
        self.web_url = validate_public_https_origin(web_url)
        self.api_url = validate_public_https_origin(api_url)
        self.allow_restart, self.timeout = allow_restart, timeout
        self.quote_material, self.quote_thickness = quote_material, quote_thickness
        # Marks this run's own synthetic users verified (see
        # app/core/staging_fixture.py). Never a public API: staging's database
        # is private, so it is reached by an operator command next to it.
        self.fixture_verifier = fixture_verifier
        self.prefix = f"s019-{uuid.uuid4().hex[:12]}"
        self.results: list[dict[str, Any]] = []
        self.created: list[dict[str, str]] = []
        self.state: dict[str, Any] = {}

    def add(self, gate_name: str, result: str, **evidence: Any) -> None:
        normalized = {
            f"observed_{key}" if key in {"name", "status"} else key: value
            for key, value in evidence.items()
        }
        self.results.append({"name": gate_name, "status": result, "evidence": sanitize_evidence(normalized)})

    def blocked(self, name: str, reason: str) -> None:
        self.add(name, "BLOCKED", reason=reason)

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = self.client.request(method, f"{self.api_url}{path}", timeout=self.timeout, follow_redirects=False, **kwargs)
        if response.is_error:
            # Keep only the status code and a redacted route: raise_for_status()
            # collapsed every failure into an opaque HTTPStatusError, and its
            # message embeds the full URL (ids, portal tokens, query strings).
            raise SmokeHttpError(method, safe_route(path), response.status_code)
        return response

    def headers(self, tenant: str = "a") -> dict[str, str]:
        return {"Authorization": f"Bearer {self.state[f'{tenant}_token']}"}

    def workspace_gate(self, name: str, action: Callable[[], dict[str, Any]], *, requires: tuple[str, ...] = ()) -> None:
        """A gate that drives authenticated workspace routes.

        Those routes are refused to an unverified user by design, so without
        the operator fixture the gate is BLOCKED (not FAILED). And a gate
        whose prerequisite record an earlier gate never created is BLOCKED
        too, naming what is missing: the failing upstream gate stays the one
        visible root cause instead of a trail of unrelated KeyError failures."""
        if not self.state.get("fixture_verified", False):
            self.blocked(name, "requires operator fixture email verification: signup users are correctly unverified, so workspace routes are refused")
            return
        missing = [key for key in requires if key not in self.state]
        if missing:
            self.blocked(name, f"prerequisite not created by an earlier gate: {', '.join(missing)}")
            return
        self.gate(name, action)

    def gate(self, name: str, action: Callable[[], dict[str, Any]]) -> None:
        try:
            evidence = action()
            failed_assertion = next((key for key, value in evidence.items() if value is False), None)
            if failed_assertion is not None:
                self.add(name, "FAIL", assertion_failed=failed_assertion)
                return
            self.add(name, "PASS", **evidence)
        except SmokeHttpError as exc:
            self.add(name, "FAIL", method=exc.method, route=exc.route, status_code=exc.status_code)
        except Exception as exc:
            self.add(name, "FAIL", error_type=type(exc).__name__)

    def signup(self, tenant: str) -> dict[str, Any]:
        email, password = f"{self.prefix}-{tenant}@example.invalid", f"S019-{uuid.uuid4().hex}!"
        signup = self.request("POST", "/api/v1/auth/signup", json={"company_name": f"{self.prefix}-{tenant}", "name": "Synthetic Operator", "email": email, "password": password})
        login = self.request("POST", "/api/v1/auth/login", json={"email": email, "password": password}).json()
        self.state[f"{tenant}_token"] = login["access_token"]
        # Sprint 027 — needed by project_assignment_status, which
        # self-assigns the synthetic Owner (no second Staff account is
        # created by this harness, keeping its footprint minimal).
        self.state[f"{tenant}_user_id"] = login["user"]["id"]
        self.created.append({"kind": "tenant_user", "synthetic_prefix": self.prefix, "tenant": tenant})
        # A fresh signup is unverified, and the product must refuse it
        # workspace data until it verifies (require_verified_email).
        unverified = self.client.get(f"{self.api_url}/api/v1/customers", headers=self.headers(tenant), timeout=self.timeout)
        return {
            "signup_status": signup.status_code,
            "login_token_received": bool(login.get("access_token")),
            "unverified_status_code": unverified.status_code,
            "unverified_access_rejected": unverified.status_code == 403,
        }

    def signup_and_prepare(self) -> dict[str, Any]:
        """Sign up both synthetic workspaces, prove each is refused while
        unverified, then (only with the operator fixture) verify them and
        prove the real no-card trial is untouched and access now works."""
        first, second = self.signup("a"), self.signup("b")
        evidence: dict[str, Any] = {
            "signup_status": second["signup_status"],
            "login_token_received": second["login_token_received"],
            "unverified_status_code": second["unverified_status_code"],
            "unverified_access_rejected": first["unverified_access_rejected"] and second["unverified_access_rejected"],
        }
        if self.fixture_verifier is None:
            evidence["fixture_verification"] = "unavailable"
            return evidence
        try:
            self.fixture_verifier(self.prefix)
        except FixtureVerificationError:
            return {**evidence, "fixture_verification": "failed", "fixture_verified": False}
        self.state["fixture_verified"] = True
        evidence["fixture_verification"] = "applied"
        statuses, trials = [], []
        for tenant in ("a", "b"):
            access = self.client.get(f"{self.api_url}/api/v1/customers", headers=self.headers(tenant), timeout=self.timeout)
            subscription = self.client.get(f"{self.api_url}/api/v1/billing/subscription", headers=self.headers(tenant), timeout=self.timeout)
            body = subscription.json() if subscription.status_code == 200 and subscription.content else None
            statuses.append(access.status_code)
            # The no-card trial signup started, as-is: still trialing, with real
            # trial dates, and never swapped for a grandfathered/paid exemption.
            trials.append(bool(body) and body.get("status") == "trialing" and body.get("trial_state") in {"active", "ending_soon"} and bool(body.get("trial_start")) and bool(body.get("trial_end")))
        evidence["verified_access_status_codes"] = statuses
        evidence["verified_access_allowed"] = all(code == 200 for code in statuses)
        evidence["trial_retained"] = all(trials)
        return evidence

    def customer(self) -> dict[str, Any]:
        row = self.request("POST", "/api/v1/customers", headers=self.headers(), json={"name": f"{self.prefix}-customer"}).json()
        self.state["customer_id"] = row["id"]
        self.created.append({"kind": "customer", "id": row["id"]})
        read = self.request("GET", f"/api/v1/customers/{row['id']}", headers=self.headers()).json()
        return {"created": bool(row.get("id")), "read_matches": read.get("id") == row["id"]}

    def project(self) -> dict[str, Any]:
        row = self.request("POST", "/api/v1/projects", headers=self.headers(), json={"name": f"{self.prefix}-project", "customer_id": self.state["customer_id"]}).json()
        self.state["project_id"] = row["id"]
        self.created.append({"kind": "project", "id": row["id"]})
        return {"created": bool(row.get("id")), "status": row.get("status")}

    def quote_invoice(self) -> dict[str, Any]:
        quote = self.request("POST", "/api/v1/quote", headers=self.headers(), json={"customer": f"{self.prefix}-customer", "customer_id": self.state["customer_id"], "material": self.quote_material, "thickness": self.quote_thickness, "kitchen_length": 2.0}).json()
        self.state["quote_id"] = quote["id"]
        invoice = self.request("GET", f"/api/v1/quotes/{quote['id']}/invoice", headers=self.headers())
        return {"quote_created": bool(quote.get("id")), "invoice_pdf": invoice.headers.get("content-type", "").startswith("application/pdf")}

    def document(self) -> dict[str, Any]:
        content = f"{self.prefix}-document".encode()
        uploaded = self.request("POST", f"/api/v1/documents?customer_id={self.state['customer_id']}", headers=self.headers(), files={"file": ("smoke.txt", content, "text/plain")}).json()
        self.state["document_id"], self.state["document_hash"] = uploaded["id"], hashlib.sha256(content).hexdigest()
        self.created.append({"kind": "document", "id": uploaded["id"]})
        download = self.request("GET", f"/api/v1/documents/{uploaded['id']}/download", headers=self.headers())
        return {"uploaded": bool(uploaded.get("id")), "download_hash_matches": hashlib.sha256(download.content).hexdigest() == self.state["document_hash"]}

    def portal(self) -> dict[str, Any]:
        link = self.request("POST", "/api/v1/portal-links", headers=self.headers(), json={"customer_id": self.state["customer_id"]}).json()
        self.state["portal_id"], self.state["portal_token"] = link["id"], link["token"]
        self.created.append({"kind": "portal_link", "id": link["id"]})
        view = self.request("GET", f"/api/v1/portal-links/token/{link['token']}").json()
        return {"active": view.get("status") == "active"}

    def portal_documents(self) -> dict[str, Any]:
        token, document_id = self.state["portal_token"], self.state["document_id"]
        rows = self.request("GET", f"/api/v1/portal-links/token/{token}/documents").json()
        download = self.request("GET", f"/api/v1/portal-links/token/{token}/documents/{document_id}/download")
        return {"document_listed": any(row.get("id") == document_id for row in rows), "download_hash_matches": hashlib.sha256(download.content).hexdigest() == self.state["document_hash"]}

    def portal_messages(self) -> dict[str, Any]:
        token = self.state["portal_token"]
        customer = self.request("POST", f"/api/v1/portal-links/token/{token}/messages", json={"body": "Synthetic customer message"}).json()
        staff = self.request("POST", f"/api/v1/messages?customer_id={self.state['customer_id']}", headers=self.headers(), json={"body": "Synthetic staff message"}).json()
        rows = self.request("GET", f"/api/v1/portal-links/token/{token}/messages").json()
        return {"customer_sender": customer.get("sender_type"), "staff_sender": staff.get("sender_type"), "chronological": [row["created_at"] for row in rows] == sorted(row["created_at"] for row in rows)}

    def token_enforcement(self) -> dict[str, Any]:
        self.request("DELETE", f"/api/v1/portal-links/{self.state['portal_id']}", headers=self.headers())
        response = self.client.get(f"{self.api_url}/api/v1/portal-links/token/{self.state['portal_token']}", timeout=self.timeout)
        body = response.json() if response.status_code == 200 else {}
        documents = self.client.get(f"{self.api_url}/api/v1/portal-links/token/{self.state['portal_token']}/documents", timeout=self.timeout)
        messages = self.client.get(f"{self.api_url}/api/v1/portal-links/token/{self.state['portal_token']}/messages", timeout=self.timeout)
        return {"status_code": response.status_code, "revoked": body.get("status") == "revoked", "documents_rejected": documents.status_code == 404, "messages_rejected": messages.status_code == 404}

    def tenant_isolation(self) -> dict[str, Any]:
        if "quote_id" not in self.state:
            raise KeyError("quote prerequisite unavailable")
        protected = ("customers", "projects", "quotes")
        ids = (self.state["customer_id"], self.state["project_id"], self.state["quote_id"])
        responses = [self.client.get(f"{self.api_url}/api/v1/{kind}/{item_id}", headers=self.headers("b"), timeout=self.timeout) for kind, item_id in zip(protected, ids, strict=True)]
        return {"checks": len(responses), "all_not_found": all(item.status_code == 404 for item in responses)}

    # Sprint 027 (docs/SPRINTS/sprint-027.md §6.9/§7/§8) — additive gates
    # covering Sprints 020, 022, 023, 025's own journeys, none of which
    # this Sprint-019-vintage harness ever exercised in staging before.

    def quote_approve_handoff(self) -> dict[str, Any]:
        """Sprint 020's own objective had zero staging smoke coverage
        before this: quote_invoice only ever created + invoiced a quote,
        never approved or handed it off."""
        quote_id = self.state["quote_id"]
        approved = self.request("POST", f"/api/v1/quotes/{quote_id}/approve", headers=self.headers()).json()
        project = self.request("POST", f"/api/v1/quotes/{quote_id}/handoff", headers=self.headers()).json()
        self.state["booked_project_id"] = project["id"]
        return {
            "approved": approved.get("status") == "approved",
            "handed_off_status": project.get("status"),
        }

    def appointment(self) -> dict[str, Any]:
        """Sprint 022 — schedule and complete a site visit against the
        Project created earlier this run (not the quote-handoff Project;
        appointments attach to any Project, and this keeps the gate
        independent of whether quote_approve_handoff ran)."""
        project_id = self.state["project_id"]
        scheduled_at = f"{datetime.now(timezone.utc).isoformat()}"
        created = self.request(
            "POST",
            f"/api/v1/projects/{project_id}/appointments",
            headers=self.headers(),
            json={"scheduled_at": scheduled_at},
        ).json()
        self.state["appointment_id"] = created["id"]
        completed = self.request(
            "PATCH",
            f"/api/v1/appointments/{created['id']}/status",
            headers=self.headers(),
            json={"status": "completed"},
        ).json()
        return {"created": bool(created.get("id")), "completed_status": completed.get("status")}

    def project_assignment_status(self) -> dict[str, Any]:
        """Sprint 023 — Owner self-assigns (no second Staff account exists
        in this harness) then advances the booked-from-handoff Project one
        real step. Depends on quote_approve_handoff having run; blocked
        otherwise rather than silently skipped."""
        if "booked_project_id" not in self.state:
            raise KeyError("booked project prerequisite unavailable")
        project_id = self.state["booked_project_id"]
        assigned = self.request(
            "PATCH",
            f"/api/v1/projects/{project_id}/assign",
            headers=self.headers(),
            json={"assigned_user_id": self.state["a_user_id"]},
        ).json()
        advanced = self.request(
            "PATCH",
            f"/api/v1/projects/{project_id}/status",
            headers=self.headers(),
            json={"status": "templated"},
        ).json()
        return {
            "assigned_user_id_matches": assigned.get("assigned_user_id") == self.state["a_user_id"],
            "advanced_status": advanced.get("status"),
        }

    def command_centre(self) -> dict[str, Any]:
        """Sprint 025 — light shape check only (not exact values, unlike
        the local Playwright suite's controlled dataset): staging carries
        real accumulated synthetic data across smoke runs, so this gate
        proves the endpoint is reachable and RBAC-gated, not specific
        numbers."""
        response = self.request("GET", "/api/v1/dashboard/command-centre", headers=self.headers())
        body = response.json()
        expected_keys = {"customers", "pipeline", "quotes", "value", "site_visits", "follow_up"}
        return {"status_code": response.status_code, "has_expected_shape": expected_keys.issubset(body.keys())}

    def cors(self, allowed: bool) -> dict[str, Any]:
        origin = self.web_url if allowed else "https://untrusted.example.invalid"
        response = self.client.options(f"{self.api_url}/api/v1/customers", headers={"Origin": origin, "Access-Control-Request-Method": "GET"}, timeout=self.timeout)
        actual = response.headers.get("access-control-allow-origin")
        return {"status_code": response.status_code, "origin_contract": actual == self.web_url if allowed else actual is None}

    def health(self, path: str, expected: dict[str, str]) -> dict[str, Any]:
        response = self.client.get(f"{self.api_url}{path}", timeout=self.timeout)
        # Sprint 027 — evidence that Sprint 026's hardening headers
        # (SecurityHeadersMiddleware, app/core/middleware.py) are actually
        # present in staging, without tripping the real login rate limiter
        # by making an authentication attempt on every smoke run.
        hardening_headers_present = all(
            response.headers.get(header) for header in
            ("x-content-type-options", "x-frame-options", "referrer-policy")
        )
        return {
            "status_code": response.status_code,
            "body_matches": response.json() == expected,
            "request_id_present": bool(response.headers.get("x-request-id")),
            "hardening_headers_present": hardening_headers_present,
        }

    def https(self) -> dict[str, Any]:
        web = self.client.get(self.web_url, timeout=self.timeout, follow_redirects=False)
        api = self.client.get(f"{self.api_url}/health", timeout=self.timeout)
        return {"web_status": web.status_code, "api_status": api.status_code}

    def run(self, *, dry_run: bool = False) -> dict[str, Any]:
        if dry_run:
            for name in SMOKE_GATES:
                self.blocked(name, "dry-run: no staging request was made")
            return self.report()
        with httpx.Client() as self.client:
            self.gate("https_reachability", self.https)
            self.gate("liveness", lambda: self.health("/health", {"status": "healthy"}))
            self.gate("readiness", lambda: self.health("/ready", {"status": "ready", "database": "reachable"}))
            self.gate("postgresql", lambda: self.health("/ready", {"status": "ready", "database": "reachable"}))
            self.blocked("migration", "requires separately recorded remote alembic current evidence")
            self.blocked("no_seeding", "requires operator comparison against a known seed inventory")
            self.gate("signup_login_auth", self.signup_and_prepare)
            self.workspace_gate("customer", self.customer)
            self.workspace_gate("project", self.project, requires=("customer_id",))
            if self.quote_material and self.quote_thickness:
                self.workspace_gate("quote_invoice", self.quote_invoice, requires=("customer_id",))
            else:
                self.blocked("quote_invoice", "requires --quote-material and --quote-thickness")
            for name, action, needs in (
                ("staff_document", self.document, ("customer_id",)),
                ("portal_token", self.portal, ("customer_id",)),
                ("portal_documents", self.portal_documents, ("portal_token", "document_id")),
                ("portal_messaging", self.portal_messages, ("portal_token", "customer_id")),
                ("token_enforcement", self.token_enforcement, ("portal_id", "portal_token")),
            ):
                self.workspace_gate(name, action, requires=needs)
            if self.quote_material and self.quote_thickness:
                self.workspace_gate("tenant_isolation", self.tenant_isolation, requires=("customer_id", "project_id", "quote_id"))
            else:
                self.blocked("tenant_isolation", "partial customer/project checks cannot satisfy full quote isolation coverage")
            # Sprint 027 — see SmokeRunner.quote_approve_handoff/appointment/
            # project_assignment_status/command_centre docstrings above.
            if self.quote_material and self.quote_thickness:
                self.workspace_gate("quote_approve_handoff", self.quote_approve_handoff, requires=("quote_id",))
            else:
                self.blocked("quote_approve_handoff", "requires --quote-material and --quote-thickness")
            self.workspace_gate("appointment", self.appointment, requires=("project_id",))
            self.workspace_gate("project_assignment_status", self.project_assignment_status, requires=("booked_project_id", "a_user_id"))
            self.blocked(
                "follow_up_notification",
                "no HTTP trigger exists by design (app/jobs/follow_up.py is a "
                "CLI-only entrypoint, docs/SPRINTS/sprint-024.md §7/§9/§11); "
                "verify separately via `railway ssh` running "
                "`python -m app.jobs.follow_up`, per docs/SPRINTS/sprint-027.md §6",
            )
            self.workspace_gate("command_centre", self.command_centre)
            for name, action in (("cors_allowed", lambda: self.cors(True)), ("cors_denied", lambda: self.cors(False))):
                self.gate(name, action)
            self.blocked("restart_persistence", "requires a configured bounded API-only Railway restart command" if self.allow_restart else "requires --allow-restart and a configured bounded API-only Railway restart command")
            self.blocked("logs_request_ids", "no approved safe test-only unhandled-failure mechanism")
            self.blocked("repository_secret_scan", "must be run locally against tracked repository files")
            self.blocked("backup_restore", "requires separately approved destructive-risk restore drill")
        return self.report()

    def report(self) -> dict[str, Any]:
        totals = {"passed": 0, "failed": 0, "blocked": 0}
        for result in self.results:
            totals[{"PASS": "passed", "FAIL": "failed", "BLOCKED": "blocked"}[result["status"]]] += 1
        return sanitize_evidence({"run_id": self.prefix, "started_at": datetime.now(timezone.utc).isoformat(), "web_url": self.web_url, "api_url": self.api_url, "gates": self.results, "totals": totals, "synthetic_cleanup": {"created": self.created, "status": "tracked; API deletion is unavailable for all created records"}})


_RAILWAY_ARGUMENT = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_RUN_PREFIX = re.compile(r"^s019-[0-9a-f]{12}$")
FIXTURE_TIMEOUT_SECONDS = 180


def railway_fixture_verifier(project_id: str, service: str, api_url: str) -> Callable[[str], None]:
    """An operator-only way to mark this run's synthetic users verified.

    Runs `python -m app.core.staging_fixture` inside the staging API
    container over `railway ssh`. The environment is hard-coded to
    "staging" (it cannot be pointed anywhere else), the API origin must be a
    staging host, and the container-side module independently refuses
    unless Railway reports its own environment as "staging"."""
    if not _RAILWAY_ARGUMENT.match(project_id) or not _RAILWAY_ARGUMENT.match(service):
        raise ValueError("railway project and service must be plain identifiers")
    if "staging" not in (urlsplit(api_url).hostname or ""):
        raise ValueError("fixture verification is only allowed against a staging API origin")
    railway = shutil.which("railway")
    if railway is None:
        raise ValueError("the railway CLI is required for fixture verification")

    def verify(run_prefix: str) -> None:
        if not _RUN_PREFIX.match(run_prefix):
            raise FixtureVerificationError("not a smoke run prefix")
        command = [railway, "ssh", "--project", project_id, "--environment", "staging", "--service", service, "--",
                   "python", "-m", "app.core.staging_fixture", "verify-email", "--run-prefix", run_prefix]
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=FIXTURE_TIMEOUT_SECONDS, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise FixtureVerificationError(type(exc).__name__) from None
        if done.returncode != 0:
            raise FixtureVerificationError(f"fixture command exited {done.returncode}")

    return verify


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the secret-safe Sprint 019 staging smoke matrix.")
    parser.add_argument("--web-url", required=True, help="Public HTTPS web origin (no path).")
    parser.add_argument("--api-url", required=True, help="Public HTTPS API origin (no path).")
    parser.add_argument("--dry-run", action="store_true", help="Write all 22 gates as BLOCKED without network activity.")
    parser.add_argument("--json-report", type=Path, required=True, help="Destination for sanitized JSON evidence.")
    parser.add_argument("--allow-restart", action="store_true", help="Opt in to a bounded API-only restart if configured.")
    parser.add_argument("--quote-material", help="Existing staging catalog material for quote verification.")
    parser.add_argument("--quote-thickness", help="Matching existing staging catalog thickness.")
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="Per-request timeout (1-60 seconds).")
    parser.add_argument("--fixture-verify-railway-project", help="Railway project id: lets the run verify its own synthetic users inside the STAGING API container (environment is fixed to 'staging').")
    parser.add_argument("--fixture-verify-railway-service", help="Railway staging API service name or id (with --fixture-verify-railway-project).")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not 1 <= args.timeout_seconds <= 60:
        parser.error("--timeout-seconds must be between 1 and 60")
    if bool(args.quote_material) != bool(args.quote_thickness):
        parser.error("--quote-material and --quote-thickness must be supplied together")
    if bool(args.fixture_verify_railway_project) != bool(args.fixture_verify_railway_service):
        parser.error("--fixture-verify-railway-project and --fixture-verify-railway-service must be supplied together")
    try:
        verifier = railway_fixture_verifier(args.fixture_verify_railway_project, args.fixture_verify_railway_service, args.api_url) if args.fixture_verify_railway_project and not args.dry_run else None
        runner = SmokeRunner(args.web_url, args.api_url, allow_restart=args.allow_restart, timeout=args.timeout_seconds, quote_material=args.quote_material, quote_thickness=args.quote_thickness, fixture_verifier=verifier)
    except ValueError as exc:
        parser.error(str(exc))
    report = runner.run(dry_run=args.dry_run)
    args.json_report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"web_url": report["web_url"], "api_url": report["api_url"], "totals": report["totals"]}, sort_keys=True))
    return 0 if not report["totals"]["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
