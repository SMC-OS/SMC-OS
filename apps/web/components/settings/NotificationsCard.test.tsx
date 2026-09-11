/**
 * Notification settings UI contract (Sprint 039, Workstream B).
 *
 * What must stay true, and what the Sprint 036 version got wrong:
 *
 *   1. The category list comes from the server, so this screen can never
 *      offer a switch for something GeoCore does not produce.
 *   2. A change is persisted through the API, not into `localStorage`.
 *   3. The card no longer claims GeoCore cannot send email — it has been
 *      able to since Sprint 038.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearToken, setToken } from "@/lib/auth-storage";

import { NotificationsCard } from "./NotificationsCard";

const PREFERENCES = [
  {
    category: "quote_activity",
    label: "Quote activity",
    description: "When a quote is approved, or is about to expire.",
    in_app: true,
    email: false,
  },
  {
    category: "communication_failure",
    label: "Delivery failures",
    description: "When an email to one of your customers bounces.",
    in_app: true,
    email: false,
  },
];

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.endsWith("/notifications/preferences") && init?.method === "PUT") {
      const body = JSON.parse(init.body as string) as {
        preferences: { category: string; in_app: boolean; email: boolean }[];
      };
      const changed = body.preferences[0];
      return jsonResponse(
        PREFERENCES.map((preference) =>
          preference.category === changed.category ? { ...preference, ...changed } : preference
        )
      );
    }
    if (url.endsWith("/notifications/preferences")) {
      return jsonResponse(PREFERENCES);
    }
    throw new Error(`Unexpected fetch in test: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  setToken("pytest-owner-token");
});

afterEach(() => {
  cleanup();
  clearToken();
  vi.unstubAllGlobals();
});

describe("NotificationsCard — Sprint 039", () => {
  it("renders_the_categories_the_server_says_exist", async () => {
    render(<NotificationsCard />);

    expect(await screen.findByText("Quote activity")).toBeInTheDocument();
    expect(screen.getByText("Delivery failures")).toBeInTheDocument();
  });

  it("offers_both_channels_for_every_category", async () => {
    render(<NotificationsCard />);

    expect(
      await screen.findByRole("checkbox", { name: /quote activity in the app/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("checkbox", { name: /quote activity by email/i })
    ).toBeInTheDocument();
  });

  it("starts_with_email_off_so_nobody_is_opted_in_by_an_upgrade", async () => {
    render(<NotificationsCard />);

    const emailToggle = await screen.findByRole("checkbox", {
      name: /quote activity by email/i,
    });
    expect(emailToggle).not.toBeChecked();
  });

  it("persists_a_change_through_the_api_not_into_this_browser", async () => {
    render(<NotificationsCard />);

    await userEvent.click(
      await screen.findByRole("checkbox", { name: /quote activity in the app/i })
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/notifications/preferences"),
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({
            preferences: [{ category: "quote_activity", in_app: false, email: false }],
          }),
        })
      );
    });
  });

  it("applies_the_servers_returned_state_after_a_save", async () => {
    render(<NotificationsCard />);

    const toggle = await screen.findByRole("checkbox", {
      name: /quote activity in the app/i,
    });
    await userEvent.click(toggle);

    await waitFor(() => expect(toggle).not.toBeChecked());
  });

  it("no_longer_claims_geocore_cannot_send_email", async () => {
    // Sprint 036's copy said "It doesn't send email, SMS or push
    // notifications yet". That has been false since Sprint 038 shipped.
    render(<NotificationsCard />);

    await screen.findByText("Quote activity");

    expect(screen.queryByText(/doesn.t send email/i)).not.toBeInTheDocument();
    expect(screen.getByText(/SMS or push/i)).toBeInTheDocument();
  });

  it("shows_a_real_error_state_rather_than_an_empty_panel", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ detail: "boom" }, 500));
    render(<NotificationsCard />);

    expect(
      await screen.findByText(/couldn.t load your notification settings/i)
    ).toBeInTheDocument();
  });
});
