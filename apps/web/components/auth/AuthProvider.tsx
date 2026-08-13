"use client";

import { createContext, useContext, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { clearToken, getToken, setToken } from "@/lib/auth-storage";
import type { SignupRequest } from "@/types/auth";

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
  login: (email: string, password: string) => Promise<void>;
  signup: (data: SignupRequest) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isReady, setIsReady] = useState(false);
  const [tenantName, setTenantName] = useState<string | null>(null);

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
      .then((me) => setTenantName(me.tenant_name))
      .catch(() => setIsAuthenticated(false))
      .finally(() => setIsReady(true));
  }, []);

  async function login(email: string, password: string) {
    const response = await api.login(email, password);
    setToken(response.access_token);
    setIsAuthenticated(true);
    setTenantName(response.user.tenant_name);
  }

  async function signup(data: SignupRequest) {
    const response = await api.signup(data);
    setToken(response.access_token);
    setIsAuthenticated(true);
    setTenantName(response.user.tenant_name);
  }

  function logout() {
    clearToken();
    setIsAuthenticated(false);
    setTenantName(null);
  }

  return (
    <AuthContext.Provider
      value={{ isAuthenticated, isReady, tenantName, login, signup, logout }}
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
