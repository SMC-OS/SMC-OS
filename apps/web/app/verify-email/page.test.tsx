/**
 * Sprint 039 Production Readiness Defect Gate, Blocker 2 follow-up
 * (verification resend/token hotfix). Reproduces, at the frontend layer,
 * the owner's exact live-staging confusion: a second view of an
 * already-successfully-used link showing a scary "invalid or expired"
 * instead of acknowledging the account is already verified, and a resend
 * after verification claiming "email sent" with nothing actually queued.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";

const pushMock = vi.fn();
let currentToken: string | null = null;

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
  useSearchParams: () => new URLSearchParams(currentToken ? `token=${currentToken}` : ""),
}));

const confirmMock = vi.fn();
const resendMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      confirmEmailVerification: (...args: unknown[]) => confirmMock(...args),
      resendVerificationEmail: (...args: unknown[]) => resendMock(...args),
    },
  };
});

let authState: {
  isReady: boolean;
  isAuthenticated: boolean;
  verificationRequired: boolean;
  email: string | null;
};
const logoutMock = vi.fn();

vi.mock("@/components/auth/AuthProvider", () => ({
  useAuth: () => ({ ...authState, logout: logoutMock }),
}));

import VerifyEmailPage from "./page";

beforeEach(() => {
  pushMock.mockClear();
  confirmMock.mockReset();
  resendMock.mockReset();
  logoutMock.mockClear();
  currentToken = null;
  authState = {
    isReady: true,
    isAuthenticated: true,
    verificationRequired: true,
    email: "owner@example.invalid",
  };
});

afterEach(() => {
  cleanup();
});

describe("VerifyEmailPage — no token (the holding screen AppShell redirects to)", () => {
  it("shows_the_users_email_resend_and_sign_out_when_authenticated", () => {
    render(<VerifyEmailPage />);
    expect(screen.getByText("owner@example.invalid")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resend verification email" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });

  it("sign_out_clears_the_session_and_returns_to_login", () => {
    render(<VerifyEmailPage />);
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(logoutMock).toHaveBeenCalled();
    expect(pushMock).toHaveBeenCalledWith("/login");
  });

  it("shows_a_sign_in_prompt_instead_of_resend_when_unauthenticated", () => {
    authState.isAuthenticated = false;
    render(<VerifyEmailPage />);
    expect(screen.queryByRole("button", { name: "Resend verification email" })).toBeNull();
    expect(screen.getByRole("link", { name: "Sign in" })).toBeInTheDocument();
  });
});

describe("VerifyEmailPage — confirming a token", () => {
  it("shows_success_and_continues_to_the_workspace_when_confirm_succeeds", async () => {
    currentToken = "a-fresh-token";
    confirmMock.mockResolvedValue({ message: "ok" });

    render(<VerifyEmailPage />);
    await waitFor(() => {
      expect(screen.getByText("Your email address has been verified.")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue to GeoCore" }));
    expect(pushMock).toHaveBeenCalledWith("/onboarding");
  });

  it("shows_an_already_verified_state_not_invalid_when_confirm_fails_but_the_session_is_already_verified", async () => {
    // The owner's exact live-staging scenario: a second view of a link
    // whose first use already succeeded. confirm() 400s (replay stays
    // rejected — that contract is unchanged), but this browser's own
    // live auth state (refreshed via /auth/me) already knows the
    // account is verified.
    currentToken = "an-already-used-token";
    confirmMock.mockRejectedValue(new ApiError("Bad request", 400));
    authState.verificationRequired = false;

    render(<VerifyEmailPage />);
    await waitFor(() => {
      expect(
        screen.getByText("Your email address is already verified — you're all set.")
      ).toBeInTheDocument();
    });
    expect(screen.queryByText(/invalid or has expired/i)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Continue to GeoCore" }));
    expect(pushMock).toHaveBeenCalledWith("/onboarding");
  });

  it("shows_the_invalid_state_when_confirm_fails_and_the_session_is_genuinely_still_unverified", async () => {
    currentToken = "a-bad-token";
    confirmMock.mockRejectedValue(new ApiError("Bad request", 400));
    authState.verificationRequired = true;

    render(<VerifyEmailPage />);
    await waitFor(() => {
      expect(screen.getByText(/invalid or has expired/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Resend verification email" })).toBeInTheDocument();
  });

  it("shows_the_invalid_state_with_a_sign_in_prompt_when_unauthenticated", async () => {
    currentToken = "a-bad-token";
    confirmMock.mockRejectedValue(new ApiError("Bad request", 400));
    authState.isAuthenticated = false;

    render(<VerifyEmailPage />);
    await waitFor(() => {
      expect(screen.getByText(/invalid or has expired/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: "sign in" })).toBeInTheDocument();
  });
});

describe("VerifyEmailPage — resend states", () => {
  it("shows_a_truthful_sent_confirmation_on_a_genuine_new_send", async () => {
    resendMock.mockResolvedValue({ message: "Verification email sent.", already_verified: false });

    render(<VerifyEmailPage />);
    fireEvent.click(screen.getByRole("button", { name: "Resend verification email" }));
    await waitFor(() => {
      expect(screen.getByText("Verification email sent — check your inbox.")).toBeInTheDocument();
    });
  });

  it("shows_an_honest_already_verified_message_instead_of_a_false_sent_confirmation", async () => {
    // The other half of the owner's exact bug: resend succeeded (200)
    // but queued nothing, because the account was already verified.
    resendMock.mockResolvedValue({
      message: "Your email is already verified.",
      already_verified: true,
    });

    render(<VerifyEmailPage />);
    fireEvent.click(screen.getByRole("button", { name: "Resend verification email" }));
    await waitFor(() => {
      expect(
        screen.getByText("Your email is already verified — you're all set.")
      ).toBeInTheDocument();
    });
    expect(screen.queryByText("Verification email sent — check your inbox.")).toBeNull();
  });

  it("shows_a_cooldown_message_on_429", async () => {
    resendMock.mockRejectedValue(new ApiError("Too Many Requests", 429));

    render(<VerifyEmailPage />);
    fireEvent.click(screen.getByRole("button", { name: "Resend verification email" }));
    await waitFor(() => {
      expect(screen.getByText(/wait a little before requesting/i)).toBeInTheDocument();
    });
  });

  it("shows_a_generic_retry_message_on_any_other_failure", async () => {
    resendMock.mockRejectedValue(new ApiError("Server error", 500));

    render(<VerifyEmailPage />);
    fireEvent.click(screen.getByRole("button", { name: "Resend verification email" }));
    await waitFor(() => {
      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    });
  });
});
