/**
 * Sprint 027 (docs/SPRINTS/sprint-027.md §6.7) — the one surface a real
 * customer (not staff) ever touches had zero component-level coverage
 * despite tests/test_portal.py being the most thoroughly-covered backend
 * module (23 tests). Covers active/expired/revoked states, document list,
 * and the message thread.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useParams: () => ({ token: "portal-token-1" }),
}));

const getPortalByTokenMock = vi.fn();
const getPortalDocumentsMock = vi.fn();
const getPortalMessagesMock = vi.fn();
const postPortalMessageMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      getPortalByToken: (...args: unknown[]) => getPortalByTokenMock(...args),
      getPortalDocuments: (...args: unknown[]) => getPortalDocumentsMock(...args),
      getPortalMessages: (...args: unknown[]) => getPortalMessagesMock(...args),
      postPortalMessage: (...args: unknown[]) => postPortalMessageMock(...args),
      downloadPortalInvoice: vi.fn(),
      downloadPortalDocument: vi.fn(),
    },
  };
});

import ClientPortalPage from "./page";

function portal(overrides: Record<string, unknown> = {}) {
  return {
    status: "active",
    tenant_name: "Acme Stoneworks",
    customer_name: "Riverside Kitchens Ltd",
    expires_at: new Date(Date.now() + 86_400_000).toISOString(),
    projects: [],
    quotes: [],
    ...overrides,
  };
}

beforeEach(() => {
  getPortalByTokenMock.mockReset();
  getPortalDocumentsMock.mockReset();
  getPortalMessagesMock.mockReset();
  postPortalMessageMock.mockReset();
  getPortalDocumentsMock.mockResolvedValue([]);
  getPortalMessagesMock.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
});

describe("ClientPortalPage — Sprint 027 customer journey entry point", () => {
  it("renders_projects_quotes_documents_for_an_active_link", async () => {
    getPortalByTokenMock.mockResolvedValue(
      portal({
        projects: [
          {
            id: "project-1",
            name: "Riverside Kitchen",
            status: "booked",
            created_at: new Date().toISOString(),
          },
        ],
        quotes: [
          {
            id: "quote-1",
            material: "Quartz",
            thickness: "20mm",
            total: 4500,
            created_at: new Date().toISOString(),
          },
        ],
      })
    );
    getPortalDocumentsMock.mockResolvedValue([
      { id: "doc-1", original_filename: "sample.pdf", created_at: new Date().toISOString() },
    ]);

    render(<ClientPortalPage />);

    await waitFor(() => {
      expect(screen.getByText("Riverside Kitchen")).toBeInTheDocument();
    });
    expect(screen.getByText(/Quartz/)).toBeInTheDocument();
    expect(screen.getByText("sample.pdf")).toBeInTheDocument();
  });

  it("shows_a_revoked_state_and_renders_no_content_sections", async () => {
    getPortalByTokenMock.mockResolvedValue(portal({ status: "revoked" }));

    render(<ClientPortalPage />);

    await waitFor(() => {
      expect(screen.getByText(/This link has been revoked/)).toBeInTheDocument();
    });
    expect(screen.queryByText("Projects")).not.toBeInTheDocument();
  });

  it("shows_an_expired_state_and_renders_no_content_sections", async () => {
    getPortalByTokenMock.mockResolvedValue(portal({ status: "expired" }));

    render(<ClientPortalPage />);

    await waitFor(() => {
      expect(screen.getByText(/This link has expired/)).toBeInTheDocument();
    });
    expect(screen.queryByText("Projects")).not.toBeInTheDocument();
  });

  it("posts_a_customer_message_and_refetches_the_thread", async () => {
    getPortalByTokenMock.mockResolvedValue(portal());
    getPortalMessagesMock.mockResolvedValueOnce([]).mockResolvedValueOnce([
      {
        id: "message-1",
        body: "When can you visit?",
        sender_type: "customer",
        created_at: new Date().toISOString(),
      },
    ]);
    postPortalMessageMock.mockResolvedValue({});

    render(<ClientPortalPage />);

    await waitFor(() => {
      expect(screen.getByText("Messages")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("Write a message…"), {
      target: { value: "When can you visit?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^send$/i }));

    await waitFor(() => {
      expect(postPortalMessageMock).toHaveBeenCalledWith(
        "portal-token-1",
        "When can you visit?"
      );
    });
    await waitFor(() => {
      expect(screen.getByText("When can you visit?")).toBeInTheDocument();
    });
  });
});
