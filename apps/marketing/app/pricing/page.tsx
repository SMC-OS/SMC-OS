import type { Metadata } from "next";

import { PricingPageClient } from "./page-client";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "GeoCore pricing: Starter £29, Team £59, Pro £99 and Business £199 a month, plus Enterprise. Every plan starts with a 14-day free trial. No card required.",
  alternates: { canonical: "/pricing" },
};

export default function PricingPage() {
  return <PricingPageClient />;
}
