import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Minimal component-test setup (Sprint 020) — the repo's only prior test
// tooling was two `node --test` scripts for non-React logic
// (lib/runtime-config.test.mjs, Dockerfile.test.mjs). This is the first
// config capable of rendering a component, simulating a click, and
// asserting on re-rendered output.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["**/*.test.{ts,tsx}"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
});
