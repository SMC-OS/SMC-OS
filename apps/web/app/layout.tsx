import AppShell from "../components/layout/AppShell";
import { AuthProvider } from "../components/auth/AuthProvider";
import { ThemeProvider } from "../components/theme/ThemeProvider";
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Sprint 034 — this is the *platform's* metadata, so it describes the
// product, not any one tenant's business. The previous description named a
// single customer company, which is a tenant identity and belongs in that
// tenant's own company profile (Settings → Company identity), never in
// global chrome every tenant sees.
export const metadata: Metadata = {
  title: "GeoCore",
  description: "AI operating system for stone and construction businesses",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: "/favicon.ico",
    shortcut: "/favicon.ico",
    apple: "/brand/icon-dark-192.png",
  },
  openGraph: {
    title: "GeoCore",
    description: "AI operating system for stone and construction businesses",
    images: ["/brand/og-image.png"],
  },
  // app.geocore.one is the authenticated application, not the public site —
  // it must never be indexed (docs/DNS_GEOCORE_ONE.md §5). apps/web/app/robots.ts
  // already enforces this at the crawler level; this keeps social-preview
  // scrapers from treating a login page as the brand's canonical page too.
  robots: { index: false, follow: false },
};

// Runs before React hydrates so the correct theme class is on <html> before
// first paint — avoids a flash of the wrong theme. Kept intentionally tiny.
const themeInitScript = `
(function () {
  try {
    // Reads the post-rebrand key first, then the pre-rebrand one. Without
    // the fallback a returning dark-mode user would flash light on their
    // first load after the deploy, before ThemeProvider migrates the value.
    var stored = localStorage.getItem("geocore-theme") || localStorage.getItem("simo-os-theme");
    var prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    var theme = stored || (prefersDark ? "dark" : "light");
    if (theme === "dark") document.documentElement.classList.add("dark");
  } catch (e) {}
})();
`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable}`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="min-h-screen" suppressHydrationWarning>
        <ThemeProvider>
          <AuthProvider>
            <AppShell>{children}</AppShell>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
