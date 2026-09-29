const PUBLIC_SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || "https://www.geocore.one").replace(/\/+$/, "");

export function legalUrl(path = ""): string {
  return `${PUBLIC_SITE_URL}/legal${path}`;
}
