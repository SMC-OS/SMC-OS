/**
 * GeoCore Premium OS Plan 05 (Sprint 044), Task 40 — component coverage
 * for the Project 360 Materials tab: requirement list/create/cancel,
 * purchase order list/create, and that only the actions valid for a PO's
 * current status are ever shown (draft: approve; approved: mark as
 * ordered; ordered/partially_received: record delivery; cancelled/
 * received: terminal).
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MaterialRequirement, PurchaseOrder } from "@/types/procurement";

const getProjectRequirementsMock = vi.fn();
const createProjectRequirementMock = vi.fn();
const cancelRequirementMock = vi.fn();
const getPurchaseOrdersMock = vi.fn();
const createPurchaseOrderMock = vi.fn();
const getPurchaseOrderMock = vi.fn();
const approvePurchaseOrderMock = vi.fn();
const orderPurchaseOrderMock = vi.fn();
const cancelPurchaseOrderMock = vi.fn();
const recordPurchaseOrderReceiptMock = vi.fn();
const downloadPurchaseOrderPdfMock = vi.fn();
const getSuppliersMock = vi.fn();
// GeoCore Premium OS Plan 05 (Sprint 044), Task 35-36 — the "Suggested
// from quote & variations" section's own data sources.
const getQuoteMock = vi.fn();
const getProjectVariationsMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      getProjectRequirements: (...args: unknown[]) => getProjectRequirementsMock(...args),
      createProjectRequirement: (...args: unknown[]) => createProjectRequirementMock(...args),
      cancelRequirement: (...args: unknown[]) => cancelRequirementMock(...args),
      getPurchaseOrders: (...args: unknown[]) => getPurchaseOrdersMock(...args),
      createPurchaseOrder: (...args: unknown[]) => createPurchaseOrderMock(...args),
      getPurchaseOrder: (...args: unknown[]) => getPurchaseOrderMock(...args),
      approvePurchaseOrder: (...args: unknown[]) => approvePurchaseOrderMock(...args),
      orderPurchaseOrder: (...args: unknown[]) => orderPurchaseOrderMock(...args),
      cancelPurchaseOrder: (...args: unknown[]) => cancelPurchaseOrderMock(...args),
      recordPurchaseOrderReceipt: (...args: unknown[]) => recordPurchaseOrderReceiptMock(...args),
      downloadPurchaseOrderPdf: (...args: unknown[]) => downloadPurchaseOrderPdfMock(...args),
      getSuppliers: (...args: unknown[]) => getSuppliersMock(...args),
      getQuote: (...args: unknown[]) => getQuoteMock(...args),
      getProjectVariations: (...args: unknown[]) => getProjectVariationsMock(...args),
    },
  };
});

import { ProjectMaterialsPanel } from "./ProjectMaterialsPanel";

function requirement(overrides: Partial<MaterialRequirement> = {}): MaterialRequirement {
  return {
    id: "req-1",
    project_id: "project-1",
    description: "40mm quartz worktop slabs",
    catalogue_surface_id: null,
    catalogue_variant_id: null,
    custom_material_name: null,
    material_family: null,
    required_quantity: 3,
    unit: "slab",
    required_by_date: null,
    preferred_supplier_id: null,
    status: "required",
    notes: null,
    source_type: null,
    source_id: null,
    created_by_user_id: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function purchaseOrder(overrides: Partial<PurchaseOrder> = {}): PurchaseOrder {
  return {
    id: "po-1",
    project_id: "project-1",
    supplier_id: null,
    reference: "PO-001",
    status: "draft",
    order_date: null,
    expected_delivery_date: null,
    received_date: null,
    supplier_reference: null,
    notes: null,
    vat_rate: 0.2,
    subtotal: 1000,
    vat: 200,
    total: 1200,
    created_by_user_id: null,
    approved_by_user_id: null,
    approved_at: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    items: [
      {
        id: "poi-1",
        material_requirement_id: null,
        catalogue_surface_id: null,
        catalogue_variant_id: null,
        description: "Quartz slab",
        quantity: 3,
        unit: "slab",
        unit_cost: 333.33,
        line_total: 1000,
        quantity_received: 0,
      },
    ],
    is_late: false,
    ...overrides,
  };
}

beforeEach(() => {
  // No quote linked and no approved variations, by default — most tests
  // aren't exercising the "Suggested" section.
  getProjectVariationsMock.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ProjectMaterialsPanel", () => {
  it("renders_requirements_and_purchase_orders_from_the_backend", async () => {
    getProjectRequirementsMock.mockResolvedValue([requirement()]);
    getPurchaseOrdersMock.mockResolvedValue([purchaseOrder()]);
    getSuppliersMock.mockResolvedValue([]);

    render(<ProjectMaterialsPanel projectId="project-1" />);

    await waitFor(() => {
      expect(screen.getByText("40mm quartz worktop slabs")).toBeInTheDocument();
    });
    expect(screen.getByText("Required")).toBeInTheDocument();
    expect(screen.getByText("PO-001")).toBeInTheDocument();
    expect(screen.getByText("£1,200 total")).toBeInTheDocument();
    expect(getPurchaseOrdersMock).toHaveBeenCalledWith({ projectId: "project-1" });
  });

  it("creates_a_material_requirement", async () => {
    getProjectRequirementsMock.mockResolvedValue([]);
    getPurchaseOrdersMock.mockResolvedValue([]);
    getSuppliersMock.mockResolvedValue([]);
    createProjectRequirementMock.mockResolvedValue(requirement());

    render(<ProjectMaterialsPanel projectId="project-1" />);

    await waitFor(() => {
      expect(screen.getByText("No material requirements yet")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /add requirement/i }));
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "40mm quartz worktop slabs" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save requirement/i }));

    await waitFor(() => {
      expect(createProjectRequirementMock).toHaveBeenCalledWith(
        "project-1",
        expect.objectContaining({ description: "40mm quartz worktop slabs" })
      );
    });
    expect(await screen.findByText("40mm quartz worktop slabs")).toBeInTheDocument();
  });

  it("cancels_a_requirement_that_is_not_yet_terminal", async () => {
    getProjectRequirementsMock.mockResolvedValue([requirement()]);
    getPurchaseOrdersMock.mockResolvedValue([]);
    getSuppliersMock.mockResolvedValue([]);
    cancelRequirementMock.mockResolvedValue(requirement({ status: "cancelled" }));

    render(<ProjectMaterialsPanel projectId="project-1" />);

    await waitFor(() => {
      expect(screen.getByText("Required")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /cancel 40mm quartz worktop slabs/i }));

    await waitFor(() => {
      expect(cancelRequirementMock).toHaveBeenCalledWith("req-1");
    });
    expect(await screen.findByText("Cancelled")).toBeInTheDocument();
  });

  it("shows_approve_only_for_a_draft_purchase_order", async () => {
    getProjectRequirementsMock.mockResolvedValue([]);
    getPurchaseOrdersMock.mockResolvedValue([purchaseOrder({ status: "approved" })]);
    getSuppliersMock.mockResolvedValue([]);

    render(<ProjectMaterialsPanel projectId="project-1" />);

    await waitFor(() => {
      expect(screen.getByText("PO-001")).toBeInTheDocument();
    });

    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /mark as ordered/i })).toBeInTheDocument();
  });

  it("approves_a_draft_purchase_order", async () => {
    getProjectRequirementsMock.mockResolvedValue([]);
    getPurchaseOrdersMock.mockResolvedValue([purchaseOrder()]);
    getSuppliersMock.mockResolvedValue([]);
    approvePurchaseOrderMock.mockResolvedValue(
      purchaseOrder({ status: "approved", approved_at: "2026-01-02T00:00:00Z" })
    );

    render(<ProjectMaterialsPanel projectId="project-1" />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() => {
      expect(approvePurchaseOrderMock).toHaveBeenCalledWith("po-1");
    });
    expect(await screen.findByText("Approved")).toBeInTheDocument();
  });

  it("records_a_delivery_against_an_ordered_purchase_order", async () => {
    getProjectRequirementsMock.mockResolvedValue([]);
    getPurchaseOrdersMock.mockResolvedValue([purchaseOrder({ status: "ordered" })]);
    getSuppliersMock.mockResolvedValue([]);
    recordPurchaseOrderReceiptMock.mockResolvedValue({});
    getPurchaseOrderMock.mockResolvedValue(
      purchaseOrder({
        status: "received",
        items: [
          {
            id: "poi-1",
            material_requirement_id: null,
            catalogue_surface_id: null,
            catalogue_variant_id: null,
            description: "Quartz slab",
            quantity: 3,
            unit: "slab",
            unit_cost: 333.33,
            line_total: 1000,
            quantity_received: 3,
          },
        ],
      })
    );

    render(<ProjectMaterialsPanel projectId="project-1" />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /record delivery/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /record delivery/i }));
    fireEvent.click(screen.getByRole("button", { name: /save delivery/i }));

    await waitFor(() => {
      expect(recordPurchaseOrderReceiptMock).toHaveBeenCalledWith(
        "po-1",
        expect.objectContaining({
          items: [expect.objectContaining({ purchase_order_item_id: "poi-1", quantity_received: 3 })],
        })
      );
    });
    expect(await screen.findByText("Received")).toBeInTheDocument();
  });

  // GeoCore Premium OS Plan 05 (Sprint 044), Task 35-36 — "Send to
  // procurement" is an editorial suggestion only: nothing is created
  // until the user presses the button for that specific line.
  it("suggests_a_catalogue_linked_quote_line_and_sends_it_to_procurement_on_request", async () => {
    getProjectRequirementsMock.mockResolvedValue([]);
    getPurchaseOrdersMock.mockResolvedValue([]);
    getSuppliersMock.mockResolvedValue([]);
    getQuoteMock.mockResolvedValue({
      id: "quote-1",
      items: [
        {
          id: "quote-item-1",
          line_kind: "stone",
          description: null,
          material: "Calacatta Oro",
          thickness: "20mm",
          quantity: 1,
          unit: null,
          slabs: 2,
          catalogue_surface_id: "surface-1",
          catalogue_variant_id: "variant-1",
        },
      ],
    });
    createProjectRequirementMock.mockResolvedValue(requirement({ description: "Calacatta Oro 20mm" }));

    render(<ProjectMaterialsPanel projectId="project-1" quoteId="quote-1" />);

    await waitFor(() => {
      expect(screen.getByText("Calacatta Oro 20mm")).toBeInTheDocument();
    });
    expect(screen.getByText(/From this project's quote/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /send to procurement/i }));

    await waitFor(() => {
      expect(createProjectRequirementMock).toHaveBeenCalledWith(
        "project-1",
        expect.objectContaining({
          description: "Calacatta Oro 20mm",
          catalogue_surface_id: "surface-1",
          catalogue_variant_id: "variant-1",
          required_quantity: 2,
          unit: "slab",
          source_type: "quote",
        })
      );
    });
    // Sent once — the suggestion disappears rather than staying offered.
    await waitFor(() => {
      expect(screen.queryByText(/From this project's quote/)).not.toBeInTheDocument();
    });
  });

  it("offers_no_further_actions_other_than_pdf_for_a_terminal_purchase_order", async () => {
    getProjectRequirementsMock.mockResolvedValue([]);
    getPurchaseOrdersMock.mockResolvedValue([purchaseOrder({ status: "received" })]);
    getSuppliersMock.mockResolvedValue([]);

    render(<ProjectMaterialsPanel projectId="project-1" />);

    await waitFor(() => {
      expect(screen.getByText("PO-001")).toBeInTheDocument();
    });

    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /mark as ordered/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /record delivery/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /cancel po-001/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /download pdf/i })).toBeInTheDocument();
  });
});
