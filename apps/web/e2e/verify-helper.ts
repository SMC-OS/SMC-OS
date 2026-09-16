import { execFileSync } from "node:child_process";
import path from "node:path";

/**
 * Sprint 039 Production Readiness Defect Gate, Blocker 2 hotfix — most E2E
 * specs sign up a fresh owner through the real API and then drive the
 * real browser through protected routes that now require a verified
 * session (see app/auth/dependencies.py's require_verified_email, wired
 * into AppShell's redirect-to-/verify-email). A spec whose subject is
 * something other than verification itself (billing, quoting, tasks,
 * tenant isolation, ...) marks its fixture user verified immediately
 * after signup, exactly the same "already an established account"
 * shortcut tests/conftest.py's other_tenant_auth_headers takes on the
 * backend side — real verification itself, end to end through the
 * browser, is covered by email-verification.spec.ts.
 *
 * Runs a real Python subprocess against the same database the running
 * FastAPI server uses (same pattern as email-verification.spec.ts's own
 * mintVerificationToken) — never a mock, never a shortcut through
 * application code.
 */
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");

export function markVerified(email: string): void {
  const script = `
from datetime import datetime, timezone
from app.database import crud
from app.database.database import SessionLocal

db = SessionLocal()
user = crud.get_user_by_email(db, ${JSON.stringify(email)})
user.email_verified_at = datetime.now(timezone.utc)
db.commit()
db.close()
`.trim();
  execFileSync("python", ["-c", script], { cwd: REPO_ROOT, encoding: "utf-8" });
}
