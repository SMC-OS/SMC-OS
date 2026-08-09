export const MATERIAL_OPTIONS = [
  "Calacatta Gold",
  "Calacatta Oro",
  "Nero Marquina",
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
