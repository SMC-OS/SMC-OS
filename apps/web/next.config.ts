import type { NextConfig } from "next";
import { createRequire } from "node:module";
import path from "node:path";

const loadRuntimeConfig = createRequire(__filename);
const { resolveApiBaseUrl } = loadRuntimeConfig(
  path.join(__dirname, "lib", "runtime-config.ts"),
) as typeof import("./lib/runtime-config");

resolveApiBaseUrl();

const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;
