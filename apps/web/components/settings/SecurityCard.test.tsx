import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
const getMe = vi.fn();
vi.mock("@/components/auth/AuthProvider", () => ({ useAuth: () => ({ role: "Owner", logout: vi.fn() }) }));
vi.mock("@/components/settings/ChangePasswordCard", () => ({ ChangePasswordCard: () => null }));
vi.mock("@/lib/api", async () => ({ ...await vi.importActual<typeof import("@/lib/api")>("@/lib/api"), api: { getMe: () => getMe() } }));
import { SecurityCard } from "./SecurityCard";
afterEach(() => { cleanup(); vi.clearAllMocks(); });
it("does not falsely classify a loading identity as unverified", async () => {
  let resolve: (value: unknown) => void = () => {};
  getMe.mockReturnValue(new Promise((done) => { resolve = done; }));
  render(<SecurityCard />);
  expect(screen.getByText("Loading…")).toBeInTheDocument();
  expect(screen.queryByText("Unverified")).not.toBeInTheDocument();
  resolve({ name: "Synthetic Owner", email: "owner@example.invalid", email_verified_at: "2026-10-10T00:00:00Z" });
  expect(await screen.findByText("Verified")).toBeInTheDocument();
});
it("shows a failed identity request instead of suppressing it or claiming unverified", async () => {
  getMe.mockRejectedValue(new Error("synthetic request failure"));
  render(<SecurityCard />);
  expect(await screen.findByText("Unavailable")).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("Could not load your account details");
  expect(screen.queryByText("Unverified")).not.toBeInTheDocument();
});
