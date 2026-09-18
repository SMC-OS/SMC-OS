import type { Metadata } from "next";

import { PricingPageClient } from "./page-client";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "GeoCore pricing: Starter, Team, Pro, Business and Enterprise plans. Every self-service plan includes a 14-day free trial — £0 due today, card required to activate.",
  alternates: { canonical: "/pricing" },
};

export default function PricingPage() {
  return <PricingPageClient />;
}
