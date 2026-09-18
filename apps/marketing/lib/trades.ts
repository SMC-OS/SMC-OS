/**
 * Sprint 041 — mirrors app/trades/catalogue.py's TRADES tuple (the
 * single canonical key/label vocabulary, GeoCore Premium OS Plan 01).
 * Keys are stable persisted identifiers and must stay byte-for-byte
 * identical to the backend's — the Request Demo form submits these keys
 * directly to POST /demo-requests, which validates each one against
 * app.trades.catalogue.TRADE_KEYS server-side. This file is display data
 * only (labels, representative workflow examples) for a public,
 * unauthenticated audience; it is not the authority, the backend is.
 */

export interface TradeInfo {
  key: string;
  label: string;
}

export const TRADES: TradeInfo[] = [
  { key: "general_building", label: "General Building" },
  { key: "renovation", label: "Renovation" },
  { key: "extension", label: "Extensions" },
  { key: "kitchen", label: "Kitchens" },
  { key: "bathroom", label: "Bathrooms" },
  { key: "roofing", label: "Roofing" },
  { key: "flooring", label: "Flooring" },
  { key: "decorating", label: "Painting & Decorating" },
  { key: "plumbing", label: "Plumbing" },
  { key: "electrical", label: "Electrical" },
  { key: "carpentry", label: "Carpentry & Joinery" },
  { key: "stone", label: "Stone & Worktops" },
  { key: "heating_hvac", label: "Heating / HVAC" },
  { key: "tiling", label: "Tiling" },
  { key: "plastering_rendering", label: "Plastering & Rendering" },
  { key: "brickwork_masonry", label: "Brickwork & Masonry" },
  { key: "groundworks", label: "Groundworks" },
  { key: "drainage", label: "Drainage" },
  { key: "windows_doors", label: "Windows & Doors" },
  { key: "glazing", label: "Glazing" },
  { key: "landscaping", label: "Landscaping" },
  { key: "fencing", label: "Fencing" },
  { key: "demolition_stripout", label: "Demolition / Strip-Out" },
  { key: "insulation", label: "Insulation" },
  { key: "steelwork", label: "Structural Steelwork" },
  { key: "scaffolding", label: "Scaffolding" },
  { key: "solar_renewables", label: "Solar & Renewables" },
  { key: "other", label: "Other / Custom Trade" },
];

// A handful of representative example sequences for the homepage's Trade
// Workflows section (app/workflows/catalogue.py is the real per-trade
// system template each of these mirrors) — not every trade's full
// sequence, which would overwhelm the page; the full list lives on
// /pricing's sibling, the trade catalogue itself, reachable via
// "Explore all trades."
export const EXAMPLE_WORKFLOWS: { trade: string; sequence: string[] }[] = [
  {
    trade: "Electrical",
    sequence: [
      "Enquiry",
      "Site Assessment",
      "Quote",
      "Approved",
      "First Fix",
      "Second Fix",
      "Testing",
      "Certification",
      "Complete",
    ],
  },
  {
    trade: "Stone & Worktops",
    sequence: [
      "Enquiry",
      "Measure",
      "Quote",
      "Approved",
      "Material",
      "Template",
      "Fabrication",
      "QC",
      "Installation",
      "Complete",
    ],
  },
  {
    trade: "General Building",
    sequence: [
      "Enquiry",
      "Site Visit",
      "Quote",
      "Approved",
      "In Progress",
      "Inspection",
      "Snagging",
      "Handover",
      "Complete",
    ],
  },
  {
    trade: "Bathrooms",
    sequence: [
      "Enquiry",
      "Survey",
      "Quote",
      "Approved",
      "Strip-Out",
      "Waterproofing",
      "Tiling / Fitting",
      "Snagging",
      "Complete",
    ],
  },
];

export const TEAM_SIZE_OPTIONS: { value: string; label: string }[] = [
  { value: "1", label: "Just me" },
  { value: "2-3", label: "2–3 people" },
  { value: "4-10", label: "4–10 people" },
  { value: "11-25", label: "11–25 people" },
  { value: "26-50", label: "26–50 people" },
  { value: "50+", label: "50+ people" },
];

export const CONTACT_METHOD_OPTIONS: { value: string; label: string }[] = [
  { value: "email", label: "Email" },
  { value: "phone", label: "Phone" },
];
