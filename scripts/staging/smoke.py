"""Secret-safe, operator-run Sprint 019 staging smoke harness.

No HTTP request is made at import time. A real run creates fresh synthetic
records only, keeps credentials in memory, and writes sanitized evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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
    "portal_messaging", "token_enforcement", "tenant_isolation", "cors_allowed",
    "cors_denied", "logs_request_ids", "repository_secret_scan", "backup_restore",
)
SENSITIVE_KEY = re.compile(r"(?:authorization|token|password|secret|email|database|credential)", re.I)
DEFAULT_TIMEOUT_SECONDS = 15.0


class SmokeHttpError(Exception):
    def __init__(self, method: str, route: str, status_code: int) -> None:
        self.method, self.route, self.status_code = method, route, status_code


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
    def __init__(self, web_url: str, api_url: str, *, allow_restart: bool, timeout: float, quote_material: str | None = None, quote_thickness: str | None = None) -> None:
        self.web_url = validate_public_https_origin(web_url)
        self.api_url = validate_public_https_origin(api_url)
        self.allow_restart, self.timeout = allow_restart, timeout
        self.quote_material, self.quote_thickness = quote_material, quote_thickness
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
        response.raise_for_status()
        return response

    def headers(self, tenant: str = "a") -> dict[str, str]:
        return {"Authorization": f"Bearer {self.state[f'{tenant}_token']}"}

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
        self.created.append({"kind": "tenant_user", "synthetic_prefix": self.prefix, "tenant": tenant})
        return {"signup_status": signup.status_code, "login_token_received": bool(login.get("access_token"))}

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

    def cors(self, allowed: bool) -> dict[str, Any]:
        origin = self.web_url if allowed else "https://untrusted.example.invalid"
        response = self.client.options(f"{self.api_url}/api/v1/customers", headers={"Origin": origin, "Access-Control-Request-Method": "GET"}, timeout=self.timeout)
        actual = response.headers.get("access-control-allow-origin")
        return {"status_code": response.status_code, "origin_contract": actual == self.web_url if allowed else actual is None}

    def health(self, path: str, expected: dict[str, str]) -> dict[str, Any]:
        response = self.client.get(f"{self.api_url}{path}", timeout=self.timeout)
        return {"status_code": response.status_code, "body_matches": response.json() == expected, "request_id_present": bool(response.headers.get("x-request-id"))}

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
            self.gate("signup_login_auth", lambda: (self.signup("a"), self.signup("b"))[1])
            for name, action in (("customer", self.customer), ("project", self.project)):
                self.gate(name, action)
            if self.quote_material and self.quote_thickness:
                self.gate("quote_invoice", self.quote_invoice)
            else:
                self.blocked("quote_invoice", "requires --quote-material and --quote-thickness")
            for name, action in (("staff_document", self.document), ("portal_token", self.portal), ("portal_documents", self.portal_documents), ("portal_messaging", self.portal_messages), ("token_enforcement", self.token_enforcement)):
                self.gate(name, action)
            if "quote_id" in self.state:
                self.gate("tenant_isolation", self.tenant_isolation)
            else:
                self.blocked("tenant_isolation", "partial customer/project checks cannot satisfy full quote isolation coverage")
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not 1 <= args.timeout_seconds <= 60:
        parser.error("--timeout-seconds must be between 1 and 60")
    if bool(args.quote_material) != bool(args.quote_thickness):
        parser.error("--quote-material and --quote-thickness must be supplied together")
    try:
        runner = SmokeRunner(args.web_url, args.api_url, allow_restart=args.allow_restart, timeout=args.timeout_seconds, quote_material=args.quote_material, quote_thickness=args.quote_thickness)
    except ValueError as exc:
        parser.error(str(exc))
    report = runner.run(dry_run=args.dry_run)
    args.json_report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"web_url": report["web_url"], "api_url": report["api_url"], "totals": report["totals"]}, sort_keys=True))
    return 0 if not report["totals"]["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
