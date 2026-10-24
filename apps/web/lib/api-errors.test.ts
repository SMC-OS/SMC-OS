import { afterEach, expect, it, vi } from "vitest";
import { api } from "./api";

afterEach(() => vi.unstubAllGlobals());

it("shows the server's actionable quote rejection instead of only HTTP 400", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail:
            "No price is set for 'My marble'. Set a selling price before quoting.",
        }),
        { status: 400 },
      ),
    ),
  );
  await expect(
    api.createQuote({ customer: "Pilot", items: [] }),
  ).rejects.toThrow(
    "No price is set for 'My marble'. Set a selling price before quoting.",
  );
});

it("keeps a useful fallback for a non-JSON rejection", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(new Response("upstream unavailable", { status: 502 })),
  );
  await expect(api.getCatalogueStatus()).rejects.toThrow(
    "Request to /catalogue/meta/status failed with 502",
  );
});
