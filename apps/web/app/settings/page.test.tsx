/**
 * Sprint 027 (docs/SPRINTS/sprint-027.md §6.6) — team invitation
 * create/list/revoke and team list/deactivate had zero component-level
 * coverage; only tests/test_invitations.py and tests/test_users.py
 * covered the backend. Also locks in the Owner-only UI gate (a Staff
 * session sees neither the invite form nor the team-management list).
 *
 * Sprint 036 rebuilt Settings as sections (?section=team) instead of one
 * long scroll, and reworded the invite flow: the copy that used to
 * apologise for having no email delivery now presents the joining link
 * as the deliberate output of the action. Every contract this file
 * protects is unchanged and still asserted here:
 *
 *   - an Owner can create an invitation and is shown the real link;
 *   - an Owner can deactivate a member, and the list refreshes;
 *   - a Staff session sees no team-management controls AND never even
 *     issues the Owner-only requests.
 *
 * Only the section the assertions run against, and the button labels,
 * moved.
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

// Sprint 036 — the page reads ?section= to decide which settings section
// to show, so useSearchParams has to be mocked alongside useRouter. Team
// is selected explicitly: these tests are about team management, and
// leaving the section implicit would couple them to whichever section
// happens to be first in the list.
let currentSection = "team";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock, push: pushMock }),
  useSearchParams: () => new URLSearchParams(`section=${currentSection}`),
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
// Sprint 034 — the Company identity card mounts inside the Owner branch of
// this page, so its load-on-mount call has to be mocked here too.
const getCompanyProfileMock = vi.fn();
const updateCompanyProfileMock = vi.fn();

const getNotificationPreferencesMock = vi.fn(async () => [
  {
    category: "quote_activity",
    label: "Quote activity",
    description: "When a quote is approved, or is about to expire.",
    in_app: true,
    email: false,
  },
]);
const updateNotificationPreferencesMock = vi.fn(async () => []);

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
      getCompanyProfile: (...args: unknown[]) => getCompanyProfileMock(...args),
      updateCompanyProfile: (...args: unknown[]) => updateCompanyProfileMock(...args),
      // Sprint 039 (Workstream B) — the notifications card is server-backed
      // now, so it fetches on mount. This mock exists so the *settings
      // page* tests keep testing navigation and role gating rather than
      // failing on a card they are not about; the card's own behaviour is
      // covered in components/settings/NotificationsCard.test.tsx.
      getNotificationPreferences: (...args: unknown[]) =>
        getNotificationPreferencesMock(...args),
      updateNotificationPreferences: (...args: unknown[]) =>
        updateNotificationPreferencesMock(...args),
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

function companyProfile(overrides: Record<string, unknown> = {}) {
  return {
    id: "tenant-1",
    name: "Riverside Stoneworks",
    slug: "riverside-stoneworks",
    status: "active",
    created_at: new Date().toISOString(),
    legal_name: null,
    trading_name: null,
    address_line1: null,
    address_line2: null,
    city: null,
    postcode: null,
    country: null,
    contact_email: null,
    contact_phone: null,
    website: null,
    company_number: null,
    vat_number: null,
    logo_url: null,
    document_footer: null,
    ...overrides,
  };
}

beforeEach(() => {
  currentRole = "Owner";
  currentSection = "team";
  getInvitationsMock.mockReset();
  getUsersMock.mockReset();
  createInvitationMock.mockReset();
  revokeInvitationMock.mockReset();
  deactivateUserMock.mockReset();
  getSubscriptionMock.mockReset();
  createPortalSessionMock.mockReset();
  cancelSubscriptionMock.mockReset();
  resumeSubscriptionMock.mockReset();
  getCompanyProfileMock.mockReset();
  updateCompanyProfileMock.mockReset();
  getInvitationsMock.mockResolvedValue([]);
  getUsersMock.mockResolvedValue([]);
  getSubscriptionMock.mockResolvedValue(null);
  getCompanyProfileMock.mockResolvedValue(companyProfile());
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
    fireEvent.click(screen.getByRole("button", { name: /create invite/i }));

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

    fireEvent.click(screen.getByRole("button", { name: "Remove access" }));

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
    // Even asked for explicitly in the URL, an Owner-only section must
    // not render for a Staff session — the section is hidden from the
    // nav, and a hand-typed ?section=team must not be a way around that.
    currentSection = "team";

    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument();
    });

    expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /create invite/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove access" })).not.toBeInTheDocument();
    // The real contract: a Staff session never issues the Owner-only
    // requests at all, rather than issuing them and hiding the 403.
    expect(getInvitationsMock).not.toHaveBeenCalled();
    expect(getUsersMock).not.toHaveBeenCalled();
  });

  it("staff_session_can_still_reach_the_sections_that_are_theirs", async () => {
    currentRole = "Staff";
    currentSection = "notifications";

    render(<SettingsPage />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /notifications/i })
      ).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /billing/i })).not.toBeInTheDocument();
  });
});
