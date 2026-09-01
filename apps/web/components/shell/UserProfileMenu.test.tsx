/**
 * Sprint 028 UAT-001 — the profile menu must show the actual signed-in
 * user's name/role/company, not a hardcoded placeholder identity. The
 * backend already returns the real `name`/`role`/`tenant_name` on every
 * auth response (app/auth/models.py); AuthProvider exposes `role` and
 * `tenantName` today but drops `name` entirely, and this component never
 * consumed any of them — it rendered a fixed `{ name: "Simo", role: "Owner" }`
 * regardless of who was actually logged in or which tenant they belonged to.
 */

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

let mockAuth: {
  name: string | null;
  role: string | null;
  tenantName: string | null;
  logout: () => void;
};

vi.mock("@/components/auth/AuthProvider", () => ({
  useAuth: () => mockAuth,
}));

import { UserProfileMenu } from "./UserProfileMenu";

afterEach(() => {
  cleanup();
});

describe("UserProfileMenu — Sprint 028 UAT-001", () => {
  it("renders_the_actual_signed_in_staff_users_name_role_and_tenant_not_a_placeholder", () => {
    mockAuth = {
      name: "Jordan Staff",
      role: "Staff",
      tenantName: "Riverside Stoneworks",
      logout: vi.fn(),
    };

    render(<UserProfileMenu />);

    expect(screen.getByText("Jordan Staff")).toBeInTheDocument();
    expect(screen.getByText("Staff")).toBeInTheDocument();
    expect(screen.queryByText("Simo")).not.toBeInTheDocument();
    expect(screen.queryByText("Owner")).not.toBeInTheDocument();
    expect(screen.queryByText("Simo Marble & Construction Ltd")).not.toBeInTheDocument();
  });

  it("renders_a_different_owners_own_name_and_tenant", async () => {
    mockAuth = {
      name: "Alex Owner",
      role: "Owner",
      tenantName: "Coastal Granite Co",
      logout: vi.fn(),
    };

    render(<UserProfileMenu />);
    await userEvent.click(screen.getByRole("button", { name: /Alex Owner/i }));

    expect(screen.getAllByText("Alex Owner").length).toBeGreaterThan(0);
    expect(screen.getByText("Coastal Granite Co")).toBeInTheDocument();
    expect(screen.queryByText("Simo")).not.toBeInTheDocument();
  });
});
