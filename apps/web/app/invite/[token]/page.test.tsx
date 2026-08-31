/**
 * Sprint 027 (docs/SPRINTS/sprint-027.md §6.5) — valid/expired/
 * already-accepted invitation-token states had zero component coverage.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";

vi.mock("next/navigation", () => ({
  useParams: () => ({ token: "invite-token-1" }),
  useRouter: () => ({ push: pushMock }),
}));

const pushMock = vi.fn();
const acceptInviteMock = vi.fn();

vi.mock("@/components/auth/AuthProvider", () => ({
  useAuth: () => ({ acceptInvite: acceptInviteMock }),
}));

const getInvitationByTokenMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: { getInvitationByToken: (...args: unknown[]) => getInvitationByTokenMock(...args) },
  };
});

import AcceptInvitePage from "./page";

function invite(overrides: Record<string, unknown> = {}) {
  return {
    email: "newhire@example.invalid",
    tenant_name: "Acme Stoneworks",
    role: "Staff",
    status: "pending",
    expires_at: new Date(Date.now() + 86_400_000).toISOString(),
    ...overrides,
  };
}

beforeEach(() => {
  pushMock.mockClear();
  acceptInviteMock.mockReset();
  getInvitationByTokenMock.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("AcceptInvitePage — Sprint 027 team-invitation entry point", () => {
  it("renders_the_accept_form_for_a_pending_invitation_and_submits", async () => {
    getInvitationByTokenMock.mockResolvedValue(invite());
    acceptInviteMock.mockResolvedValue(undefined);

    render(<AcceptInvitePage />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("newhire@example.invalid")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "New Hire" } });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "a-real-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: /accept invitation/i }));

    await waitFor(() => {
      expect(acceptInviteMock).toHaveBeenCalledWith("invite-token-1", {
        name: "New Hire",
        password: "a-real-password",
      });
    });
    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/customers");
    });
  });

  it("shows_an_expired_state_and_renders_no_form", async () => {
    getInvitationByTokenMock.mockResolvedValue(invite({ status: "expired" }));

    render(<AcceptInvitePage />);

    await waitFor(() => {
      expect(
        screen.getByText(/This invitation link has expired/)
      ).toBeInTheDocument();
    });
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
  });

  it("shows_a_revoked_state_and_renders_no_form", async () => {
    getInvitationByTokenMock.mockResolvedValue(invite({ status: "revoked" }));

    render(<AcceptInvitePage />);

    await waitFor(() => {
      expect(screen.getByText(/This invitation has been revoked/)).toBeInTheDocument();
    });
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
  });

  it("shows_an_already_accepted_state_and_renders_no_form", async () => {
    getInvitationByTokenMock.mockResolvedValue(invite({ status: "accepted" }));

    render(<AcceptInvitePage />);

    await waitFor(() => {
      expect(screen.getByText(/already been used/)).toBeInTheDocument();
    });
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
  });

  it("shows_a_not_found_state_for_an_unknown_token", async () => {
    getInvitationByTokenMock.mockRejectedValue(new ApiError("Not found", 404));

    render(<AcceptInvitePage />);

    await waitFor(() => {
      expect(screen.getByText("This invitation link isn't valid.")).toBeInTheDocument();
    });
  });
});
