"use client";

import { createContext, useContext, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { clearToken, getToken, setToken } from "@/lib/auth-storage";
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
  // Sprint 011 — "Owner" | "Staff" | null, used to gate the invitations UI
  // client-side (the server enforces this for real via require_role()).
  role: string | null;
  // Sprint 015 — the signed-in user's own id, used to hide a "manage this
  // person" action on their own row (e.g. the Team list's Deactivate
  // button) — the server enforces the real rule (CannotDeactivateSelfError)
  // regardless of what the UI shows.
  userId: string | null;
  login: (email: string, password: string) => Promise<void>;
  signup: (data: SignupRequest) => Promise<void>;
  // Sprint 011 — accepting a Staff invitation signs the new user straight
  // in, same shape as login()/signup().
  acceptInvite: (token: string, data: AcceptInvitationRequest) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isReady, setIsReady] = useState(false);
  const [tenantName, setTenantName] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);

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
      })
      .catch(() => setIsAuthenticated(false))
      .finally(() => setIsReady(true));
  }, []);

  async function login(email: string, password: string) {
    const response = await api.login(email, password);
    setToken(response.access_token);
    setIsAuthenticated(true);
    setTenantName(response.user.tenant_name);
    setRole(response.user.role);
    setUserId(response.user.id);
  }

  async function signup(data: SignupRequest) {
    const response = await api.signup(data);
    setToken(response.access_token);
    setIsAuthenticated(true);
    setTenantName(response.user.tenant_name);
    setRole(response.user.role);
    setUserId(response.user.id);
  }

  async function acceptInvite(token: string, data: AcceptInvitationRequest) {
    const response = await api.acceptInvitation(token, data);
    setToken(response.access_token);
    setIsAuthenticated(true);
    setTenantName(response.user.tenant_name);
    setRole(response.user.role);
    setUserId(response.user.id);
  }

  function logout() {
    clearToken();
    setIsAuthenticated(false);
    setTenantName(null);
    setRole(null);
    setUserId(null);
  }

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        isReady,
        tenantName,
        role,
        userId,
        login,
        signup,
        acceptInvite,
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
