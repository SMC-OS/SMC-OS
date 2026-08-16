import type { ActivityEvent, ActivityType } from "@/types/activity";
import type { AuthUser, LoginResponse, SignupRequest } from "@/types/auth";
import type { Customer, CustomerCreate } from "@/types/customer";
import type { DashboardStats } from "@/types/dashboard";
import type { DocumentOut } from "@/types/document";
import type {
  AcceptInvitationRequest,
  InvitationCreateOut,
  InvitationOut,
  InvitationPublicOut,
} from "@/types/invitation";
import type { AppNotification } from "@/types/notification";
import type { PortalLinkCreateOut, PortalLinkOut, PortalPublicOut } from "@/types/portal";
import type { Project, ProjectCreate, ProjectStatus } from "@/types/project";
import type { AIQuoteDraft, Quote, QuoteRequest, QuoteResult } from "@/types/quote";
import type { TeamMemberOut } from "@/types/user";
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

  // Sprint 009 — creates a new company workspace + its first (Owner) user,
  // returns the same shape as login so the caller can sign the new owner
  // straight in.
  signup: (data: SignupRequest) =>
    request<LoginResponse>("/auth/signup", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getMe: () => request<AuthUser>("/auth/me"),

  // Sprint 011 — Owner-only (require_role(OWNER) server-side; a Staff
  // caller gets a 403 handled by the caller, same as any other ApiError).
  createInvitation: (email: string) =>
    request<InvitationCreateOut>("/invitations", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  getInvitations: () => request<InvitationOut[]>("/invitations"),

  revokeInvitation: (id: string) =>
    request<InvitationOut>(`/invitations/${id}`, { method: "DELETE" }),

  // Sprint 015 — Owner-only (require_role(OWNER) server-side; a Staff
  // caller gets a 403 handled by the caller, same as invitations).
  getUsers: () => request<TeamMemberOut[]>("/users"),

  deactivateUser: (id: string) =>
    request<TeamMemberOut>(`/users/${id}/deactivate`, { method: "POST" }),

  // Public — no token required, the invitee has no account yet.
  getInvitationByToken: (token: string) =>
    request<InvitationPublicOut>(`/invitations/token/${token}`),

  acceptInvitation: (token: string, data: AcceptInvitationRequest) =>
    request<LoginResponse>(`/invitations/token/${token}/accept`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getCustomers: (limit = 20) =>
    request<Customer[]>(`/customers?limit=${limit}`),

  getCustomer: (id: string) => request<Customer>(`/customers/${id}`),

  createCustomer: (customer: CustomerCreate) =>
    request<Customer>("/customers", {
      method: "POST",
      body: JSON.stringify(customer),
    }),

  // Sprint 013 — any authenticated tenant user, not Owner-only (sharing a
  // project link with a customer is routine work, unlike inviting a
  // teammate).
  createPortalLink: (customerId: string) =>
    request<PortalLinkCreateOut>("/portal-links", {
      method: "POST",
      body: JSON.stringify({ customer_id: customerId }),
    }),

  getPortalLinks: (customerId?: string) =>
    request<PortalLinkOut[]>(
      `/portal-links${customerId ? `?customer_id=${customerId}` : ""}`
    ),

  revokePortalLink: (id: string) =>
    request<PortalLinkOut>(`/portal-links/${id}`, { method: "DELETE" }),

  // Public — no token required, the customer has no account.
  getPortalByToken: (token: string) =>
    request<PortalPublicOut>(`/portal-links/token/${token}`),

  // Public — same blob-download pattern as downloadInvoice, but keyed by
  // the portal token instead of a bearer token (the customer has neither).
  downloadPortalInvoice: async (token: string, quoteId: string): Promise<void> => {
    let res: Response;

    try {
      res = await fetch(
        `${API_BASE_URL}/api/v1/portal-links/token/${token}/invoice/${quoteId}`
      );
    } catch {
      throw new ApiError(
        `Could not reach the API at /portal-links/token/${token}/invoice/${quoteId}`,
        0
      );
    }

    if (!res.ok) {
      throw new ApiError(
        `Request to /portal-links/token/${token}/invoice/${quoteId} failed with ${res.status}`,
        res.status
      );
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `invoice-${quoteId.slice(0, 8)}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },

  // Sprint 016 — public, no token required, matches
  // getPortalByToken/downloadPortalInvoice.
  getPortalDocuments: (token: string) =>
    request<DocumentOut[]>(`/portal-links/token/${token}/documents`),

  downloadPortalDocument: async (
    token: string,
    documentId: string,
    filename: string
  ): Promise<void> => {
    let res: Response;
    try {
      res = await fetch(
        `${API_BASE_URL}/api/v1/portal-links/token/${token}/documents/${documentId}/download`
      );
    } catch {
      throw new ApiError(
        `Could not reach the API at /portal-links/token/${token}/documents/${documentId}/download`,
        0
      );
    }

    if (!res.ok) {
      throw new ApiError(
        `Request to /portal-links/token/${token}/documents/${documentId}/download failed with ${res.status}`,
        res.status
      );
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },

  getProjects: (limit = 20) => request<Project[]>(`/projects?limit=${limit}`),

  getProject: (id: string) => request<Project>(`/projects/${id}`),

  createProject: (project: ProjectCreate) =>
    request<Project>("/projects", {
      method: "POST",
      body: JSON.stringify(project),
    }),

  updateProjectStatus: (id: string, projectStatus: ProjectStatus) =>
    request<Project>(`/projects/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status: projectStatus }),
    }),

  // AI Quotation Generator v1: extraction only, pre-fills the manual form
  // for human review — never auto-submitted, never priced by the AI.
  generateQuoteDraft: (text: string) =>
    request<AIQuoteDraft>("/quotes/ai-draft", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),

  getQuotes: (limit = 20) => request<Quote[]>(`/quotes?limit=${limit}`),

  getQuote: (id: string) => request<Quote>(`/quotes/${id}`),

  // Sprint 007: not JSON, so this bypasses request() and triggers a real
  // browser download directly — fetch the PDF as a blob, point a synthetic
  // <a download> at an object URL, click it, clean up.
  downloadInvoice: async (id: string): Promise<void> => {
    const token = getToken();
    let res: Response;

    try {
      res = await fetch(`${API_BASE_URL}/api/v1/quotes/${id}/invoice`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
    } catch {
      throw new ApiError(`Could not reach the API at /quotes/${id}/invoice`, 0);
    }

    if (!res.ok) {
      if (res.status === 401) clearToken();
      throw new ApiError(
        `Request to /quotes/${id}/invoice failed with ${res.status}`,
        res.status
      );
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `invoice-${id.slice(0, 8)}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },

  // Sprint 016 — multipart upload, cannot reuse request()'s JSON-only
  // Content-Type/body handling. Mirrors request()'s auth-header and
  // 401-clearing behavior manually; browser sets the multipart
  // Content-Type boundary automatically when body is a FormData instance
  // (must NOT set Content-Type manually here).
  uploadDocument: async (customerId: string, file: File): Promise<DocumentOut> => {
    const token = getToken();
    const formData = new FormData();
    formData.append("file", file);

    let res: Response;
    try {
      res = await fetch(
        `${API_BASE_URL}/api/v1/documents?customer_id=${customerId}`,
        {
          method: "POST",
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          body: formData,
        }
      );
    } catch {
      throw new ApiError(`Could not reach the API at /documents`, 0);
    }

    if (!res.ok) {
      if (res.status === 401) clearToken();
      const body = await res.json().catch(() => ({}));
      throw new ApiError(
        body.detail ?? `Request to /documents failed with ${res.status}`,
        res.status
      );
    }
    return res.json();
  },

  getDocuments: (customerId: string) =>
    request<DocumentOut[]>(`/documents?customer_id=${customerId}`),

  // Sprint 016 — same blob-download-and-save pattern as downloadInvoice,
  // parameterized by filename since documents don't have a predictable
  // name the way "invoice-<id>.pdf" does.
  downloadDocument: async (id: string, filename: string): Promise<void> => {
    const token = getToken();
    let res: Response;

    try {
      res = await fetch(`${API_BASE_URL}/api/v1/documents/${id}/download`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
    } catch {
      throw new ApiError(`Could not reach the API at /documents/${id}/download`, 0);
    }

    if (!res.ok) {
      if (res.status === 401) clearToken();
      throw new ApiError(
        `Request to /documents/${id}/download failed with ${res.status}`,
        res.status
      );
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },
};
