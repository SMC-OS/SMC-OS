/**
 * Sprint 027 (docs/SPRINTS/sprint-027.md §6.4) — structural twin of
 * app/login/page.test.tsx.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

const signupMock = vi.fn();

vi.mock("@/components/auth/AuthProvider", () => ({
  useAuth: () => ({ signup: signupMock }),
}));

import SignupPage from "./page";

beforeEach(() => {
  pushMock.mockClear();
  signupMock.mockReset();
});

afterEach(() => {
  cleanup();
});

function fillForm() {
  fireEvent.change(screen.getByLabelText("Company name"), {
    target: { value: "Acme Stoneworks" },
  });
  fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Jane Doe" } });
  fireEvent.change(screen.getByLabelText("Email"), {
    target: { value: "jane@acmestoneworks.invalid" },
  });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "a-real-password" } });
  fireEvent.change(screen.getByLabelText("Confirm password"), {
    target: { value: "a-real-password" },
  });
}

describe("SignupPage — Sprint 027 full-system journey entry point", () => {
  it("masks_both_passwords_and_toggles_each_field_independently", () => {
    render(<SignupPage />);

    const password = screen.getByLabelText("Password");
    const confirmation = screen.getByLabelText("Confirm password");
    expect(password).toHaveAttribute("type", "password");
    expect(confirmation).toHaveAttribute("type", "password");
    expect(password).toHaveAttribute("autocomplete", "new-password");
    expect(confirmation).toHaveAttribute("autocomplete", "new-password");

    fireEvent.change(password, { target: { value: "kept-secret" } });
    fireEvent.change(confirmation, { target: { value: "other-secret" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Show password" })[0]);
    expect(password).toHaveAttribute("type", "text");
    expect(confirmation).toHaveAttribute("type", "password");
    expect(password).toHaveValue("kept-secret");
    expect(confirmation).toHaveValue("other-secret");

    fireEvent.click(screen.getByRole("button", { name: "Hide password" }));
    expect(password).toHaveAttribute("type", "password");
  });

  it("blocks_empty_or_mismatched_confirmation_without_sending_credentials", async () => {
    render(<SignupPage />);
    fillForm();
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "" } });
    fireEvent.submit(screen.getByRole("button", { name: /create workspace/i }).closest("form")!);
    expect(await screen.findByText("Passwords do not match.")).toBeInTheDocument();
    expect(signupMock).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "a-different-password" },
    });
    fireEvent.submit(screen.getByRole("button", { name: /create workspace/i }).closest("form")!);
    expect(signupMock).not.toHaveBeenCalled();
  });

  it("submits_the_full_signup_payload_and_redirects_to_onboarding_when_already_verified", async () => {
    // e.g. a legacy-grace-exempt account, or verification disabled in a
    // given environment — signup() resolving false means normal access.
    signupMock.mockResolvedValue(false);

    render(<SignupPage />);
    fillForm();
    fireEvent.click(screen.getByRole("button", { name: /create workspace/i }));

    await waitFor(() => {
      expect(signupMock).toHaveBeenCalledWith({
        company_name: "Acme Stoneworks",
        name: "Jane Doe",
        email: "jane@acmestoneworks.invalid",
        password: "a-real-password",
      });
    });
    // Sprint 036 (Workstream J) — a brand-new workspace lands on setup
    // rather than on an empty customer list. /onboarding sends an
    // already-established workspace straight through, so nobody who is
    // already working is sent back to a wizard.
    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/onboarding");
    });
  });

  // Sprint 039 Production Readiness Defect Gate, Blocker 2 hotfix — the
  // real, normal case: a brand-new signup is unverified and must land on
  // the verification screen, not straight into the workspace.
  it("redirects_to_verify_email_when_the_new_account_is_unverified", async () => {
    signupMock.mockResolvedValue(true);

    render(<SignupPage />);
    fillForm();
    fireEvent.click(screen.getByRole("button", { name: /create workspace/i }));

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/verify-email");
    });
  });

  it("shows_a_specific_error_on_409_conflict_and_never_redirects", async () => {
    signupMock.mockRejectedValue(new ApiError("Conflict", 409));

    render(<SignupPage />);
    fillForm();
    fireEvent.click(screen.getByRole("button", { name: /create workspace/i }));

    await waitFor(() => {
      expect(
        screen.getByText("An account with that email already exists.")
      ).toBeInTheDocument();
    });
    expect(pushMock).not.toHaveBeenCalled();
  });
});
