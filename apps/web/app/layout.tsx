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
  title: "SIMO OS",
  description: "AI operating system for stone and construction businesses",
};

// Runs before React hydrates so the correct theme class is on <html> before
// first paint — avoids a flash of the wrong theme. Kept intentionally tiny.
const themeInitScript = `
(function () {
  try {
    var stored = localStorage.getItem("simo-os-theme");
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
