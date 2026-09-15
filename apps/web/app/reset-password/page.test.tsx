/**
 * Sprint 039 Production Readiness Defect Gate, Blocker 2.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";

const pushMock = vi.fn();
let currentToken: string | null = "a-real-token";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
  useSearchParams: () => new URLSearchParams(currentToken ? `token=${currentToken}` : ""),
}));

const resetPasswordMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: { resetPassword: (...args: unknown[]) => resetPasswordMock(...args) },
  };
});

import ResetPasswordPage from "./page";

beforeEach(() => {
  pushMock.mockClear();
  resetPasswordMock.mockReset();
  currentToken = "a-real-token";
});

afterEach(() => {
  cleanup();
});

function fillForm(password: string, confirmPassword: string) {
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: password } });
  fireEvent.change(screen.getByLabelText("Confirm new password"), {
    target: { value: confirmPassword },
  });
}

describe("ResetPasswordPage", () => {
  it("uses_independently_toggleable_new_password_fields", () => {
    render(<ResetPasswordPage />);
    const password = screen.getByLabelText("New password");
    const confirmation = screen.getByLabelText("Confirm new password");
    expect(password).toHaveAttribute("type", "password");
    expect(confirmation).toHaveAttribute("type", "password");
    expect(password).toHaveAttribute("autocomplete", "new-password");
    expect(confirmation).toHaveAttribute("autocomplete", "new-password");

    fireEvent.click(screen.getAllByRole("button", { name: "Show password" })[1]);
    expect(password).toHaveAttribute("type", "password");
    expect(confirmation).toHaveAttribute("type", "text");
  });

  it("submits_the_token_and_new_password_and_shows_success", async () => {
    resetPasswordMock.mockResolvedValue({ message: "ok" });

    render(<ResetPasswordPage />);
    fillForm("a-brand-new-password", "a-brand-new-password");
    fireEvent.click(screen.getByRole("button", { name: /^reset password$/i }));

    await waitFor(() => {
      expect(resetPasswordMock).toHaveBeenCalledWith("a-real-token", "a-brand-new-password");
    });
    await waitFor(() => {
      expect(screen.getByText(/your password has been reset/i)).toBeInTheDocument();
    });
  });

  it("rejects_mismatched_passwords_without_calling_the_api", async () => {
    render(<ResetPasswordPage />);
    fillForm("a-brand-new-password", "a-different-password");
    fireEvent.click(screen.getByRole("button", { name: /^reset password$/i }));

    await waitFor(() => {
      expect(screen.getByText(/don't match/i)).toBeInTheDocument();
    });
    expect(resetPasswordMock).not.toHaveBeenCalled();
  });

  it("shows_an_invalid_state_on_a_400_from_the_server", async () => {
    resetPasswordMock.mockRejectedValue(new ApiError("Bad request", 400));

    render(<ResetPasswordPage />);
    fillForm("a-brand-new-password", "a-brand-new-password");
    fireEvent.click(screen.getByRole("button", { name: /^reset password$/i }));

    await waitFor(() => {
      expect(screen.getByText(/invalid or has expired/i)).toBeInTheDocument();
    });
  });

  it("shows_a_no_token_state_when_the_link_has_no_token", () => {
    currentToken = null;
    render(<ResetPasswordPage />);
    expect(screen.getByText(/missing its token/i)).toBeInTheDocument();
  });
});
