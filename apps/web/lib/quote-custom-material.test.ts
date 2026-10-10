import { beforeEach, expect, it } from "vitest";
import { readQuoteCustomMaterial, writeQuoteCustomMaterial } from "./quote-custom-material";

beforeEach(() => sessionStorage.clear());
it("retains price and dimensions across repeated draft reads/Refresh without placing them in the link", () => {
  const material = { canonical_name: "Synthetic quartz", material_family: "quartz" as const, variant: { slab_length_mm: 3000, slab_width_mm: 1400, thickness_mm: 20 }, buy_cost_per_slab: 400, selling_price_per_slab: 600, save_to_catalogue: false };
  const id = writeQuoteCustomMaterial(material);
  expect(id).toMatch(/^[a-f0-9-]{36}$/);
  expect(sessionStorage.getItem("geocore:quote-custom-material:" + id)).toContain('"selling_price_per_slab":600');
  expect(readQuoteCustomMaterial(id)).toEqual(material);
  expect(readQuoteCustomMaterial(id)).toEqual(material);
});
it("rejects a missing or malformed draft instead of substituting the default stone", () => {
  expect(() => readQuoteCustomMaterial("not-an-id")).toThrow(/invalid/);
  expect(() => readQuoteCustomMaterial(crypto.randomUUID())).toThrow(/no longer has/);
});
