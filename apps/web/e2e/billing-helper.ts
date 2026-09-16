import { execFileSync } from "node:child_process";
import path from "node:path";

/**
 * GEOCORE V1 — FINAL AUTH + TRIAL ACCESS GATES. Most E2E specs sign up a
 * fresh owner through the real API and then drive the real browser
 * through protected routes that now require billing/trial activation
 * (see app/auth/dependencies.py's require_billing_access, wired into
 * AppShell's redirect-to-/pricing). A spec whose subject is something
 * other than billing activation itself marks its fixture tenant active
 * immediately after signup — same "already an established account"
 * shortcut apps/web/e2e/verify-helper.ts takes for email verification,
 * and tests/conftest.py's other_tenant_auth_headers takes on the
 * backend side. Real activation itself, end to end through a real
 * Stripe TEST Checkout, is covered by billing-pricing.spec.ts.
 *
 * Runs a real Python subprocess against the same database the running
 * FastAPI server uses (same pattern as verify-helper.ts) — never a
 * mock, never a shortcut through application code.
 */
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");

function run(script: string): void {
  execFileSync("python", ["-c", script.trim()], { cwd: REPO_ROOT, encoding: "utf-8" });
}

/** Legacy-grandfathered exemption — unlocks workspace access regardless
 * of any particular subscription status, for a spec that doesn't care
 * about billing/trial UI specifics at all. */
export function grantBillingAccess(email: string): void {
  run(`
from app.database import crud
from app.database.database import SessionLocal

db = SessionLocal()
user = crud.get_user_by_email(db, ${JSON.stringify(email)})
crud.upsert_subscription(
    db,
    tenant_id=user.tenant_id,
    plan="pro",
    billing_period="monthly",
    status="active",
    legacy_grandfathered=True,
)
db.close()
`);
}

/** A real trialing subscription with genuine trial dates, mirroring what
 * a real Stripe Checkout + webhook produces — for a spec whose subject
 * is the trial UI itself (days-remaining banner, etc.), not just "can
 * this fixture reach a gated route." */
export function startRealTrial(email: string, plan = "pro", days = 14): void {
  // stripe_subscription_id is unique across the whole table — derive it
  // from the tenant's own user id rather than a fixed literal, or two
  // specs calling this in the same run collide.
  run(`
import uuid
from datetime import datetime, timedelta, timezone
from app.database import crud
from app.database.database import SessionLocal

db = SessionLocal()
user = crud.get_user_by_email(db, ${JSON.stringify(email)})
now = datetime.now(timezone.utc)
crud.upsert_subscription(
    db,
    tenant_id=user.tenant_id,
    plan=${JSON.stringify(plan)},
    billing_period="monthly",
    status="trialing",
    stripe_customer_id=f"cus_e2e_{uuid.uuid4().hex[:12]}",
    stripe_subscription_id=f"sub_e2e_{user.id.hex[:12]}",
    trial_start=now,
    trial_end=now + timedelta(days=${days}),
)
db.close()
`);
}
