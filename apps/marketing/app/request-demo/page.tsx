import type { Metadata } from "next";

import { RequestDemoPageClient } from "./page-client";

export const metadata: Metadata = {
  title: "Request a Demo",
  description:
    "See GeoCore run your own kind of job. Request a demo — no account and no card required.",
  alternates: { canonical: "/request-demo" },
};

export default function RequestDemoPage() {
  return <RequestDemoPageClient />;
}
