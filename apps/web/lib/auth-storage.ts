/** Browser authentication lives in an HttpOnly API cookie. No bearer token
 * is read from or written to localStorage/sessionStorage. The in-memory
 * bearer seam supports explicit API clients and component test fixtures. */
import { LEGACY_TOKEN_KEY, TOKEN_KEY, removeValue } from "@/lib/storage-keys";

let memoryBearer: string | null = null;
let csrfToken: string | null = null;
export const TOKEN_CLEARED_EVENT = "geocore:token-cleared";

export function getToken(): string | null { return memoryBearer; }
export function setToken(token: string): void { memoryBearer = token; }
export function getCsrfToken(): string | null { return csrfToken; }
export function setCsrfToken(token: string): void { csrfToken = token; }

export function clearLegacyTokens(): void {
  removeValue(TOKEN_KEY, LEGACY_TOKEN_KEY);
}

export function clearToken(): void {
  memoryBearer = null;
  csrfToken = null;
  clearLegacyTokens();
  window.dispatchEvent(new Event(TOKEN_CLEARED_EVENT));
}
