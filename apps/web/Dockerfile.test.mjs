import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const nextConfig = await readFile(new URL("./next.config.ts", import.meta.url), "utf8");

test("web production build emits the standalone artifact required by the container", () => {
  assert.match(nextConfig, /output:\s*["']standalone["']/);
});

test("web production image runs a standalone server as an unprivileged user", async () => {
  const dockerfile = await readFile(new URL("./Dockerfile", import.meta.url), "utf8");

  assert.match(dockerfile, /ENV\s+HOSTNAME=0\.0\.0\.0/);
  assert.match(dockerfile, /USER\s+nextjs/);
  assert.match(dockerfile, /["']node["'],\s*["']apps\/web\/server\.js["']/);
});

test("web production image does not copy backend secrets", async () => {
  const dockerfile = await readFile(new URL("./Dockerfile", import.meta.url), "utf8");

  assert.doesNotMatch(dockerfile, /COPY\s+.*\.env/i);
  assert.doesNotMatch(dockerfile, /JWT_SECRET|DATABASE_URL|SEED_ADMIN_PASSWORD/i);
});

test("root Docker context retains the workspace web app", async () => {
  const ignore = await readFile(new URL("../../.dockerignore", import.meta.url), "utf8");
  assert.doesNotMatch(ignore, /^apps$/m);
});

test("web Docker contract is reproducibly invoked by package scripts and CI", async () => {
  const packageJson = JSON.parse(await readFile(new URL("./package.json", import.meta.url), "utf8"));
  const ci = await readFile(new URL("../../.github/workflows/ci.yml", import.meta.url), "utf8");

  assert.equal(packageJson.scripts["test:docker-contract"], "node --test Dockerfile.test.mjs");
  assert.match(ci, /pnpm --filter web test:docker-contract/);
});
