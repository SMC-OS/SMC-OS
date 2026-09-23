import type { ActivityEvent, ActivityType } from "@/types/activity";
import type {
  AppointmentCreate,
  AppointmentOut,
  AppointmentTransitionTarget,
} from "@/types/appointment";
import type { AuthUser, LoginResponse, SignupRequest } from "@/types/auth";
import type { BillingPeriod, Plan, PlanId, Subscription } from "@/types/billing";
import type {
  CatalogueStatus,
  CustomMaterialInput,
  CustomMaterialResult,
  SurfaceDetail,
  SurfaceSearchResult,
  TenantOverride,
  TenantOverrideInput,
} from "@/types/catalogue";
import type { CommandCentreStats } from "@/types/command-centre";
import type { AICapabilities, ChatMessage, ChatResponse } from "@/types/ai";
import type {
  Automation,
  AutomationCreate,
  AutomationMeta,
  AutomationRun,
  AutomationTemplate,
  AutomationUpdate,
} from "@/types/automation";
import type { CalendarResponse } from "@/types/calendar";
import type {
  Customer,
  CustomerContext,
  CustomerCreate,
  CustomerUpdate,
} from "@/types/customer";
import type { DashboardStats } from "@/types/dashboard";
import type { DocumentOut } from "@/types/document";
import type {
  ProjectCostEntry,
  ProjectCostEntryIn,
  ProjectCostEntryUpdate,
  ProjectFinancialSummary,
} from "@/types/financials";
import type {
  AcceptInvitationRequest,
  InvitationCreateOut,
  InvitationOut,
  InvitationPublicOut,
} from "@/types/invitation";
import type { MessageOut } from "@/types/message";
import type { AppNotification } from "@/types/notification";
import type { PortalLinkCreateOut, PortalLinkOut, PortalPublicOut } from "@/types/portal";
import type {
  CatalogueSupplierSummary,
  MaterialAllocation,
  MaterialAllocationCreate,
  MaterialRequirement,
  MaterialRequirementIn,
  MaterialRequirementUpdate,
  OrderPurchaseOrderRequest,
  PurchaseOrder,
  PurchaseOrderCreate,
  PurchaseOrderUpdate,
  PurchaseReceipt,
  PurchaseReceiptCreate,
  TenantSupplierAccount,
} from "@/types/procurement";
import type {
  Project,
  ProjectCreate,
  ProjectStatus,
  ProjectUpdate,
} from "@/types/project";
import type { Task, TaskCreate, TaskStatus } from "@/types/task";
import type {
  AIQuoteDraft,
  GeneralQuoteRequest,
  GeneralQuoteUpdate,
  Quote,
  QuoteRequest,
  QuoteResult,
  QuoteUnit,
  Trade,
} from "@/types/quote";
import type {
  OnboardingState,
  OnboardingUpdate,
  TenantProfile,
  TenantProfileUpdate,
} from "@/types/tenant";
import type { TeamMemberOut } from "@/types/user";
import type { Variation, VariationCreate, VariationUpdate } from "@/types/variation";
import type { ProjectWorkflowDetail, WorkflowHistoryEntry } from "@/types/workflow";
import { clearToken, getToken } from "@/lib/auth-storage";
import { resolveApiBaseUrl } from "@/lib/runtime-config";

/**
 * Single source of truth for the backend base URL. Reads from an env var
 * instead of being hardcoded per-component (the previous implementation in
 * app/page.tsx hardcoded http://127.0.0.1:8000 directly in a fetch call).
 *
 * Set NEXT_PUBLIC_API_URL in apps/web/.env.local to point elsewhere.
 */
export const API_BASE_URL = resolveApiBaseUrl();

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

/**
 * A request that returns no body (204). `request()` always parses JSON
 * and would throw on an empty response, so DELETE endpoints use this
 * instead of pretending to decode nothing.
 */
