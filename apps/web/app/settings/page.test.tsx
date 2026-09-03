/**
 * Sprint 027 (docs/SPRINTS/sprint-027.md §6.6) — team invitation
 * create/list/revoke and team list/deactivate had zero component-level
 * coverage; only tests/test_invitations.py and tests/test_users.py
 * covered the backend. Also locks in the Owner-only UI gate (a Staff
 * session sees neither the invite form nor the team-management list).
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Hoisted, stable references — same reasoning as
// app/projects/[id]/page.test.tsx: settings/page.tsx's own load-on-mount
// useEffect depends on `router` in its dependency array, so a mock that
// returns a *new* function on every render re-fires that effect (and
// therefore api.getUsers/getInvitations) on every re-render, not once.
const replaceMock = vi.fn();
const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock, push: pushMock }),
}));

let currentRole: string | null = "Owner";

vi.mock("@/components/auth/AuthProvider", () => ({
  useAuth: () => ({
    isAuthenticated: true,
    isReady: true,
    role: currentRole,
    userId: "owner-1",
  }),
}));

const getInvitationsMock = vi.fn();
const getUsersMock = vi.fn();
const createInvitationMock = vi.fn();
const revokeInvitationMock = vi.fn();
const deactivateUserMock = vi.fn();
const getSubscriptionMock = vi.fn();
const createPortalSessionMock = vi.fn();
const cancelSubscriptionMock = vi.fn();
const resumeSubscriptionMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      getInvitations: (...args: unknown[]) => getInvitationsMock(...args),
      getUsers: (...args: unknown[]) => getUsersMock(...args),
      createInvitation: (...args: unknown[]) => createInvitationMock(...args),
      revokeInvitation: (...args: unknown[]) => revokeInvitationMock(...args),
      deactivateUser: (...args: unknown[]) => deactivateUserMock(...args),
      getSubscription: (...args: unknown[]) => getSubscriptionMock(...args),
      createPortalSession: (...args: unknown[]) => createPortalSessionMock(...args),
      cancelSubscriptionAtPeriodEnd: (...args: unknown[]) => cancelSubscriptionMock(...args),
      resumeSubscription: (...args: unknown[]) => resumeSubscriptionMock(...args),
    },
  };
});

import SettingsPage from "./page";

function teamMember(overrides: Record<string, unknown> = {}) {
  return {
    id: "staff-1",
    name: "Jordan Staff",
    email: "jordan@example.invalid",
    role: "Staff",
    is_active: true,
    ...overrides,
  };
}

beforeEach(() => {
  currentRole = "Owner";
  getInvitationsMock.mockReset();
  getUsersMock.mockReset();
  createInvitationMock.mockReset();
  revokeInvitationMock.mockReset();
  deactivateUserMock.mockReset();
  getSubscriptionMock.mockReset();
  createPortalSessionMock.mockReset();
  cancelSubscriptionMock.mockReset();
  resumeSubscriptionMock.mockReset();
  getInvitationsMock.mockResolvedValue([]);
  getUsersMock.mockResolvedValue([]);
  getSubscriptionMock.mockResolvedValue(null);
});

afterEach(() => {
  cleanup();
});

describe("SettingsPage — Sprint 027 team/invitation management", () => {
  it("owner_can_create_an_invitation_and_sees_the_generated_link", async () => {
    createInvitationMock.mockResolvedValue({
      id: "invite-1",
      email: "newhire@example.invalid",
      status: "pending",
      created_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 7 * 86_400_000).toISOString(),
      token: "invite-token-abc",
    });

    render(<SettingsPage />);

    await waitFor(() => {
      expect(getInvitationsMock).toHaveBeenCalled();
    });

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "newhire@example.invalid" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send invite/i }));

    await waitFor(() => {
      expect(createInvitationMock).toHaveBeenCalledWith("newhire@example.invalid");
    });
    await waitFor(() => {
      expect(screen.getByText(/newhire@example\.invalid/)).toBeInTheDocument();
      expect(screen.getByDisplayValue(/\/invite\/invite-token-abc$/)).toBeInTheDocument();
    });
  });

  it("owner_sees_the_team_list_and_can_deactivate_a_staff_member", async () => {
    getUsersMock.mockResolvedValue([teamMember()]);

    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByText("Jordan Staff")).toBeInTheDocument();
    });
    const callsBeforeDeactivate = getUsersMock.mock.calls.length;

    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));

    await waitFor(() => {
      expect(deactivateUserMock).toHaveBeenCalledWith("staff-1");
    });
    // A before/after comparison, not an exact count: this environment's
    // effect-running behavior (React re-render batching in jsdom) makes
    // the initial mount's own call count non-deterministic here — the
    // actual contract under test is "deactivating refreshes the team
    // list," proven by strictly more calls after the click than before.
    await waitFor(() => {
      expect(getUsersMock.mock.calls.length).toBeGreaterThan(callsBeforeDeactivate);
    });
  });

  it("staff_session_sees_no_invite_or_team_management_controls", async () => {
    currentRole = "Staff";

    render(<SettingsPage />);

    await waitFor(() => {
      expect(
        screen.getByText("Only workspace owners can invite and manage teammates.")
      ).toBeInTheDocument();
    });
    expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /send invite/i })).not.toBeInTheDocument();
    expect(getInvitationsMock).not.toHaveBeenCalled();
    expect(getUsersMock).not.toHaveBeenCalled();
  });
});
