"use client";

import { createContext, useContext, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { clearToken, getToken, setToken } from "@/lib/auth-storage";

interface AuthContextValue {
  isAuthenticated: boolean;
  // False until the localStorage check below has run. Consumers must wait
  // for this before deciding to redirect — child effects fire before this
  // provider's own mount effect, so isAuthenticated is still its initial
  // `false` on the very first pass even for an already-logged-in user.
  isReady: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    // One-time sync from a browser-only API (localStorage isn't available
    // during SSR) — same justified pattern as ThemeProvider's mount effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsAuthenticated(getToken() !== null);
    setIsReady(true);
  }, []);

  async function login(email: string, password: string) {
    const response = await api.login(email, password);
    setToken(response.access_token);
    setIsAuthenticated(true);
  }

  function logout() {
    clearToken();
    setIsAuthenticated(false);
  }

  return (
    <AuthContext.Provider value={{ isAuthenticated, isReady, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
