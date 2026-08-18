const DEVELOPMENT_API_BASE_URL = "http://127.0.0.1:8000";
const RAW_HTTPS_ORIGIN = /^https:\/\/[^/?#\\\s]+\/?$/i;

function isLoopbackHostname(hostname: string): boolean {
  const lower = hostname.toLowerCase().replace(/\.+$/, "");
  const normalized =
    lower.startsWith("[") && lower.endsWith("]")
      ? lower.slice(1, -1)
      : lower;

  const mappedIpv4 = /^::ffff:([0-9a-f]{1,4}):[0-9a-f]{1,4}$/.exec(
    normalized,
  );

  return (
    normalized === "localhost" ||
    normalized === "::1" ||
    normalized.startsWith("127.") ||
    (mappedIpv4 !== null && (Number.parseInt(mappedIpv4[1], 16) >> 8) === 127)
  );
}

export function resolveApiBaseUrl(
  appEnv = process.env.APP_ENV,
  candidate = process.env.NEXT_PUBLIC_API_URL,
): string {
  if (appEnv !== "production") {
    return candidate ?? DEVELOPMENT_API_BASE_URL;
  }

  if (!candidate) {
    throw new Error(
      "NEXT_PUBLIC_API_URL is required when APP_ENV=production",
    );
  }

  const rawAuthority = candidate.replace(/^https:\/\//i, "").replace(/\/$/, "");
  if (!RAW_HTTPS_ORIGIN.test(candidate) || rawAuthority.includes("@")) {
    throw new Error(
      "NEXT_PUBLIC_API_URL must be an absolute HTTPS origin in production",
    );
  }

  let url: URL;
  try {
    url = new URL(candidate);
  } catch {
    throw new Error(
      "NEXT_PUBLIC_API_URL must be an absolute HTTPS origin in production",
    );
  }

  if (
    candidate.includes("*") ||
    url.hostname.includes("*") ||
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  ) {
    throw new Error(
      "NEXT_PUBLIC_API_URL must be an absolute HTTPS origin in production",
    );
  }

  if (isLoopbackHostname(url.hostname)) {
    throw new Error(
      "NEXT_PUBLIC_API_URL cannot use a loopback host in production",
    );
  }

  return url.origin;
}
