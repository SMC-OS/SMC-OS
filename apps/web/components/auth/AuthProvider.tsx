"use client";

import { createContext, useContext, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { clearToken, getToken, setToken, TOKEN_CLEARED_EVENT } from "@/lib/auth-storage";
import type { SignupRequest } from "@/types/auth";
import type { AcceptInvitationRequest } from "@/types/invitation";

interface AuthContextValue {
  isAuthenticated: boolean;
  // False until the localStorage check below has run. Consumers must wait
  // for this before deciding to redirect — child effects fire before this
  // provider's own mount effect, so isAuthenticated is still its initial
  // `false` on the very first pass even for an already-logged-in user.
  isReady: boolean;
  // Sprint 009 — the signed-in user's company name, null until resolved
  // (no token, or the token turned out to be invalid/expired).
  tenantName: string | null;
  // Sprint 028 (UAT-001) — the signed-in user's own name, for display
  // (e.g. the header profile menu) — never used for access decisions.
  name: string | null;
  // Sprint 011 — "Owner" | "Staff" | null, used to gate the invitations UI
  // client-side (the server enforces this for real via require_role()).
  role: string | null;
  // Sprint 015 — the signed-in user's own id, used to hide a "manage this
  // person" action on their own row (e.g. the Team list's Deactivate
  // button) — the server enforces the real rule (CannotDeactivateSelfError)
  // regardless of what the UI shows.
  userId: string | null;
  // Sprint 039 Production Readiness Defect Gate, Blocker 2 hotfix — the
  // signed-in user's own email, shown on the "verify your email" holding
  // screen ("We've sent a link to <email>") without a second request.
  email: string | null;
  // Whether the signed-in user is CURRENTLY blocked from normal
  // application access (mirrors AuthUser.verification_required). AppShell
  // reads this to redirect to /verify-email; consumers must not derive
  // this from email_verified_at themselves (see that field's own note).
  verificationRequired: boolean;
  // GEOCORE V1 — FINAL AUTH + TRIAL ACCESS GATES — mirrors
  // AuthUser.billing_access_required exactly the same way
  // verificationRequired mirrors verification_required. AppShell checks
  // this only once verificationRequired is false (verification is the
  // narrower, earlier gate) to redirect to /pricing.
  billingAccessRequired: boolean;
  // login/signup/acceptInvite resolve to the fresh required-state so the
  // calling page can route synchronously on success, rather than reading
  // this same value back off (necessarily-async) state.
  login: (email: string, password: string) => Promise<AuthRequiredState>;
  signup: (data: SignupRequest) => Promise<AuthRequiredState>;
  // Sprint 011 — accepting a Staff invitation signs the new user straight
  // in, same shape as login()/signup().
  acceptInvite: (token: string, data: AcceptInvitationRequest) => Promise<AuthRequiredState>;
  // Phase B — re-reads /auth/me so a change made on the server (starting
  // the no-card trial, returning from Checkout) unlocks the workspace
  // without a full page reload.
  refreshAccess: () => Promise<AuthRequiredState>;
  logout: () => void;
}

interface AuthRequiredState {
  verificationRequired: boolean;
  billingAccessRequired: boolean;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isReady, setIsReady] = useState(false);
  const [tenantName, setTenantName] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  const [name, setName] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [verificationRequired, setVerificationRequired] = useState(false);
  const [billingAccessRequired, setBillingAccessRequired] = useState(false);

  useEffect(() => {
    // One-time sync from a browser-only API (localStorage isn't available
    // during SSR) — same justified pattern as ThemeProvider's mount effect.
    const token = getToken();
    if (token === null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setIsReady(true);
      return;
    }

    setIsAuthenticated(true);
    // Sprint 009 — a stored token alone doesn't tell us the company name,
    // so it's resolved once via /auth/me on mount (also doubles as the
    // token-still-valid check request() already handles via clearToken()
    // on a 401).
    api
      .getMe()
      .then((me) => {
        setTenantName(me.tenant_name);
        setRole(me.role);
        setUserId(me.id);
        setName(me.name);
        setEmail(me.email);
        setVerificationRequired(me.verification_required);
        setBillingAccessRequired(me.billing_access_required);
      })
      .catch(() => setIsAuthenticated(false))
      .finally(() => setIsReady(true));
  }, []);

  useEffect(() => {
    // Production incident (post-v1.0.1): a token can go invalid at any
    // point during an already-authenticated session (expiry, a 401 from
    // any api.* call) — not just at mount. clearToken() announces this via
    // TOKEN_CLEARED_EVENT so this state stays truthful for the rest of the
    // session, the same way an explicit logout() already resets it.
    function handleTokenCleared() {
      setIsAuthenticated(false);
      setTenantName(null);
      setRole(null);
      setUserId(null);
      setName(null);
      setEmail(null);
      setVerificationRequired(false);
      setBillingAccessRequired(false);
    }
    window.addEventListener(TOKEN_CLEARED_EVENT, handleTokenCleared);
    return () => window.removeEventListener(TOKEN_CLEARED_EVENT, handleTokenCleared);
  }, []);

  async function refreshAccess(): Promise<AuthRequiredState> {
    const me = await api.getMe();
    setVerificationRequired(me.verification_required);
    setBillingAccessRequired(me.billing_access_required);
    return {
      verificationRequired: me.verification_required,
      billingAccessRequired: me.billing_access_required,
    };
  }

  async function login(email: string, password: string): Promise<AuthRequiredState> {
    const response = await api.login(email, password);
    setToken(response.access_token);
    setIsAuthenticated(true);
    setTenantName(response.user.tenant_name);
    setRole(response.user.role);
    setUserId(response.user.id);
    setName(response.user.name);
    setEmail(response.user.email);
    setVerificationRequired(response.user.verification_required);
    setBillingAccessRequired(response.user.billing_access_required);
    return {
      verificationRequired: response.user.verification_required,
      billingAccessRequired: response.user.billing_access_required,
    };
  }

  async function signup(data: SignupRequest): Promise<AuthRequiredState> {
    const response = await api.signup(data);
    setToken(response.access_token);
    setIsAuthenticated(true);
    setTenantName(response.user.tenant_name);
    setRole(response.user.role);
    setUserId(response.user.id);
    setName(response.user.name);
    setEmail(response.user.email);
    setVerificationRequired(response.user.verification_required);
    setBillingAccessRequired(response.user.billing_access_required);
    return {
      verificationRequired: response.user.verification_required,
      billingAccessRequired: response.user.billing_access_required,
    };
  }

  async function acceptInvite(
    token: string,
    data: AcceptInvitationRequest
  ): Promise<AuthRequiredState> {
    const response = await api.acceptInvitation(token, data);
    setToken(response.access_token);
    setIsAuthenticated(true);
    setTenantName(response.user.tenant_name);
    setRole(response.user.role);
    setUserId(response.user.id);
    setName(response.user.name);
    setEmail(response.user.email);
    setVerificationRequired(response.user.verification_required);
    setBillingAccessRequired(response.user.billing_access_required);
    return {
      verificationRequired: response.user.verification_required,
      billingAccessRequired: response.user.billing_access_required,
    };
  }

  function logout() {
    clearToken();
    setIsAuthenticated(false);
    setTenantName(null);
    setRole(null);
    setUserId(null);
    setName(null);
    setEmail(null);
    setVerificationRequired(false);
    setBillingAccessRequired(false);
  }

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        isReady,
        tenantName,
        role,
        userId,
        name,
        email,
        verificationRequired,
        billingAccessRequired,
        login,
        signup,
        acceptInvite,
        refreshAccess,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
