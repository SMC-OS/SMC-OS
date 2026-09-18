/**
 * GeoCore Premium OS Plan 04 (Sprint 043), Task 28 — component coverage
 * for the Project 360 Variations tab: list rendering, create-draft flow,
 * and that only the actions valid for a variation's current status are
 * ever shown (draft/sent can approve/reject/void; approved/rejected/void
 * are terminal, PDF-only).
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Variation } from "@/types/variation";

const getProjectVariationsMock = vi.fn();
const createVariationMock = vi.fn();
const sendVariationMock = vi.fn();
const approveVariationMock = vi.fn();
const rejectVariationMock = vi.fn();
const voidVariationMock = vi.fn();
const downloadVariationPdfMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      getProjectVariations: (...args: unknown[]) => getProjectVariationsMock(...args),
      createVariation: (...args: unknown[]) => createVariationMock(...args),
      sendVariation: (...args: unknown[]) => sendVariationMock(...args),
      approveVariation: (...args: unknown[]) => approveVariationMock(...args),
      rejectVariation: (...args: unknown[]) => rejectVariationMock(...args),
      voidVariation: (...args: unknown[]) => voidVariationMock(...args),
      downloadVariationPdf: (...args: unknown[]) => downloadVariationPdfMock(...args),
    },
  };
});

import { ProjectVariationsPanel } from "./ProjectVariationsPanel";

function variation(overrides: Partial<Variation> = {}): Variation {
  return {
    id: "variation-1",
    project_id: "project-1",
    reference: "V-001",
    title: "Additional tiling",
    description: null,
    status: "draft",
    vat_rate: 0.2,
    subtotal: 100,
    vat: 20,
    total: 120,
    requested_by: null,
    approved_at: null,
    approved_by_user_id: null,
    created_by_user_id: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    items: [],
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ProjectVariationsPanel", () => {
  it("renders_a_variation_by_its_human_readable_reference", async () => {
    getProjectVariationsMock.mockResolvedValue([variation()]);

    render(<ProjectVariationsPanel projectId="project-1" />);

    await waitFor(() => {
      expect(screen.getByText(/V-001/)).toBeInTheDocument();
    });
    expect(screen.getByText("£120 total")).toBeInTheDocument();
    expect(screen.getByText("Draft")).toBeInTheDocument();
  });

  it("shows_no_action_buttons_other_than_pdf_for_a_terminal_status", async () => {
    getProjectVariationsMock.mockResolvedValue([variation({ status: "approved" })]);

    render(<ProjectVariationsPanel projectId="project-1" />);

    await waitFor(() => {
      expect(screen.getByText(/V-001/)).toBeInTheDocument();
    });

    expect(screen.queryByRole("button", { name: "Send" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /download pdf/i })).toBeInTheDocument();
  });

  it("offers_send_only_from_draft_not_from_sent", async () => {
    getProjectVariationsMock.mockResolvedValue([variation({ status: "sent" })]);

    render(<ProjectVariationsPanel projectId="project-1" />);

    await waitFor(() => {
      expect(screen.getByText(/V-001/)).toBeInTheDocument();
    });

    expect(screen.queryByRole("button", { name: "Send" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
  });

  it("creates_a_draft_variation_with_line_items", async () => {
    getProjectVariationsMock.mockResolvedValue([]);
    createVariationMock.mockResolvedValue(variation());

    render(<ProjectVariationsPanel projectId="project-1" />);

    await waitFor(() => {
      expect(screen.getByText("No variations yet")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /new variation/i }));
    fireEvent.change(screen.getByLabelText("Title"), {
      target: { value: "Additional tiling" },
    });
    fireEvent.change(screen.getByLabelText("Item description"), {
      target: { value: "Extra tiles" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save draft/i }));

    await waitFor(() => {
      expect(createVariationMock).toHaveBeenCalledWith(
        "project-1",
        expect.objectContaining({
          title: "Additional tiling",
          items: expect.arrayContaining([expect.objectContaining({ description: "Extra tiles" })]),
        })
      );
    });
    expect(await screen.findByText(/V-001/)).toBeInTheDocument();
  });

  it("approves_a_variation", async () => {
    getProjectVariationsMock.mockResolvedValue([variation()]);
    approveVariationMock.mockResolvedValue(variation({ status: "approved", approved_at: "2026-01-02T00:00:00Z" }));

    render(<ProjectVariationsPanel projectId="project-1" />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() => {
      expect(approveVariationMock).toHaveBeenCalledWith("variation-1");
    });
    expect(await screen.findByText("Approved")).toBeInTheDocument();
  });
});
