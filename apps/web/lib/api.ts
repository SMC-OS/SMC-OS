import type { ActivityEvent, ActivityType } from "@/types/activity";
import type { LoginResponse } from "@/types/auth";
import type { Customer, CustomerCreate } from "@/types/customer";
import type { DashboardStats } from "@/types/dashboard";
import type { AppNotification } from "@/types/notification";
import type { QuoteRequest, QuoteResult } from "@/types/quote";
import { clearToken, getToken } from "@/lib/auth-storage";

/**
 * Single source of truth for the backend base URL. Reads from an env var
 * instead of being hardcoded per-component (the previous implementation in
 * app/page.tsx hardcoded http://127.0.0.1:8000 directly in a fetch call).
 *
 * Set NEXT_PUBLIC_API_URL in apps/web/.env.local to point elsewhere.
 */
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;

  // Sprint 004: attach the stored JWT (if any) to every call. Harmless on
  // public routes — required on auth-gated ones like /customers.
  const token = getToken();

  try {
    // Sprint 003: every backend route (except / and /health) moved under
    // /api/v1 (ADR-012) — applied once here so every api.* call site below
    // stays a bare resource path, not a search-and-replace across each one.
    res = await fetch(`${API_BASE_URL}/api/v1${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    // Network failure (backend down, offline, CORS, etc.)
    throw new ApiError(`Could not reach the API at ${path}`, 0);
  }

  if (!res.ok) {
    // A 401 means the stored token is missing/invalid/expired — clear it so
    // the next auth check on a protected page redirects to /login instead
    // of retrying with a dead token.
    if (res.status === 401) clearToken();
    throw new ApiError(`Request to ${path} failed with ${res.status}`, res.status);
  }

  return (await res.json()) as T;
}

export const api = {
  getDashboardStats: () => request<DashboardStats>("/dashboard"),

  getActivity: (limit = 10, type?: ActivityType) =>
    request<ActivityEvent[]>(
      `/activity?limit=${limit}${type ? `&type=${type}` : ""}`
    ),

  logActivity: (event: { type: ActivityType; title: string; description?: string }) =>
    request<ActivityEvent>("/activity", {
      method: "POST",
      body: JSON.stringify(event),
    }),

  getNotifications: (limit = 20) =>
    request<AppNotification[]>(`/notifications?limit=${limit}`),

  getUnreadNotificationCount: () =>
    request<{ unread: number }>("/notifications/unread-count"),

  markNotificationRead: (id: string) =>
    request<AppNotification>(`/notifications/${id}/read`, { method: "PATCH" }),

  createQuote: (quote: QuoteRequest) =>
    request<QuoteResult>("/quote", {
      method: "POST",
      body: JSON.stringify(quote),
    }),

  processPrompt: (text: string) =>
    request<Record<string, unknown> | unknown[]>("/process", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),

  login: (email: string, password: string) =>
    request<LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  getCustomers: (limit = 20) =>
    request<Customer[]>(`/customers?limit=${limit}`),

  getCustomer: (id: string) => request<Customer>(`/customers/${id}`),

  createCustomer: (customer: CustomerCreate) =>
    request<Customer>("/customers", {
      method: "POST",
      body: JSON.stringify(customer),
    }),
};
