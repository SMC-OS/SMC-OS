import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CONSENT_KEY } from "@/lib/consent";
vi.mock("@/lib/api", () => ({ api: { getMarketingPreference: vi.fn().mockResolvedValue({ enabled: false }), setMarketingPreference: vi.fn() } }));
import { PrivacyCard } from "./PrivacyCard";
afterEach(() => { cleanup(); localStorage.clear(); });
it("does not activate optional storage until Save browser preferences is clicked", async () => {
  localStorage.clear();
  render(<PrivacyCard />);
  await screen.findByText("Marketing email");
  fireEvent.click(screen.getByRole("checkbox", { name: /^Analytics$/ }));
  expect(localStorage.getItem(CONSENT_KEY)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Save browser preferences" }));
  expect(JSON.parse(localStorage.getItem(CONSENT_KEY)!)).toMatchObject({ essential: true, analytics: true, preferences: false, marketing: false });
  cleanup();
  render(<PrivacyCard />);
  expect(screen.getByRole("checkbox", { name: /^Analytics$/ })).toBeChecked();
});
