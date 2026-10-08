# Staged HttpOnly Cookie Migration

## Current boundary

The web client stores the bearer access token in localStorage and attaches it
as an Authorization header. This makes a token reachable by JavaScript if an
XSS defect exists; it is not an acceptable final browser-session architecture.

## Target

The API will issue a short-lived, `HttpOnly`, `Secure`, `SameSite=Lax` session
cookie on same-site login. State-changing cross-site requests will require a
CSRF token (double-submit or server-issued request token). Browser clients
will use `credentials: "include"`; non-browser API clients retain an explicit
Bearer-token path until a separately reviewed deprecation.

## Sequencing and rollback

1. Add server-side session issuance and CSRF validation behind a feature flag.
2. Update web fetch helpers to send credentials and CSRF headers.
3. Run both cookie and bearer paths, preferring cookie authentication.
4. Verify login, logout, password reset, Stripe return, CORS, and CSRF tests.
5. Remove localStorage writes only after a monitored release proves cookie
   sessions are stable. Rollback re-enables the bearer path without changing
   password or token-version protections.

No authentication architecture change is made in Phase 2 because cookie/CORS
and CSRF behavior requires an integrated, separately reviewed migration.
