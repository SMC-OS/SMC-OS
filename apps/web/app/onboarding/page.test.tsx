import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const replaceMock = vi.fn();
const refreshMock = vi.fn();
const getOnboardingStateMock = vi.fn();
const getTradesMock = vi.fn();
const updateOnboardingMock = vi.fn();
const updateCompanyProfileMock = vi.fn();
const createInvitationMock = vi.fn();

// Stable router/provider mocks prevent an effect re-run on every render.
const router = { replace: replaceMock };
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/components/auth/AuthProvider", () => ({
  useAuth: () => ({
    isReady: true,
    isAuthenticated: true,
    tenantName: "Test Stoneworks",
  }),
}));
vi.mock("@/components/workspace/WorkspaceProvider", () => ({
  useWorkspace: () => ({ refresh: refreshMock }),
}));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      getOnboardingState: (...args: unknown[]) => getOnboardingStateMock(...args),
      getTrades: (...args: unknown[]) => getTradesMock(...args),
      updateOnboarding: (...args: unknown[]) => updateOnboardingMock(...args),
      updateCompanyProfile: (...args: unknown[]) => updateCompanyProfileMock(...args),
      createInvitation: (...args: unknown[]) => createInvitationMock(...args),
    },
  };
});

import OnboardingPage from "./page";

beforeEach(() => {
  replaceMock.mockReset();
  refreshMock.mockReset();
  getOnboardingStateMock.mockReset().mockResolvedValue({
    required: true,
    trades: [],
    currency: "GBP",
  });
  getTradesMock.mockReset().mockResolvedValue([]);
  updateOnboardingMock.mockReset();
  updateCompanyProfileMock.mockReset();
  createInvitationMock.mockReset();
});

afterEach(() => cleanup());

async function reachFinalStep() {
  render(<OnboardingPage />);
  await screen.findByText("What kind of work do you do?");
  fireEvent.click(screen.getByRole("button", { name: "Skip" }));
  await screen.findByRole("heading", { name: "Your company" });
  fireEvent.click(screen.getByRole("button", { name: "Skip" }));
  await screen.findByRole("heading", { name: "Bring your team in" });
  fireEvent.click(screen.getByRole("button", { name: "Skip" }));
  await screen.findByRole("button", { name: "Go to GeoCore" });
}

describe("new workspace onboarding completion integrity", () => {
  it("keeps the final screen and allows retry when completion persistence fails", async () => {
    updateOnboardingMock.mockRejectedValueOnce(new Error("Temporary failure"))
      .mockResolvedValueOnce({ onboarding_completed_at: "2026-11-02T00:00:00Z" });

    await reachFinalStep();
    fireEvent.click(screen.getByRole("button", { name: "Go to GeoCore" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not finish setup. Please try again."
    );
    expect(replaceMock).not.toHaveBeenCalledWith("/");
    expect(refreshMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Go to GeoCore" }));
    await waitFor(() => {
      expect(updateOnboardingMock).toHaveBeenCalledTimes(2);
      expect(updateOnboardingMock).toHaveBeenLastCalledWith({ complete: true });
      expect(replaceMock).toHaveBeenCalledWith("/");
    });
    expect(refreshMock).toHaveBeenCalledTimes(1);
  });

  it("only redirects after the completion write succeeds", async () => {
    let resolveCompletion!: (value: unknown) => void;
    updateOnboardingMock.mockImplementationOnce(() => new Promise((resolve) => {
      resolveCompletion = resolve;
    }));

    await reachFinalStep();
    fireEvent.click(screen.getByRole("button", { name: "Go to GeoCore" }));
    await waitFor(() => expect(updateOnboardingMock).toHaveBeenCalledWith({ complete: true }));
    expect(replaceMock).not.toHaveBeenCalled();

    resolveCompletion({ onboarding_completed_at: "2026-11-02T00:00:00Z" });
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/"));
    expect(refreshMock).toHaveBeenCalledTimes(1);
  });
});
