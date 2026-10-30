import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import PrivacyControlsPage from "./page";

const { replace, download, state } = vi.hoisted(() => ({
  replace: vi.fn(),
  download: vi.fn(),
  state: {
    isReady: true,
    isAuthenticated: true,
    verificationRequired: false,
    billingAccessRequired: true,
    role: "Owner",
  },
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
vi.mock("@/components/auth/AuthProvider", () => ({ useAuth: () => state }));
vi.mock("@/components/settings/PrivacyCard", () => ({
  PrivacyCard: () => <div>Consent controls</div>,
}));
vi.mock("@/lib/api", () => ({ api: { downloadWorkspaceExport: download } }));
beforeEach(() => {
  replace.mockClear();
  download.mockReset();
  state.isAuthenticated = true;
  state.verificationRequired = false;
  state.role = "Owner";
});
afterEach(cleanup);

it("allows an expired owner to request a metadata export explicitly", async () => {
  download.mockResolvedValue(undefined);
  render(<PrivacyControlsPage />);
  expect(screen.getByText("Consent controls")).toBeVisible();
  expect(download).not.toHaveBeenCalled();
  await userEvent.click(
    screen.getByRole("button", { name: "Download workspace metadata" }),
  );
  await waitFor(() => expect(download).toHaveBeenCalledTimes(1));
});
it("does not offer an owner export to staff", () => {
  state.role = "Staff";
  render(<PrivacyControlsPage />);
  expect(
    screen.queryByRole("button", { name: "Download workspace metadata" }),
  ).not.toBeInTheDocument();
  expect(screen.getByText("Consent controls")).toBeVisible();
});
it("redirects a signed-out visitor without showing private controls", () => {
  state.isAuthenticated = false;
  render(<PrivacyControlsPage />);
  expect(replace).toHaveBeenCalledWith("/login");
  expect(screen.queryByText("Consent controls")).not.toBeInTheDocument();
});
it("does not show private controls before verification", () => {
  state.verificationRequired = true;
  render(<PrivacyControlsPage />);
  expect(screen.queryByText("Consent controls")).not.toBeInTheDocument();
});
it("reports an export failure without claiming success", async () => {
  download.mockRejectedValue(new Error("unavailable"));
  render(<PrivacyControlsPage />);
  await userEvent.click(
    screen.getByRole("button", { name: "Download workspace metadata" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Could not download",
  );
});
