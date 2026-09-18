/** GeoCore Premium OS Plan 05 (Sprint 044) — mirrors app/procurement/models.py.
 * Project -> Material Requirement -> Purchase Order -> Ordered -> Part
 * Received -> Fully Received -> Allocated -> Used/Closed, trade-neutral. */

export const REQUIREMENT_STATUSES = [
  "planned",
  "required",
  "ordered",
  "partially_received",
  "received",
  "allocated",
  "consumed",
  "cancelled",
] as const;
export type RequirementStatus = (typeof REQUIREMENT_STATUSES)[number];

export const REQUIREMENT_STATUS_LABELS: Record<RequirementStatus, string> = {
  planned: "Planned",
  required: "Required",
  ordered: "Ordered",
  partially_received: "Partially received",
  received: "Received",
  allocated: "Allocated",
  consumed: "Consumed",
  cancelled: "Cancelled",
};

export const REQUIREMENT_STATUS_TONE: Record<
  RequirementStatus,
  "neutral" | "info" | "success" | "danger"
> = {
  planned: "neutral",
  required: "info",
  ordered: "info",
  partially_received: "info",
  received: "success",
  allocated: "success",
  consumed: "success",
  cancelled: "danger",
};

export interface MaterialRequirementIn {
  description: string;
  catalogue_surface_id?: string | null;
  catalogue_variant_id?: string | null;
  custom_material_name?: string | null;
  material_family?: string | null;
  required_quantity?: number | null;
  unit?: string | null;
  required_by_date?: string | null;
  preferred_supplier_id?: string | null;
  status?: RequirementStatus;
  notes?: string | null;
  source_type?: string | null;
  source_id?: string | null;
}

export type MaterialRequirementUpdate = Partial<MaterialRequirementIn>;

export interface MaterialRequirement {
  id: string;
  project_id: string;
  description: string;
  catalogue_surface_id: string | null;
  catalogue_variant_id: string | null;
  custom_material_name: string | null;
  material_family: string | null;
  required_quantity: number | null;
  unit: string | null;
  required_by_date: string | null;
  preferred_supplier_id: string | null;
  status: RequirementStatus;
  notes: string | null;
  source_type: string | null;
  source_id: string | null;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

// --- Purchase orders -------------------------------------------------------

export const PO_STATUSES = [
  "draft",
  "approved",
  "ordered",
  "partially_received",
  "received",
  "cancelled",
] as const;
export type PurchaseOrderStatus = (typeof PO_STATUSES)[number];

export const PO_STATUS_LABELS: Record<PurchaseOrderStatus, string> = {
  draft: "Draft",
  approved: "Approved",
  ordered: "Ordered",
  partially_received: "Partially received",
  received: "Received",
  cancelled: "Cancelled",
};

export const PO_STATUS_TONE: Record<PurchaseOrderStatus, "neutral" | "info" | "success" | "danger"> = {
  draft: "neutral",
  approved: "info",
  ordered: "info",
  partially_received: "info",
  received: "success",
  cancelled: "danger",
};

export interface PurchaseOrderItemIn {
  description: string;
  material_requirement_id?: string | null;
  catalogue_surface_id?: string | null;
  catalogue_variant_id?: string | null;
  quantity: number;
  unit: string;
  unit_cost: number;
}

export interface PurchaseOrderItem {
  id: string;
  material_requirement_id: string | null;
  catalogue_surface_id: string | null;
  catalogue_variant_id: string | null;
  description: string;
  quantity: number;
  unit: string;
  unit_cost: number;
  line_total: number;
  quantity_received: number;
}

export interface PurchaseOrderCreate {
  project_id?: string | null;
  supplier_id?: string | null;
  expected_delivery_date?: string | null;
  notes?: string | null;
  vat_rate?: number;
  items?: PurchaseOrderItemIn[];
}

export interface PurchaseOrderUpdate {
  supplier_id?: string | null;
  expected_delivery_date?: string | null;
  notes?: string | null;
  vat_rate?: number;
  items?: PurchaseOrderItemIn[];
}

export interface OrderPurchaseOrderRequest {
  supplier_reference?: string | null;
  expected_delivery_date?: string | null;
}

export interface PurchaseOrder {
  id: string;
  project_id: string | null;
  supplier_id: string | null;
  reference: string;
  status: PurchaseOrderStatus;
  order_date: string | null;
  expected_delivery_date: string | null;
  received_date: string | null;
  supplier_reference: string | null;
  notes: string | null;
  vat_rate: number;
  subtotal: number;
  vat: number;
  total: number;
  created_by_user_id: string | null;
  approved_by_user_id: string | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
  items: PurchaseOrderItem[];
  is_late: boolean;
}

// --- Receipts ----------------------------------------------------------

export interface PurchaseReceiptItemIn {
  purchase_order_item_id: string;
  quantity_received: number;
}

export interface PurchaseReceiptCreate {
  received_at: string;
  delivery_reference?: string | null;
  notes?: string | null;
  items: PurchaseReceiptItemIn[];
}

export interface PurchaseReceiptItem {
  id: string;
  purchase_order_item_id: string;
  quantity_received: number;
}

export interface PurchaseReceipt {
  id: string;
  purchase_order_id: string;
  received_at: string;
  received_by_user_id: string | null;
  delivery_reference: string | null;
  notes: string | null;
  created_at: string;
  items: PurchaseReceiptItem[];
}

// --- Allocations -------------------------------------------------------

export interface MaterialAllocationCreate {
  material_requirement_id?: string | null;
  purchase_order_item_id?: string | null;
  quantity: number;
  notes?: string | null;
}

export interface MaterialAllocation {
  id: string;
  project_id: string;
  material_requirement_id: string | null;
  purchase_order_item_id: string | null;
  quantity: number;
  allocated_by_user_id: string | null;
  notes: string | null;
  created_at: string;
}

// --- Suppliers -----------------------------------------------------------

export interface CatalogueSupplierSummary {
  id: string;
  name: string;
  slug: string;
}

export interface TenantSupplierAccount {
  id: string;
  tenant_id: string;
  supplier_id: string;
  account_reference: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  payment_terms: string | null;
  delivery_notes: string | null;
  private_notes: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}