async function requestNoContent(path: string, init?: RequestInit): Promise<void> {
  const token = getToken();
  let res: Response;

  try {
    res = await fetch(`${API_BASE_URL}/api/v1${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError(`Could not reach the API at ${path}`, 0);
  }

  if (!res.ok) {
    if (res.status === 401) clearToken();
    throw new ApiError(`Request to ${path} failed with ${res.status}`, res.status);
  }
}

export const api = {
  getDashboardStats: () => request<DashboardStats>("/dashboard"),

  getCommandCentre: () => request<CommandCentreStats>("/dashboard/command-centre"),

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

  // Sprint 039 Production Readiness Defect Gate, Blocker 1. `already_verified`
  // (Blocker 2 follow-up, verification resend/token hotfix) is the only way
  // the caller can tell "a new email was actually queued" apart from a
  // silent no-op for an account that's already verified — both return 200.
  resendVerificationEmail: () =>
    request<{ message: string; already_verified: boolean }>(
      "/auth/email/verify/resend",
      { method: "POST" }
    ),

  confirmEmailVerification: (token: string) =>
    request<{ message: string }>("/auth/email/verify/confirm", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),

  // Sprint 039 Production Readiness Defect Gate, Blocker 2.
  forgotPassword: (email: string) =>
    request<{ message: string }>("/auth/password/forgot", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  resetPassword: (token: string, newPassword: string) =>
    request<{ message: string }>("/auth/password/reset", {
      method: "POST",
      body: JSON.stringify({ token, new_password: newPassword }),
    }),

  // Settings > Security. Always the signed-in user's own account — the
  // body carries no user id or email. Returns a fresh token because the
  // change signs every other session out.
  changePassword: (currentPassword: string, newPassword: string) =>
    request<LoginResponse>("/auth/password/change", {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),

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

  // Sprint 034 — company identity. Read by any authenticated member;
  // the PATCH is Owner-only server-side (app/tenants/router.py).
  getCompanyProfile: () => request<TenantProfile>("/tenants/me/profile"),

  updateCompanyProfile: (data: TenantProfileUpdate) =>
    request<TenantProfile>("/tenants/me/profile", {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  // Sprint 032 (Workstream A) — subscriptions/billing.
  getPlans: () => request<Plan[]>("/billing/plans"),

  getSubscription: () => request<Subscription | null>("/billing/subscription"),

  createCheckoutSession: (plan: PlanId, billingPeriod: BillingPeriod) =>
    request<{ checkout_url: string }>("/billing/checkout", {
      method: "POST",
      body: JSON.stringify({ plan, billing_period: billingPeriod }),
    }),

  // Phase B — start the 14-day no-card trial for a workspace that has
  // never had a subscription (new signups get one automatically).
  startTrial: (plan?: PlanId, billingPeriod?: BillingPeriod) =>
    request<Subscription>("/billing/trial", {
      method: "POST",
      body: JSON.stringify({ plan: plan ?? null, billing_period: billingPeriod ?? null }),
    }),

  createPortalSession: () =>
    request<{ portal_url: string }>("/billing/portal", { method: "POST" }),

  cancelSubscriptionAtPeriodEnd: () =>
    request<Subscription>("/billing/cancel", { method: "POST" }),

  resumeSubscription: () =>
    request<Subscription>("/billing/resume", { method: "POST" }),

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

  // Sprint 036 (Workstream D). An omitted key is left alone server-side;
  // an explicit null clears the field.
  updateCustomer: (id: string, changes: CustomerUpdate) =>
    request<Customer>(`/customers/${id}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),

  // One call backing the customer detail page's business context —
  // their quotes, their projects and what those are worth — so the page
  // has no partially-loaded intermediate state.
  getCustomerContext: (id: string) =>
    request<CustomerContext>(`/customers/${id}/context`),

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

  // Sprint 017 — public, no token required. postPortalMessage is the
  // first public write call this client ever makes (the customer's side
  // of two-way portal messaging, ADR-033).
  getPortalMessages: (token: string) =>
    request<MessageOut[]>(`/portal-links/token/${token}/messages`),

  postPortalMessage: (token: string, body: string) =>
    request<MessageOut>(`/portal-links/token/${token}/messages`, {
      method: "POST",
      body: JSON.stringify({ body }),
    }),

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

  // Sprint 036 (Workstream F) — a project's own details. Status keeps its
  // own endpoint below, with its own linear-transition rules.
  updateProject: (id: string, changes: ProjectUpdate) =>
    request<Project>(`/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),

  updateProjectStatus: (id: string, projectStatus: ProjectStatus) =>
    request<Project>(`/projects/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status: projectStatus }),
    }),

  // Sprint 023 — Owner-only server-side (require_role(OWNER)), distinct
  // from updateProjectStatus's Owner+Staff gating (docs/SPRINTS/sprint-023.md
  // Decision 2). assignedUserId: null is a valid, explicit unassignment.
  assignProject: (id: string, assignedUserId: string | null) =>
    request<Project>(`/projects/${id}/assign`, {
      method: "PATCH",
      body: JSON.stringify({ assigned_user_id: assignedUserId }),
    }),

  // Sprint 021 — Owner/Staff only (require_role(OWNER, STAFF) server-side; a
  // caller without that role gets a 403 handled by the caller, same as
  // approveQuote/handoffQuote). Returns the created/linked Customer
  // (CustomerOut), not the Project — that Customer is authoritative.
  convertProjectToCustomer: (id: string, customer: CustomerCreate) =>
    request<Customer>(`/projects/${id}/convert-to-customer`, {
      method: "POST",
      body: JSON.stringify(customer),
    }),

  // Sprint 022 — site visit scheduling (docs/SPRINTS/sprint-022.md).
  // Owner/Staff only server-side (require_role(OWNER, STAFF)), same as
  // convertProjectToCustomer above. Decision 6: dedicated
  // completeAppointment/cancelAppointment methods over one generic
  // updateAppointmentStatus(id, status).
  getProjectAppointments: (projectId: string) =>
    request<AppointmentOut[]>(`/projects/${projectId}/appointments`),

  createAppointment: (projectId: string, appointment: AppointmentCreate) =>
    request<AppointmentOut>(`/projects/${projectId}/appointments`, {
      method: "POST",
      body: JSON.stringify(appointment),
    }),

  completeAppointment: (id: string) =>
    request<AppointmentOut>(`/appointments/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status: "completed" satisfies AppointmentTransitionTarget }),
    }),

  cancelAppointment: (id: string) =>
    request<AppointmentOut>(`/appointments/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status: "cancelled" satisfies AppointmentTransitionTarget }),
    }),

  // GeoCore Premium OS Plan 01 (Sprint 040, Task 8) — Project 360's
  // Workflow/Timeline tabs. getProjectWorkflow's `allowed_transitions`
  // already carries each option's own unmet gate requirements
  // (blocked_requirements), so the UI never needs a second round trip to
  // explain why a listed move isn't reachable yet.
  getProjectWorkflow: (projectId: string) =>
    request<ProjectWorkflowDetail>(`/projects/${projectId}/workflow`),

  getProjectWorkflowHistory: (projectId: string) =>
    request<WorkflowHistoryEntry[]>(`/projects/${projectId}/workflow/history`),

  // One endpoint for every project's advancement action regardless of
  // trade or legacy binding (Hold/Resume/Cancel included — the caller
  // just names the target stage key, e.g. "on_hold"). Returns the
  // updated Project, same authoritative-response contract as
  // updateProjectStatus/assignProject above.
  transitionProjectWorkflow: (projectId: string, targetStageKey: string, reason?: string | null) =>
    request<Project>(`/projects/${projectId}/workflow/transition`, {
      method: "POST",
      body: JSON.stringify({ target_stage_key: targetStageKey, reason: reason ?? null }),
    }),

  // AI Quotation Generator v1: extraction only, pre-fills the manual form
  // for human review — never auto-submitted, never priced by the AI.
  generateQuoteDraft: (text: string) =>
    request<AIQuoteDraft>("/quotes/ai-draft", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),

  // --- Sprint 036 (Workstream E) — universal quoting. ---
  //
  // Deliberately distinct from createQuote above, which is the public
  // stone calculator (POST /quote) and is unchanged. This is the
  // authenticated general construction quote (POST /quotes).
  createGeneralQuote: (quote: GeneralQuoteRequest) =>
    request<Quote>("/quotes", {
      method: "POST",
      body: JSON.stringify(quote),
    }),

  updateGeneralQuote: (id: string, changes: GeneralQuoteUpdate) =>
    request<Quote>(`/quotes/${id}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),

  // Records that a person gave this quote to the customer. Sends
  // nothing — GeoCore has no email, SMS or messaging channel, and the UI
  // says so where this is offered.
  sendQuote: (id: string) => request<Quote>(`/quotes/${id}/send`, { method: "POST" }),

  // Served from the backend rather than duplicated as frontend constants,
  // so the quote form, the project form and onboarding cannot drift.
  getTrades: () => request<Trade[]>("/quotes/meta/trades"),

  // Sprint 042 (GeoCore Premium OS Plan 03) — Master Materials & Supplier Catalogue.
  getMaterialFamilies: () => request<string[]>("/catalogue/meta/material-families"),

  getCatalogueStatus: () => request<CatalogueStatus>("/catalogue/meta/status"),

  searchCatalogueSurfaces: (params: {
    q?: string;
    material_family?: string;
    colour_family?: string;
    supplier_id?: string;
    include_discontinued?: boolean;
    limit?: number;
  } = {}) => {
    const query = new URLSearchParams();
    if (params.q) query.set("q", params.q);
    if (params.material_family) query.set("material_family", params.material_family);
    if (params.supplier_id) query.set("supplier_id", params.supplier_id);
    if (params.colour_family) query.set("colour_family", params.colour_family);
    if (params.include_discontinued) query.set("include_discontinued", "true");
    query.set("limit", String(params.limit ?? 30));
    return request<SurfaceSearchResult[]>(`/catalogue/surfaces?${query.toString()}`);
  },

  getCatalogueSurface: (surfaceId: string) => request<SurfaceDetail>(`/catalogue/surfaces/${surfaceId}`),

  upsertCatalogueOverride: (surfaceId: string, data: TenantOverrideInput) =>
    request<TenantOverride>(`/catalogue/surfaces/${surfaceId}/override`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  createCustomMaterial: (data: CustomMaterialInput) =>
    request<CustomMaterialResult>("/catalogue/custom-materials", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getQuoteUnits: () => request<QuoteUnit[]>("/quotes/meta/units"),

  // --- Sprint 036 (Workstream G) — automations. ---
  getAutomations: () => request<Automation[]>("/automations"),

  getAutomation: (id: string) => request<Automation>(`/automations/${id}`),

  getAutomationMeta: () => request<AutomationMeta>("/automations/meta"),

  getAutomationTemplates: () => request<AutomationTemplate[]>("/automations/templates"),

  getAutomationRuns: (automationId?: string, limit = 50) =>
    request<AutomationRun[]>(
      `/automations/runs?limit=${limit}${
        automationId ? `&automation_id=${automationId}` : ""
      }`
    ),

  createAutomation: (automation: AutomationCreate) =>
    request<Automation>("/automations", {
      method: "POST",
      body: JSON.stringify(automation),
    }),

  activateAutomationTemplate: (templateKey: string) =>
    request<Automation>("/automations/templates", {
      method: "POST",
      body: JSON.stringify({ template_key: templateKey }),
    }),

  updateAutomation: (id: string, changes: AutomationUpdate) =>
    request<Automation>(`/automations/${id}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),

  // 204 No Content — bypasses request(), which always parses JSON.
  deleteAutomation: async (id: string): Promise<void> => {
    await requestNoContent(`/automations/${id}`, { method: "DELETE" });
  },

  // --- Sprint 036 — tasks, calendar and GeoCore AI. ---
  getTasks: (status?: TaskStatus, limit = 50) =>
    request<Task[]>(`/tasks?limit=${limit}${status ? `&status=${status}` : ""}`),

  createTask: (task: TaskCreate) =>
    request<Task>("/tasks", { method: "POST", body: JSON.stringify(task) }),

  updateTaskStatus: (id: string, status: TaskStatus) =>
    request<Task>(`/tasks/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),

  getCalendar: (start: string, end: string) =>
    request<CalendarResponse>(`/calendar?start=${start}&end=${end}`),

  getAICapabilities: () => request<AICapabilities>("/ai/capabilities"),

  chatWithAI: (messages: ChatMessage[]) =>
    request<ChatResponse>("/ai/chat", {
      method: "POST",
      body: JSON.stringify({ messages }),
    }),

  // --- Sprint 036 (Workstreams I/J) — workspace setup and branding. ---
  getOnboardingState: () => request<OnboardingState>("/tenants/me/onboarding"),

  updateOnboarding: (changes: OnboardingUpdate) =>
    request<TenantProfile>("/tenants/me/onboarding", {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),

  // Multipart, so it cannot reuse request()'s JSON-only handling —
  // mirrors uploadDocument's auth-header and 401-clearing behaviour. The
  // browser sets the multipart boundary itself, so Content-Type must NOT
  // be set manually here.
  uploadCompanyLogo: async (file: File): Promise<TenantProfile> => {
    const token = getToken();
    const formData = new FormData();
    formData.append("file", file);

    let res: Response;
    try {
      res = await fetch(`${API_BASE_URL}/api/v1/tenants/me/logo`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      });
    } catch {
      throw new ApiError("Could not reach the API at /tenants/me/logo", 0);
    }

    if (!res.ok) {
      if (res.status === 401) clearToken();
      const body = await res.json().catch(() => ({}));
      throw new ApiError(
        body.detail ?? `Request to /tenants/me/logo failed with ${res.status}`,
        res.status
      );
    }
    return res.json();
  },

  deleteCompanyLogo: () =>
    request<TenantProfile>("/tenants/me/logo", { method: "DELETE" }),

  /** The authenticated URL the logo is served from. A cache-busting
   * parameter is the caller's job — the browser will otherwise keep
   * showing the previous logo after an upload. */
  companyLogoUrl: () => `${API_BASE_URL}/api/v1/tenants/me/logo`,

  getQuotes: (limit = 20) => request<Quote[]>(`/quotes?limit=${limit}`),

  getQuote: (id: string) => request<Quote>(`/quotes/${id}`),

  // Sprint 020 — Owner/Staff only (require_role(OWNER, STAFF) server-side; a
  // caller without that role gets a 403 handled by the caller, same as
  // invitations/users).
  approveQuote: (id: string) => request<Quote>(`/quotes/${id}/approve`, { method: "POST" }),

  // Sprint 020 — Owner/Staff only, same role gate as approveQuote. The
  // returned Project's own id is authoritative for the post-handoff
  // redirect, never derived from the Quote id.
  handoffQuote: (id: string) => request<Project>(`/quotes/${id}/handoff`, { method: "POST" }),

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

  // Sprint 017 — staff side of client-portal messaging. Any authenticated
  // tenant user, not Owner-only, matching createPortalLink/uploadDocument.
  getMessages: (customerId: string) =>
    request<MessageOut[]>(`/messages?customer_id=${customerId}`),

  postMessage: (customerId: string, body: string) =>
    request<MessageOut>(`/messages?customer_id=${customerId}`, {
      method: "POST",
      body: JSON.stringify({ body }),
    }),

  // --- GeoCore Premium OS Plan 04 (Sprint 043) — job financials. ---
  // Owner/Staff only server-side (require_role(OWNER, STAFF)), same gate
  // as project workflow transitions/appointments.
  getProjectFinancialSummary: (projectId: string) =>
    request<ProjectFinancialSummary>(`/projects/${projectId}/financials/summary`),

  getProjectCosts: (projectId: string) =>
    request<ProjectCostEntry[]>(`/projects/${projectId}/costs`),

  createProjectCost: (projectId: string, data: ProjectCostEntryIn) =>
    request<ProjectCostEntry>(`/projects/${projectId}/costs`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateProjectCost: (projectId: string, costEntryId: string, data: ProjectCostEntryUpdate) =>
    request<ProjectCostEntry>(`/projects/${projectId}/costs/${costEntryId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  deleteProjectCost: (projectId: string, costEntryId: string) =>
    requestNoContent(`/projects/${projectId}/costs/${costEntryId}`, { method: "DELETE" }),

  // --- GeoCore Premium OS Plan 04 (Sprint 043) — variations (change orders). ---
  getProjectVariations: (projectId: string) =>
    request<Variation[]>(`/projects/${projectId}/variations`),

  createVariation: (projectId: string, data: VariationCreate) =>
    request<Variation>(`/projects/${projectId}/variations`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getVariation: (id: string) => request<Variation>(`/variations/${id}`),

  // Draft-only server-side — a 409 (ApiError) means the variation has
  // already been sent/approved/rejected/voided; the caller must not
  // silently retry as a create.
  updateVariation: (id: string, data: VariationUpdate) =>
    request<Variation>(`/variations/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  sendVariation: (id: string) => request<Variation>(`/variations/${id}/send`, { method: "POST" }),

  approveVariation: (id: string) =>
    request<Variation>(`/variations/${id}/approve`, { method: "POST" }),

  rejectVariation: (id: string) =>
    request<Variation>(`/variations/${id}/reject`, { method: "POST" }),

  voidVariation: (id: string) => request<Variation>(`/variations/${id}/void`, { method: "POST" }),

  // Same blob-download-and-save pattern as downloadInvoice/downloadDocument.
  downloadVariationPdf: async (id: string, reference: string): Promise<void> => {
    const token = getToken();
    let res: Response;

    try {
      res = await fetch(`${API_BASE_URL}/api/v1/variations/${id}/pdf`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
    } catch {
      throw new ApiError(`Could not reach the API at /variations/${id}/pdf`, 0);
    }

    if (!res.ok) {
      if (res.status === 401) clearToken();
      throw new ApiError(`Request to /variations/${id}/pdf failed with ${res.status}`, res.status);
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${reference}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },

  // --- GeoCore Premium OS Plan 05 (Sprint 044) — procurement + materials operations. ---
  getSuppliers: () => request<CatalogueSupplierSummary[]>("/catalogue/suppliers"),

  getSupplierAccounts: () => request<TenantSupplierAccount[]>("/procurement/supplier-accounts"),

  upsertSupplierAccount: (supplierId: string, fields: Partial<TenantSupplierAccount>) =>
    request<TenantSupplierAccount>(`/procurement/supplier-accounts/${supplierId}`, {
      method: "PUT",
      body: JSON.stringify(fields),
    }),

  getProjectRequirements: (projectId: string) =>
    request<MaterialRequirement[]>(`/projects/${projectId}/requirements`),

  createProjectRequirement: (projectId: string, data: MaterialRequirementIn) =>
    request<MaterialRequirement>(`/projects/${projectId}/requirements`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateRequirement: (requirementId: string, data: MaterialRequirementUpdate) =>
    request<MaterialRequirement>(`/requirements/${requirementId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  cancelRequirement: (requirementId: string) =>
    request<MaterialRequirement>(`/requirements/${requirementId}/cancel`, { method: "POST" }),

  getPurchaseOrders: (params: { projectId?: string; lateOnly?: boolean } = {}) => {
    const query = new URLSearchParams();
    if (params.projectId) query.set("project_id", params.projectId);
    if (params.lateOnly) query.set("late_only", "true");
    const qs = query.toString();
    return request<PurchaseOrder[]>(`/purchase-orders${qs ? `?${qs}` : ""}`);
  },

  createPurchaseOrder: (data: PurchaseOrderCreate) =>
    request<PurchaseOrder>("/purchase-orders", { method: "POST", body: JSON.stringify(data) }),

  getPurchaseOrder: (id: string) => request<PurchaseOrder>(`/purchase-orders/${id}`),

  updatePurchaseOrder: (id: string, data: PurchaseOrderUpdate) =>
    request<PurchaseOrder>(`/purchase-orders/${id}`, { method: "PATCH", body: JSON.stringify(data) }),

  approvePurchaseOrder: (id: string) =>
    request<PurchaseOrder>(`/purchase-orders/${id}/approve`, { method: "POST" }),

  orderPurchaseOrder: (id: string, data: OrderPurchaseOrderRequest) =>
    request<PurchaseOrder>(`/purchase-orders/${id}/order`, { method: "POST", body: JSON.stringify(data) }),

  cancelPurchaseOrder: (id: string) =>
    request<PurchaseOrder>(`/purchase-orders/${id}/cancel`, { method: "POST" }),

  getPurchaseOrderReceipts: (id: string) => request<PurchaseReceipt[]>(`/purchase-orders/${id}/receipts`),

  recordPurchaseOrderReceipt: (id: string, data: PurchaseReceiptCreate) =>
    request<PurchaseReceipt>(`/purchase-orders/${id}/receipts`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  downloadPurchaseOrderPdf: async (id: string, reference: string): Promise<void> => {
    const token = getToken();
    let res: Response;

    try {
      res = await fetch(`${API_BASE_URL}/api/v1/purchase-orders/${id}/pdf`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
    } catch {
      throw new ApiError(`Could not reach the API at /purchase-orders/${id}/pdf`, 0);
    }

    if (!res.ok) {
      if (res.status === 401) clearToken();
      throw new ApiError(`Request to /purchase-orders/${id}/pdf failed with ${res.status}`, res.status);
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${reference}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },

  getProjectAllocations: (projectId: string) =>
    request<MaterialAllocation[]>(`/projects/${projectId}/allocations`),

  allocateMaterial: (projectId: string, data: MaterialAllocationCreate) =>
    request<MaterialAllocation>(`/projects/${projectId}/allocations`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
};
