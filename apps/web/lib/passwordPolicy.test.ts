import { describe, expect, it } from "vitest";

import {
  PASSWORD_TOO_LONG_MESSAGE,
  passwordExceedsMaxBytes,
  passwordPolicyError,
  passwordSatisfiesPolicy,
} from "@/lib/passwordPolicy";

// Mirrors tests/test_password_max_bytes.py: the limit is UTF-8 bytes.
const ASCII_72 = "Aa1!" + "a".repeat(68);
const ASCII_73 = ASCII_72 + "a";
const UNICODE_72_BYTES = "Aa1!" + "é".repeat(34); // 38 characters
const UNICODE_74_BYTES = "Aa1!" + "é".repeat(35); // 39 characters
const EMOJI_76_BYTES = "Aa1!" + "😀".repeat(18);

describe("password byte limit", () => {
  it("counts UTF-8 bytes, not characters", () => {
    expect(passwordExceedsMaxBytes(ASCII_72)).toBe(false);
    expect(passwordExceedsMaxBytes(UNICODE_72_BYTES)).toBe(false);
    expect(passwordExceedsMaxBytes(ASCII_73)).toBe(true);
    expect(passwordExceedsMaxBytes(UNICODE_74_BYTES)).toBe(true);
    expect(passwordExceedsMaxBytes(EMOJI_76_BYTES)).toBe(true);
  });

  it.each([ASCII_72, UNICODE_72_BYTES, "Correct-Horse-Battery-1!"])(
    "accepts a password within 72 bytes",
    (password) => {
      expect(passwordPolicyError(password)).toBeNull();
      expect(passwordSatisfiesPolicy(password)).toBe(true);
    }
  );

  it.each([ASCII_73, UNICODE_74_BYTES, EMOJI_76_BYTES])(
    "rejects a password over 72 bytes with the backend's message",
    (password) => {
      expect(passwordPolicyError(password)).toBe(PASSWORD_TOO_LONG_MESSAGE);
      expect(passwordSatisfiesPolicy(password)).toBe(false);
    }
  );

  it("still reports the normal policy for weak passwords", () => {
    expect(passwordPolicyError("short")).toMatch(/at least 10 characters/);
  });
});
