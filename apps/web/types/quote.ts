// Sprint 005: mirrors the seeded catalogue in app/materials/seed.py.
// Materials stay internal (no GET /api/v1/materials this sprint), so this
// list is hand-kept in sync the same way the previous 3-item list was.
export const MATERIAL_OPTIONS = [
  // Quartz
  "Calacatta Gold",
  "Calacatta Oro",
  "Nero Marquina",
  "Statuario White",
  "Carrara Mist",
  // Granite
  "Absolute Black",
  "Kashmir White",
  "Baltic Brown",
  // Marble
  "Carrara White",
  "Emperador Brown",
  "Statuario Marble",
  // Porcelain
  "Grey Concrete Porcelain",
  "Calacatta Porcelain",
  // Dekton
  "Dekton Sirocco",
  "Dekton Kelya",
] as const;

export const THICKNESS_OPTIONS = ["20mm", "30mm"] as const;

export interface QuoteRequest {
  customer: string;
  material: string;
  thickness: string;
  kitchen_length: number;
  island: boolean;
  waterfall: number;
  splashback: boolean;
  upstands: boolean;
  postcode?: string;
}

export interface QuoteResult {
  customer: string;
  material: string;
  slabs: number;
  price_per_slab: number;
  price_before_vat: number;
  vat: number;
  total: number;
}
