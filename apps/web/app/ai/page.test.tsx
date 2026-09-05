/**
 * Sprint 036 (Workstream H) — GeoCore AI.
 *
 * The page this replaced rendered raw JSON in a <pre> and named
 * `POST /process`, `BrainManager` and a sprint number in its own product
 * copy. The tests here are about the two things that must stay true:
 * developer internals never reach the interface, and the product never
 * claims a capability this deployment does not have.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const replaceMock = vi.fn();
let searchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock, push: vi.fn() }),
  useSearchParams: () => searchParams,
}));

vi.mock("@/components/auth/AuthProvider", () => ({
  useAuth: () => ({ isAuthenticated: true, isReady: true, role: "Owner" }),
}));

const capabilitiesMock = vi.fn();
const chatMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      getAICapabilities: (...a: unknown[]) => capabilitiesMock(...a),
      chatWithAI: (...a: unknown[]) => chatMock(...a),
    },
  };
});

import GeoCoreAIPage from "./page";

function capabilities(llm: boolean) {
  return {
    conversational: true,
    llm_configured: llm,
    workspace_context: llm,
    quote_drafting: llm,
    material_search: true,
    notes: [],
  };
}

beforeEach(() => {
  searchParams = new URLSearchParams();
  capabilitiesMock.mockReset();
  chatMock.mockReset();
  capabilitiesMock.mockResolvedValue(capabilities(true));
});

afterEach(() => cleanup());

describe("GeoCore AI — Sprint 036", () => {
  it("never shows developer internals in the interface", async () => {
    render(<GeoCoreAIPage />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "GeoCore AI" })).toBeInTheDocument();
    });

    for (const leak of [/BrainManager/i, /\/process/i, /Sprint \d/i, /endpoint/i]) {
      expect(screen.queryByText(leak)).not.toBeInTheDocument();
    }
    // And it is no longer called "AI Assistant".
    expect(screen.queryByText("AI Assistant")).not.toBeInTheDocument();
  });

  it("sends a message and renders the reply as a conversation", async () => {
    const user = userEvent.setup();
    chatMock.mockResolvedValue({ reply: "Two quotes need chasing.", engine: "llm" });

    render(<GeoCoreAIPage />);
    await waitFor(() => {
      expect(screen.getByLabelText("Ask GeoCore AI")).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText("Ask GeoCore AI"), "What needs my attention?");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(screen.getByText("Two quotes need chasing.")).toBeInTheDocument();
    });
    // Both sides of the exchange stay on screen.
    expect(screen.getByText("What needs my attention?")).toBeInTheDocument();
    expect(chatMock).toHaveBeenCalledWith([
      { role: "user", content: "What needs my attention?" },
    ]);
  });

  it("labels a built-in reply so a keyword matcher is never passed off as AI", async () => {
    const user = userEvent.setup();
    chatMock.mockResolvedValue({ reply: "Here's what I found.", engine: "builtin" });

    render(<GeoCoreAIPage />);
    await waitFor(() => {
      expect(screen.getByLabelText("Ask GeoCore AI")).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText("Ask GeoCore AI"), "quartz");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(screen.getByText("Built-in assistant")).toBeInTheDocument();
    });
  });

  it("says plainly when no AI provider is connected, and offers what does work", async () => {
    capabilitiesMock.mockResolvedValue(capabilities(false));

    render(<GeoCoreAIPage />);

    await waitFor(() => {
      expect(
        screen.getByText(/No AI provider is connected to this workspace yet/i)
      ).toBeInTheDocument();
    });
    // The suggestions offered are the ones the built-in assistant can
    // genuinely answer, not ones that will disappoint it.
    expect(
      screen.getByRole("button", { name: "What does 20mm quartz cost?" })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "What needs my attention today?" })
    ).not.toBeInTheDocument();
  });

  it("states that it cannot act, only answer", async () => {
    render(<GeoCoreAIPage />);

    await waitFor(() => {
      expect(
        screen.getByText(/can’t create, edit or send anything for you/i)
      ).toBeInTheDocument();
    });
  });

  it("asks a question handed to it in the URL exactly once", async () => {
    searchParams = new URLSearchParams("q=What+needs+my+attention%3F");
    chatMock.mockResolvedValue({ reply: "Nothing urgent.", engine: "llm" });

    render(<GeoCoreAIPage />);

    await waitFor(() => {
      expect(screen.getByText("Nothing urgent.")).toBeInTheDocument();
    });
    expect(chatMock).toHaveBeenCalledTimes(1);
  });

  it("shows a recoverable error rather than losing the conversation", async () => {
    const user = userEvent.setup();
    const { ApiError } = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
    chatMock.mockRejectedValue(new ApiError("boom", 500));

    render(<GeoCoreAIPage />);
    await waitFor(() => {
      expect(screen.getByLabelText("Ask GeoCore AI")).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText("Ask GeoCore AI"), "hello");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/couldn't answer/i);
    });
    // The question the user asked is still there to try again with.
    expect(screen.getByText("hello")).toBeInTheDocument();
  });
});
