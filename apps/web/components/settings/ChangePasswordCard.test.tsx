/**
 * Settings > Security "Change password" form. Locks down: client-side
 * validation (required, policy, mismatch, new == current), the request
 * never naming an account, the fresh token being stored, the loading and
 * success states, and a safe message for each server failure.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const changePasswordMock = vi.fn();
const setTokenMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: { changePassword: (...args: unknown[]) => changePasswordMock(...args) },
  };
});

vi.mock("@/lib/auth-storage", () => ({ setToken: (t: string) => setTokenMock(t) }));

import { ApiError } from "@/lib/api";

import { ChangePasswordCard } from "./ChangePasswordCard";

const CURRENT = "Current-Password-123!";
const NEXT = "A-Brand-New-Password-456!";

function fill(current: string, next: string, confirm: string) {
  fireEvent.change(screen.getByLabelText("Current password"), { target: { value: current } });
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: next } });
  fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: confirm } });
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Change password" }));
}

function okResponse(verified = true) {
  return {
    access_token: "fresh-token",
    token_type: "bearer",
    user: { email: "owner@example.invalid", email_verified_at: verified ? "2026-09-01T00:00:00Z" : null },
  };
}

describe("ChangePasswordCard", () => {
  beforeEach(() => {
    changePasswordMock.mockReset();
    setTokenMock.mockReset();
  });
  afterEach(cleanup);

  it("renders three password fields, each with its own show/hide control", () => {
    render(<ChangePasswordCard />);
    for (const label of ["Current password", "New password", "Confirm new password"]) {
      expect(screen.getByLabelText(label)).toHaveAttribute("type", "password");
    }
    const toggles = screen.getAllByRole("button", { name: "Show password" });
    expect(toggles).toHaveLength(3);
    fireEvent.click(toggles[0]);
    expect(screen.getByLabelText("Current password")).toHaveAttribute("type", "text");
    expect(screen.getByLabelText("New password")).toHaveAttribute("type", "password");
  });

  it("uses the right autocomplete hints", () => {
    render(<ChangePasswordCard />);
    expect(screen.getByLabelText("Current password")).toHaveAttribute("autocomplete", "current-password");
    expect(screen.getByLabelText("New password")).toHaveAttribute("autocomplete", "new-password");
  });

  it("requires every field before calling the API", () => {
    render(<ChangePasswordCard />);
    submit();
    expect(screen.getByText("Enter your current password.")).toBeInTheDocument();
    expect(screen.getByText("Enter a new password.")).toBeInTheDocument();
    expect(screen.getByText("Confirm your new password.")).toBeInTheDocument();
    expect(screen.getByLabelText("Current password")).toHaveAttribute("aria-invalid", "true");
    expect(changePasswordMock).not.toHaveBeenCalled();
  });

  it("enforces the password policy on the new password", () => {
    render(<ChangePasswordCard />);
    fill(CURRENT, "weakpass", "weakpass");
    submit();
    expect(screen.getByText(/Password must include/)).toBeInTheDocument();
    expect(changePasswordMock).not.toHaveBeenCalled();
  });

  it("rejects a confirmation that doesn't match", () => {
    render(<ChangePasswordCard />);
    fill(CURRENT, NEXT, `${NEXT}x`);
    submit();
    expect(screen.getByText("The new passwords don't match.")).toBeInTheDocument();
    expect(changePasswordMock).not.toHaveBeenCalled();
  });

  it("rejects a new password equal to the current one", () => {
    render(<ChangePasswordCard />);
    fill(CURRENT, CURRENT, CURRENT);
    submit();
    expect(screen.getByText(/different from your current one/)).toBeInTheDocument();
    expect(changePasswordMock).not.toHaveBeenCalled();
  });

  it("sends only the two passwords, stores the fresh token and confirms success", async () => {
    let resolve: (value: unknown) => void = () => {};
    changePasswordMock.mockReturnValue(new Promise((r) => (resolve = r)));
    render(<ChangePasswordCard />);
    fill(CURRENT, NEXT, NEXT);
    submit();

    expect(changePasswordMock).toHaveBeenCalledWith(CURRENT, NEXT);
    expect(screen.getByRole("button", { name: "Changing password…" })).toBeDisabled();
    expect(screen.getByLabelText("Current password")).toBeDisabled();

    resolve(okResponse());
    expect(await screen.findByRole("status")).toHaveTextContent(/password has been changed/);
    expect(screen.getByRole("status")).toHaveTextContent(/confirmation has been sent/);
    expect(setTokenMock).toHaveBeenCalledWith("fresh-token");
    expect(screen.getByLabelText("Current password")).toHaveValue("");
    expect(screen.getByLabelText("New password")).toHaveValue("");
  });

  it("does not claim an email was sent to an unverified address", async () => {
    changePasswordMock.mockResolvedValue(okResponse(false));
    render(<ChangePasswordCard />);
    fill(CURRENT, NEXT, NEXT);
    submit();
    const status = await screen.findByRole("status");
    expect(status).not.toHaveTextContent(/confirmation/);
  });

  it.each([
    [400, "Your current password is incorrect."],
    [422, "This password doesn't meet the requirements below."],
    [429, /Too many incorrect attempts/],
    [500, /Something went wrong/],
  ])("shows a safe message for a %s", async (status, message) => {
    changePasswordMock.mockRejectedValue(new ApiError("failed", status));
    render(<ChangePasswordCard />);
    fill(CURRENT, NEXT, NEXT);
    submit();
    await waitFor(() => expect(screen.getByText(message)).toBeInTheDocument());
    expect(setTokenMock).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Change password" })).not.toBeDisabled();
  });
});
