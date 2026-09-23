/**
 * Post-release remediation §2 — the command palette previously offered
 * only static nav/quick-action/settings entries; a user could not jump
 * to a specific existing project by name.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearToken, setToken } from "@/lib/auth-storage";

import { CommandPalette } from "./CommandPalette";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  pushMock.mockClear();
  fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.includes("/projects")) {
      return jsonResponse([
        { id: "project-1", name: "Riverside Kitchen Renovation" },
        { id: "project-2", name: "Oakwood Bathroom Refit" },
      ]);
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

describe("CommandPalette — project search", () => {
  it("fetches projects once opened and lists them under a Projects group", async () => {
    render(<CommandPalette open={true} onOpenChange={vi.fn()} />);

    expect(await screen.findByText("Riverside Kitchen Renovation")).toBeInTheDocument();
    expect(screen.getByText("Oakwood Bathroom Refit")).toBeInTheDocument();
    // "Projects" also appears as the static nav item's own label — the
    // group heading is the uppercase-tracked one, not a clickable button.
    const groupHeading = screen.getAllByText("Projects").find((el) => el.tagName === "P");
    expect(groupHeading).toBeTruthy();
  });

  it("filters to a matching project and navigates to it on click", async () => {
    render(<CommandPalette open={true} onOpenChange={vi.fn()} />);

    await screen.findByText("Riverside Kitchen Renovation");

    await userEvent.type(screen.getByPlaceholderText(/search pages and actions/i), "Riverside");

    expect(screen.getByText("Riverside Kitchen Renovation")).toBeInTheDocument();
    expect(screen.queryByText("Oakwood Bathroom Refit")).not.toBeInTheDocument();

    await userEvent.click(screen.getByText("Riverside Kitchen Renovation"));

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/projects/project-1");
    });
  });

  it("does not fetch projects while closed", () => {
    render(<CommandPalette open={false} onOpenChange={vi.fn()} />);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
