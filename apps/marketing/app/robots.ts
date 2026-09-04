import type { MetadataRoute } from "next";

import { IS_INDEXABLE, SITE_URL } from "@/lib/site";

// Sprint 034 (Phase 2). Only the production canonical host invites
// crawling; a staging or preview deploy of this same image disallows
// everything, so it can never compete with geocore.one in the index.
export default function robots(): MetadataRoute.Robots {
  if (!IS_INDEXABLE) {
    return { rules: [{ userAgent: "*", disallow: "/" }] };
  }

  return {
    rules: [{ userAgent: "*", allow: "/" }],
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
