/**
 * Sprint 024 — frontend follow-up automation contract: notification
 * navigation, recipient-scoped visibility, and mark-read failure safety
 * (mirrors the backend's per-recipient scoping,
 * tests/test_follow_up_automation.py). First component test for
 * NotificationsPanel.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearToken, setToken } from "@/lib/auth-storage";

import { NotificationsPanel } from "./NotificationsPanel";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

function makeNotification(overrides: Record<string, unknown> = {}) {
  return {
    id: "notification-1",
    title: "Enquiry needs follow-up",
    message: "Riverside Kitchen has had no progress since it was created.",
    type: "warning",
    timestamp: new Date().toISOString(),
    read: false,
    source_type: "project",
    source_id: "project-1",
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

let fetchMock: ReturnType<typeof vi.fn>;
let currentNotifications: Record<string, unknown>[] = [];

beforeEach(() => {
  currentNotifications = [makeNotification()];
  fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();

    if (url.endsWith("/notifications/notification-1/read") && init?.method === "PATCH") {
      return jsonResponse({ ...currentNotifications[0], read: true });
    }
    if (url.includes("/notifications")) {
      return jsonResponse(currentNotifications);
    }
    throw new Error(`Unexpected fetch in test: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  setToken("pytest-owner-token");
  pushMock.mockClear();
});

afterEach(() => {
  cleanup();
  clearToken();
  vi.unstubAllGlobals();
});

describe("NotificationsPanel — follow-up automation (Sprint 024)", () => {
  it("clicking_a_sourced_notification_marks_it_read_and_navigates_to_the_project", async () => {
    render(<NotificationsPanel />);

    const bell = await screen.findByRole("button", { name: /notifications/i });
    await userEvent.click(bell);

    const notification = await screen.findByText("Enquiry needs follow-up");
    await userEvent.click(notification);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/notifications/notification-1/read"),
        expect.objectContaining({ method: "PATCH" })
      );
    });

    // Navigation uses the server-provided source_id, never a client-
    // supplied URL, and only fires for a known source_type.
    expect(pushMock).toHaveBeenCalledWith("/projects/project-1");
  });

  it("clicking_a_notification_with_no_source_only_marks_it_read", async () => {
    currentNotifications = [
      makeNotification({ id: "broadcast-1", source_type: null, source_id: null }),
    ];
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/notifications/broadcast-1/read") && init?.method === "PATCH") {
        return jsonResponse({ ...currentNotifications[0], read: true });
      }
      if (url.includes("/notifications")) {
        return jsonResponse(currentNotifications);
      }
      throw new Error(`Unexpected fetch in test: ${url}`);
    });

    render(<NotificationsPanel />);
    await userEvent.click(await screen.findByRole("button", { name: /notifications/i }));
    await userEvent.click(await screen.findByText("Enquiry needs follow-up"));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/notifications/broadcast-1/read"),
        expect.objectContaining({ method: "PATCH" })
      );
    });

    // Existing tenant-wide-broadcast behavior (no source) is unchanged —
    // nothing to navigate to, so nothing navigates.
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("navigates_even_when_marking_read_fails_but_leaves_the_notification_unread", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/notifications/notification-1/read") && init?.method === "PATCH") {
        return jsonResponse({ detail: "failed" }, 500);
      }
      if (url.includes("/notifications")) {
        return jsonResponse(currentNotifications);
      }
      throw new Error(`Unexpected fetch in test: ${url}`);
    });

    render(<NotificationsPanel />);
    await userEvent.click(await screen.findByRole("button", { name: /notifications/i }));
    await userEvent.click(await screen.findByText("Enquiry needs follow-up"));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/notifications/notification-1/read"),
        expect.objectContaining({ method: "PATCH" })
      );
    });

    // A failed mark-read must never block reaching the linked entity.
    expect(pushMock).toHaveBeenCalledWith("/projects/project-1");

    // Navigating closed the panel — reopen it to confirm the read state
    // was never faked client-side: it's still shown as unread since the
    // server never confirmed the mark-read.
    await userEvent.click(await screen.findByRole("button", { name: /notifications/i }));
    const reopened = await screen.findByText("Enquiry needs follow-up");
    const unreadDot = reopened.closest("button")?.querySelector(".bg-accent");
    expect(unreadDot).not.toBeNull();
  });

  it("clicking_an_already_read_notification_still_navigates_without_re_marking_it", async () => {
    currentNotifications = [makeNotification({ read: true })];

    render(<NotificationsPanel />);
    await userEvent.click(await screen.findByRole("button", { name: /notifications/i }));
    await userEvent.click(await screen.findByText("Enquiry needs follow-up"));

    expect(pushMock).toHaveBeenCalledWith("/projects/project-1");
    // No PATCH call for an already-read notification.
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining("/read"),
      expect.anything()
    );
  });
});
