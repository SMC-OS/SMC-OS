"""Real GeoCore sandbox billing acceptance. No live keys or customer data.
Run with --preflight before configuring QA; normal mode uses a fresh synthetic owner.
Never log secrets, tokens, checkout URLs or raw upstream error payloads.
"""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://geocore-api-qa-acceptance.up.railway.app"
STRIPE = "https://api.stripe.com/v1"
QA_ENV = "f948241d-446f-43ed-bff0-5d12decffd50"
PRICES = {
    "STARTER_MONTHLY": ("price_1UFciG3AQWJTR2rG5pTEIwMl", 2900, "month"),
    "STARTER_ANNUAL": ("price_1UFcik3AQWJTR2rGfU9dKc7G", 29000, "year"),
    "TEAM_MONTHLY": ("price_1UFciN3AQWJTR2rG2XvyLuqb", 5900, "month"),
    "TEAM_ANNUAL": ("price_1UFcir3AQWJTR2rGHyFXBBAU", 59000, "year"),
    "PRO_MONTHLY": ("price_1UFciW3AQWJTR2rGndTcBJJx", 9900, "month"),
    "PRO_ANNUAL": ("price_1UFciy3AQWJTR2rGWmbmBUyc", 99000, "year"),
    "BUSINESS_MONTHLY": ("price_1UFcif3AQWJTR2rGiY1msITo", 19900, "month"),
    "BUSINESS_ANNUAL": ("price_1UFcj43AQWJTR2rGf2kBBxCp", 199000, "year"),
}
KEY = os.environ.get("QA_STRIPE_KEY", "")
SECRET = os.environ.get("QA_STRIPE_SIGNING_SECRET", "")
if not KEY.startswith(("rk_test_", "sk_test_")) or not SECRET.startswith("whsec_"):
    sys.exit("BLOCKED: missing/malformed sandbox key or webhook signing secret; live keys forbidden.")
if os.environ.get("QA_ENVIRONMENT_ID") != QA_ENV or os.environ.get("QA_API") != API:
    sys.exit("REFUSED: not the isolated QA environment.")
results = []

def check(label, good):
    results.append({"check": label, "passed": bool(good)})
    print(("PASS " if good else "FAIL ") + label, flush=True)
    if not good:
        raise RuntimeError(label)

def request(method, base, path, token=None, form=None, body=None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if form is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        data = urllib.parse.urlencode(form).encode()
    elif body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=40) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, {}
    except Exception:
        return 0, {}

def stripe(method, path, form=None, label=None):
    code, obj = request(method, STRIPE, path, KEY, form=form)
    check(label or f"Stripe {method} {path.split('/')[1]} HTTP {code}", 200 <= code < 300)
    return obj

def api(method, path, token=None, body=None, label=None, expected=(200,)):
    code, obj = request(method, API + "/api/v1", path, token, body=body)
    check(label or f"GeoCore {method} {path} HTTP {code}", code in expected)
    return obj

def preflight():
    for name, (pid, amount, interval) in PRICES.items():
        p = stripe("GET", "/prices/" + pid, label="sandbox price readable " + name)
        check("price matches " + name, p.get("livemode") is False and p.get("active") is True
              and p.get("currency") == "gbp" and p.get("unit_amount") == amount
              and p.get("recurring", {}).get("interval") == interval)

def poll(token, label, predicate, seconds=180):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        code, obj = request("GET", API + "/api/v1", "/billing/subscription", token)
        if code == 200 and predicate(obj):
            check(label, True)
            return obj
        time.sleep(5)
    check(label, False)

