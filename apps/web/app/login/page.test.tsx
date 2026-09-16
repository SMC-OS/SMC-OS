/**
 * Sprint 027 (docs/SPRINTS/sprint-027.md §6.3) — the login form had zero
 * component-level coverage before this sprint; every Playwright spec
 * signed up through the raw API instead of exercising this form.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

const loginMock = vi.fn();

vi.mock("@/components/auth/AuthProvider", () => ({
  useAuth: () => ({ login: loginMock }),
}));

import LoginPage from "./page";

beforeEach(() => {
  pushMock.mockClear();
  loginMock.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("LoginPage — Sprint 027 full-system journey entry point", () => {
  it("masks_then_reveals_and_hides_the_password_without_submitting_or_losing_it", () => {
    render(<LoginPage />);
    const password = screen.getByLabelText("Password");
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveAttribute("autocomplete", "current-password");
    fireEvent.change(password, { target: { value: "correct-password" } });

    fireEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
    expect(password).toHaveValue("correct-password");
    expect(loginMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Hide password" }));
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveValue("correct-password");
  });

  it("submits_credentials_and_redirects_to_customers_on_success", async () => {
    loginMock.mockResolvedValue({ verificationRequired: false, billingAccessRequired: false });

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "owner@example.invalid" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "correct-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(loginMock).toHaveBeenCalledWith("owner@example.invalid", "correct-password");
    });
    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/customers");
    });
  });

  // Sprint 039 Production Readiness Defect Gate, Blocker 2 hotfix — an
  // existing-but-unverified account must not bypass verification just by
  // logging in again.
  it("redirects_to_verify_email_when_the_account_is_still_unverified", async () => {
    loginMock.mockResolvedValue({ verificationRequired: true, billingAccessRequired: true });

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "unverified@example.invalid" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "correct-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/verify-email");
    });
  });

  // GEOCORE V1 — FINAL AUTH + TRIAL ACCESS GATES — a verified account
  // with no active billing/trial must not bypass activation by logging
  // in again either.
  it("redirects_to_pricing_when_verified_but_not_yet_billing_activated", async () => {
    loginMock.mockResolvedValue({ verificationRequired: false, billingAccessRequired: true });

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "not-activated@example.invalid" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "correct-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/pricing");
    });
  });

  it("shows_a_specific_error_on_401_and_never_redirects", async () => {
    loginMock.mockRejectedValue(new ApiError("Unauthorized", 401));

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "owner@example.invalid" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "wrong-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText("Incorrect email or password.")).toBeInTheDocument();
    });
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("shows_a_generic_error_on_a_non_401_failure", async () => {
    loginMock.mockRejectedValue(new ApiError("Server error", 500));

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "owner@example.invalid" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "correct-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText("Something went wrong.")).toBeInTheDocument();
    });
    expect(pushMock).not.toHaveBeenCalled();
  });
});
