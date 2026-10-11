import type { CustomMaterialInput } from "@/types/catalogue";

const PREFIX = "geocore:quote-custom-material:";

/** Non-authentication draft data, kept in this tab so buy/sell prices never
 * enter the URL or HTTP logs. It survives Refresh and is never a reusable
 * catalogue entry. The API validates and snapshots it when a quote is saved. */
export function writeQuoteCustomMaterial(material: CustomMaterialInput): string {
  const id = crypto.randomUUID();
  sessionStorage.setItem(PREFIX + id, JSON.stringify({ ...material, save_to_catalogue: false }));
  return id;
}

export function readQuoteCustomMaterial(id: string): CustomMaterialInput {
  if (!/^[a-f0-9-]{36}$/i.test(id)) throw new Error("This custom material draft link is invalid. Return to the Catalogue and select it again.");
  const raw = sessionStorage.getItem(PREFIX + id);
  if (!raw) throw new Error("This tab no longer has the custom material draft. Return to the Catalogue and enter it again.");
  const material = JSON.parse(raw) as CustomMaterialInput;
  if (!material || typeof material.canonical_name !== "string" || !material.canonical_name.trim() || material.save_to_catalogue !== false) {
    throw new Error("This custom material draft is invalid. Return to the Catalogue and enter it again.");
  }
  return material;
}
