import type { MetadataRoute } from "next";

import { SITE_DESCRIPTION, SITE_NAME } from "@/lib/site";

// Sprint 035 — GeoCore brand asset integration.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: SITE_NAME,
    short_name: SITE_NAME,
    description: SITE_DESCRIPTION,
    start_url: "/",
    display: "browser",
    background_color: "#F8F6EE",
    theme_color: "#0F2E23",
    icons: [
      { src: "/brand/icon-dark-192.png", sizes: "192x192", type: "image/png" },
      { src: "/brand/icon-dark-512.png", sizes: "512x512", type: "image/png" },
    ],
  };
}
