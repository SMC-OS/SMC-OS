/**
 * Sprint 039 Production Readiness Defect Gate, Blocker 2 — structural
 * twin of app/login/page.test.tsx.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const forgotPasswordMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: { forgotPassword: (...args: unknown[]) => forgotPasswordMock(...args) },
  };
});

import ForgotPasswordPage from "./page";

beforeEach(() => {
  forgotPasswordMock.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("ForgotPasswordPage", () => {
  it("submits_the_email_and_shows_the_generic_confirmation", async () => {
    forgotPasswordMock.mockResolvedValue({ message: "sent" });

    render(<ForgotPasswordPage />);
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "owner@example.invalid" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send reset link/i }));

    await waitFor(() => {
      expect(forgotPasswordMock).toHaveBeenCalledWith("owner@example.invalid");
    });
    await waitFor(() => {
      expect(
        screen.getByText(/if an account exists for that email/i)
      ).toBeInTheDocument();
    });
  });

  it("shows_the_same_generic_confirmation_even_on_a_request_failure", async () => {
    // Sprint 039 Blocker 2's no-enumeration contract: the page itself
    // has no way to know why a call failed (rate limit, network, a real
    // 500), so it never surfaces anything more specific than the backend
    // route's own identical response would.
    forgotPasswordMock.mockRejectedValue(new Error("network error"));

    render(<ForgotPasswordPage />);
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "owner@example.invalid" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send reset link/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/if an account exists for that email/i)
      ).toBeInTheDocument();
    });
  });
});
