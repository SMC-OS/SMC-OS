import type { MetadataRoute } from "next";

// Sprint 035 — GeoCore brand asset integration. Installable-app metadata
// only (icons/colours); no service worker or offline caching is added
// here, which would be a separate, larger decision.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "GeoCore",
    short_name: "GeoCore",
    // Sprint 039 Production Readiness Defect Gate, Blocker 7 — this had
    // drifted from apps/web/app/layout.tsx's own metadata.description,
    // which was already corrected. Matched to it exactly.
    description: "The AI operating system for construction and renovation businesses",
    start_url: "/",
    display: "standalone",
    background_color: "#0F2E23",
    theme_color: "#0F2E23",
    icons: [
      { src: "/brand/icon-dark-192.png", sizes: "192x192", type: "image/png" },
      { src: "/brand/icon-dark-512.png", sizes: "512x512", type: "image/png" },
    ],
  };
}
