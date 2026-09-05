/**
 * Sprint 036 (Workstream G) — the Automations page.
 *
 * The binding constraint of this workstream is honesty: no automation
 * reaches a customer, because GeoCore has no channel to reach one
 * through. That fact is asserted here, and it is asserted against the
 * value the API returns rather than against hardcoded copy — so if
 * outbound delivery is ever genuinely built, this test does not have to
 * lie to keep passing.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const replaceMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock, push: vi.fn() }),
}));

let currentRole: string | null = "Owner";
vi.mock("@/components/auth/AuthProvider", () => ({
  useAuth: () => ({ isAuthenticated: true, isReady: true, role: currentRole }),
}));

const getAutomationsMock = vi.fn();
const getTemplatesMock = vi.fn();
const getMetaMock = vi.fn();
const getRunsMock = vi.fn();
const activateMock = vi.fn();
const updateMock = vi.fn();
const deleteMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      getAutomations: (...a: unknown[]) => getAutomationsMock(...a),
      getAutomationTemplates: (...a: unknown[]) => getTemplatesMock(...a),
      getAutomationMeta: (...a: unknown[]) => getMetaMock(...a),
      getAutomationRuns: (...a: unknown[]) => getRunsMock(...a),
      activateAutomationTemplate: (...a: unknown[]) => activateMock(...a),
      updateAutomation: (...a: unknown[]) => updateMock(...a),
      deleteAutomation: (...a: unknown[]) => deleteMock(...a),
    },
  };
});

import AutomationsPage from "./page";

const META = {
  triggers: [
    {
      key: "quote.approved",
      label: "Quote approved",
      description: "Runs when a quote is approved.",
      kind: "event" as const,
      subject_type: "quote",
    },
  ],
  actions: ["create_notification", "create_task", "draft_message", "create_project_from_quote"],
  operators: ["eq"],
  delivery: {
    external_delivery_available: false,
    note: "Automations act inside your workspace only. GeoCore does not send email, SMS or messages to customers; a drafted message is prepared for a person to review and send.",
  },
};

function automation(overrides: Record<string, unknown> = {}) {
  return {
    id: "automation-1",
    name: "Approved quote → project",
    description: null,
    template_key: "approved_quote_to_project",
    trigger_type: "quote.approved",
    conditions: [],
    actions: [{ type: "create_project_from_quote", config: {} }],
    enabled: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

beforeEach(() => {
  currentRole = "Owner";
  for (const mock of [
    getAutomationsMock,
    getTemplatesMock,
    getMetaMock,
    getRunsMock,
    activateMock,
    updateMock,
    deleteMock,
  ]) {
    mock.mockReset();
  }
  getAutomationsMock.mockResolvedValue([]);
  getTemplatesMock.mockResolvedValue([
    {
      key: "approved_quote_to_project",
      name: "Approved quote → project",
      description: "Turn an approved quote into a project automatically.",
      trigger_type: "quote.approved",
      conditions: [],
      actions: [{ type: "create_project_from_quote", config: {} }],
    },
  ]);
  getMetaMock.mockResolvedValue(META);
  getRunsMock.mockResolvedValue([]);
});

afterEach(() => cleanup());

describe("AutomationsPage — Sprint 036", () => {
  it("states that automations never contact a customer", async () => {
    render(<AutomationsPage />);

    await waitFor(() => {
      expect(screen.getByText(META.delivery.note)).toBeInTheDocument();
    });
  });

  it("turns a template into a real automation", async () => {
    const user = userEvent.setup();
    activateMock.mockResolvedValue(automation());

    render(<AutomationsPage />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Turn on" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Turn on" }));

    await waitFor(() => {
      expect(activateMock).toHaveBeenCalledWith("approved_quote_to_project");
    });
    // The list is re-read, not patched locally — the server's version of
    // the rule is the one the page then shows.
    expect(getAutomationsMock.mock.calls.length).toBeGreaterThan(1);
  });

  it("does not offer to turn on a template that is already on", async () => {
    getAutomationsMock.mockResolvedValue([automation()]);

    render(<AutomationsPage />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Already on" })).toBeDisabled();
    });
  });

  it("shows a failed run rather than hiding it", async () => {
    getRunsMock.mockResolvedValue([
      {
        id: "run-1",
        automation_id: "automation-1",
        trigger_type: "quote.approved",
        subject_type: "quote",
        subject_id: "quote-1",
        status: "failed",
        detail: "quote is not approved (status: draft)",
        created_at: new Date().toISOString(),
      },
    ]);

    render(<AutomationsPage />);

    await waitFor(() => {
      expect(screen.getByText("quote is not approved (status: draft)")).toBeInTheDocument();
    });
    expect(screen.getByText("failed")).toBeInTheDocument();
  });

  it("hides every write control from a Staff session", async () => {
    currentRole = "Staff";
    getAutomationsMock.mockResolvedValue([automation()]);

    render(<AutomationsPage />);
    await waitFor(() => {
      // Appears twice — once as the active rule, once as the template it
      // came from — so getAllByText is correct here, not a workaround.
      expect(screen.getAllByText("Approved quote → project").length).toBeGreaterThan(0);
    });

    // Reading what the system will do to your work is not a privilege;
    // authoring a workspace-wide rule is. The server enforces this for
    // real — this is the UI half.
    expect(screen.queryByRole("button", { name: "Turn on" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Turn off" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /build your own/i })).not.toBeInTheDocument();
  });

  it("explains a 403 rather than showing a generic failure", async () => {
    const user = userEvent.setup();
    const { ApiError } = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
    activateMock.mockRejectedValue(new ApiError("Forbidden", 403));

    render(<AutomationsPage />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Turn on" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Turn on" }));

    await waitFor(() => {
      expect(
        screen.getByText("Only the workspace owner can turn automations on.")
      ).toBeInTheDocument();
    });
  });
});