def main():
    preflight()
    if "--preflight" in sys.argv:
        return
    email = os.environ["STAGING_OWNER_EMAIL"]
    check("synthetic owner only", email.startswith("stripe-qa-") and email.endswith("@acceptance.invalid"))
    token = api("POST", "/auth/login", body={"email": email, "password": os.environ["STAGING_OWNER_PASSWORD"]})["access_token"]
    current = api("GET", "/billing/subscription", token)
    check("fresh no-card trial", current.get("status") == "trialing" and current.get("trial_state") in ("active", "ending_soon")
          and 13 <= current.get("trial_days_remaining", 0) <= 14)
    tenant = current["tenant_id"]
    trial_end = int(dt.datetime.fromisoformat(current["trial_end"].replace("Z", "+00:00")).timestamp())
    check("trial has >48h remaining", trial_end - time.time() > 172800)
    code, _ = request("POST", API + "/api/v1", "/billing/webhook", body={"invalid": True})
    check("unsigned webhook refused", code == 400)
    checkout_id = customer_id = sub_id = None
    try:
        api("POST", "/billing/checkout", token, {"plan": "starter", "billing_period": "monthly"},
            label="closed admission refuses first checkout", expected=(403,))
        # Real Stripe API subscription, not a fabricated webhook. This separately exercises actual Stripe event delivery.
        # Public admission stays CLOSED. This creates only a synthetic subscription; it is not proof of first-checkout completion.
        customer = stripe("POST", "/customers", {"email": email, "description": "GeoCore isolated QA " + os.environ.get("GITHUB_RUN_ID", ""), "metadata[geocore_qa]": "true", "metadata[tenant_id]": tenant})
        customer_id = customer["id"]
        check("customer sandbox and synthetic", customer.get("livemode") is False and customer.get("email") == email)
        pm = stripe("POST", "/payment_methods/pm_card_visa/attach", {"customer": customer_id})
        pm_id = pm["id"]
        check("test payment method attached to QA customer", pm.get("customer") == customer_id)
        sub = stripe("POST", "/subscriptions", {
            "customer": customer_id, "items[0][price]": PRICES["STARTER_MONTHLY"][0],
            "default_payment_method": pm_id, "trial_end": str(trial_end),
            "metadata[tenant_id]": tenant, "metadata[plan]": "starter", "metadata[billing_period]": "monthly",
        })
        sub_id = sub["id"]
        check("real sandbox trial subscription", sub.get("livemode") is False and sub.get("customer") == customer_id and sub.get("status") == "trialing" and sub.get("trial_end") == trial_end)
        poll(token, "actual Stripe subscription-created webhook applied", lambda x: x.get("plan") == "starter" and x.get("status") == "trialing" and x.get("trial_state") is None)
        sub = stripe("POST", "/subscriptions/" + sub_id, {"trial_end": "now", "proration_behavior": "none"})
        # Trial-ending invoices may remain draft pending Stripe's asynchronous finalization.
        # Identify the non-zero renewal invoice, then finalize/pay in the sandbox if needed.
        end = time.monotonic() + 240
        invoice_id = None
        invoice = {}
        while time.monotonic() < end:
            sub = stripe("GET", "/subscriptions/" + sub_id)
            iid = sub.get("latest_invoice")
            if isinstance(iid, str) and iid.startswith("in_"):
                code, inv = request("GET", STRIPE, "/invoices/" + iid, KEY)
                if code == 200 and inv.get("total", 0) > 0:
                    invoice_id, invoice = iid, inv
                    break
            time.sleep(5)
        check("trial-ending non-zero invoice", invoice_id is not None)
        if invoice.get("status") == "draft":
            invoice = stripe("POST", "/invoices/" + invoice_id + "/finalize", {"auto_advance": "false"})
        if invoice.get("status") == "open":
            # Stripe serializes payment attempts; refresh before attempting to pay.
            invoice = stripe("GET", "/invoices/" + invoice_id)
            if invoice.get("status") == "open":
                invoice = stripe("POST", "/invoices/" + invoice_id + "/pay", {"payment_method": pm_id})
        end = time.monotonic() + 180
        paid = False
        while time.monotonic() < end:
            code, invoice = request("GET", STRIPE, "/invoices/" + invoice_id, KEY)
            if code == 200 and invoice.get("status") == "paid" and invoice.get("amount_paid", 0) > 0:
                paid = True
                break
            time.sleep(5)
        check("real sandbox invoice paid", paid)
        poll(token, "trial-to-active after real Stripe event", lambda x: x.get("plan") == "starter" and x.get("status") == "active", 240)
        # Existing subscription holders may still use Checkout while admission is closed.
        # Create but do not complete this session: a second subscription would be unwanted.
        checkout = api("POST", "/billing/checkout", token, {"plan": "starter", "billing_period": "monthly"})
        url = checkout.get("checkout_url", "")
        match = re.search(r"/(cs_test_[a-zA-Z0-9]+)", urllib.parse.urlsplit(url).path)
        check("existing subscriber hosted sandbox Checkout URL", urllib.parse.urlsplit(url).hostname == "checkout.stripe.com" and match is not None)
        checkout_id = match.group(1)
        session = stripe("GET", "/checkout/sessions/" + checkout_id)
        check("actual Checkout session is subscription in test mode", session.get("livemode") is False and session.get("mode") == "subscription")
        check("Checkout bound to synthetic workspace", session.get("client_reference_id") == tenant and session.get("metadata", {}).get("tenant_id") == tenant)
        lines = stripe("GET", "/checkout/sessions/" + checkout_id + "/line_items")
        check("Checkout correct price", len(lines.get("data", [])) == 1 and lines["data"][0]["price"]["id"] == PRICES["STARTER_MONTHLY"][0])
        stripe("POST", "/checkout/sessions/" + checkout_id + "/expire", {})
        checkout_id = None
        portal = api("POST", "/billing/portal", token)
        check("customer portal created", urllib.parse.urlsplit(portal.get("portal_url", "")).hostname == "billing.stripe.com")
        cancel = api("POST", "/billing/cancel", token)
        check("cancel at period end", cancel.get("cancel_at_period_end") is True)
        check("Stripe cancellation flag", stripe("GET", "/subscriptions/" + sub_id).get("cancel_at_period_end") is True)
        resume = api("POST", "/billing/resume", token)
        check("resume before period end", resume.get("cancel_at_period_end") is False)
        check("Stripe resume flag", stripe("GET", "/subscriptions/" + sub_id).get("cancel_at_period_end") is False)
        item = stripe("GET", "/subscriptions/" + sub_id)["items"]["data"][0]["id"]
        for plan, price in (("team", PRICES["TEAM_MONTHLY"][0]), ("starter", PRICES["STARTER_MONTHLY"][0])):
            stripe("POST", "/subscriptions/" + sub_id, {"items[0][id]": item, "items[0][price]": price, "proration_behavior": "none"})
            poll(token, "actual Stripe plan change reflected: " + plan, lambda x, p=plan: x.get("plan") == p and x.get("status") == "active")
        stripe("DELETE", "/subscriptions/" + sub_id)
        sub_id = None
        poll(token, "actual Stripe cancellation webhook applied", lambda x: x.get("status") in ("cancelled", "canceled"))
    finally:
        # All IDs originate from this run; never enumerate or delete unrelated sandbox resources.
        if sub_id:
            code, _ = request("DELETE", STRIPE, "/subscriptions/" + sub_id, KEY)
            print("cleanup synthetic subscription HTTP", code)
            results.append({"check": "cleanup synthetic subscription", "passed": code in (200, 404)})
        if checkout_id:
            code, _ = request("POST", STRIPE, "/checkout/sessions/" + checkout_id + "/expire", KEY, form={})
            print("cleanup uncompleted checkout HTTP", code)
            results.append({"check": "expire synthetic checkout", "passed": code in (200, 404)})
        if customer_id:
            code, _ = request("DELETE", STRIPE, "/customers/" + customer_id, KEY)
            print("cleanup synthetic customer HTTP", code)
            results.append({"check": "cleanup synthetic customer", "passed": code in (200, 404)})

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Exception messages from network/client libraries may include sensitive request details.
        print("BILLING RUN STOPPED:", type(exc).__name__, flush=True)
        sys.exit(1)
    finally:
        Path("qa-stripe-results.json").write_text(json.dumps({"environment": "isolated_qa", "checks": results, "scope": "closed admission denial; real sandbox API-created subscription and webhook acceptance; existing-subscriber checkout session only; initial hosted checkout completion and failed-payment recovery not covered"}, indent=2))
    if not all(x["passed"] for x in results):
        sys.exit(1)
