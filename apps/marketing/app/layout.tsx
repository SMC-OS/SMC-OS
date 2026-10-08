import type { Metadata } from "next";
import { Geist } from "next/font/google";

import { IS_INDEXABLE, SEO_LONG_NAME, SEO_NAME, SITE_DESCRIPTION, SITE_TAGLINE, SITE_URL } from "@/lib/site";
import { ConsentBanner } from "@/components/ConsentBanner";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-sans",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: `${SEO_NAME}: ${SITE_TAGLINE}`,
    template: `%s | ${SEO_NAME}`,
  },
  description: SITE_DESCRIPTION,
  applicationName: SEO_NAME,
  alternates: { canonical: "/" },
  manifest: "/manifest.webmanifest",
  icons: {
    icon: "/favicon.ico",
    shortcut: "/favicon.ico",
    apple: "/brand/icon-dark-192.png",
  },
  openGraph: {
    type: "website",
    url: SITE_URL,
    siteName: SEO_NAME,
    title: SEO_LONG_NAME,
    description: SITE_DESCRIPTION,
    locale: "en_GB",
    images: [`${SITE_URL}/brand/og-image.png`],
  },
  twitter: {
    card: "summary_large_image",
    title: SEO_LONG_NAME,
    description: SITE_DESCRIPTION,
    images: [`${SITE_URL}/brand/og-image.png`],
  },
  // Staging and preview hosts must stay out of the index; only the
  // production canonical host advertises itself as indexable.
  robots: IS_INDEXABLE
    ? { index: true, follow: true }
    : { index: false, follow: false },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en-GB" className={geistSans.variable}>
      <body>{children}<ConsentBanner /></body>
    </html>
  );
}
