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
}

describe("SignupPage — Sprint 027 full-system journey entry point", () => {
  it("submits_the_full_signup_payload_and_redirects_on_success", async () => {
    signupMock.mockResolvedValue(undefined);

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
