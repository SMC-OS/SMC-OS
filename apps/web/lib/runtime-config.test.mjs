import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

const source = await readFile(
  new URL("./runtime-config.ts", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2020,
  },
}).outputText;
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`;
const { resolveApiBaseUrl } = await import(moduleUrl);

const normalizationBypasses = [
  ["encoded wildcard", "https://%2A.example.com"],
  ["trailing-dot localhost", "https://localhost."],
  ["IPv4-mapped IPv6 loopback", "https://[::ffff:127.0.0.1]"],
  ["dot-segment path", "https://api.example.com/foo/.."],
  ["empty query delimiter", "https://api.example.com?"],
  ["empty fragment delimiter", "https://api.example.com#"],
  ["empty userinfo delimiter", "https://@api.example.com"],
];

for (const [name, candidate] of normalizationBypasses) {
  test(`production rejects ${name} before URL normalization`, () => {
    assert.throws(
      () => resolveApiBaseUrl("production", candidate),
      /NEXT_PUBLIC_API_URL/,
    );
  });
}
