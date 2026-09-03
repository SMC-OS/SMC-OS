/**
 * Production incident (post-v1.0.1): a signed-in user whose token expired
 * mid-session kept seeing themselves as authenticated (name/role still
 * shown, no redirect to /login) because AuthProvider only ever computed
 * isAuthenticated once, on mount. A 401 raised later by any api.* call
 * clears the stored token (lib/api.ts's request()) but that never reached
 * this component's React state. AuthProvider must react to the token being
 * cleared at any time, the same way it reacts to an explicit logout().
 */

import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "@/components/auth/AuthProvider";
import { clearToken, setToken } from "@/lib/auth-storage";

vi.mock("@/lib/api", () => ({
  api: {
    getMe: vi.fn(() =>
      Promise.resolve({
        tenant_name: "Acme Stoneworks",
        role: "Owner",
        id: "user-1",
        name: "Jordan Owner",
      })
    ),
  },
}));

function Probe() {
  const { isAuthenticated, isReady, name } = useAuth();
  return (
    <div>
      <span data-testid="ready">{String(isReady)}</span>
      <span data-testid="authed">{String(isAuthenticated)}</span>
      <span data-testid="name">{name ?? "none"}</span>
    </div>
  );
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

describe("AuthProvider — reacts to a token becoming invalid mid-session", () => {
  it("flips isAuthenticated to false and clears the displayed user when the token is cleared after mount", async () => {
    setToken("a-valid-looking-token");

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await screen.findByText("true", { selector: '[data-testid="ready"]' });
    expect(screen.getByTestId("authed")).toHaveTextContent("true");
    expect(screen.getByTestId("name")).toHaveTextContent("Jordan Owner");

    // Simulates what happens when a later API call (e.g. the dashboard
    // poll) gets a 401 for an expired token: lib/api.ts calls this same
    // clearToken(), entirely outside any AuthProvider method.
    act(() => {
      clearToken();
    });

    expect(screen.getByTestId("authed")).toHaveTextContent("false");
    expect(screen.getByTestId("name")).toHaveTextContent("none");
  });
});
