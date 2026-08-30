// Sprint 022 — mirrors app/appointments/models.py's AppointmentOut.

export const APPOINTMENT_STATUSES = ["scheduled", "completed", "cancelled"] as const;

export type AppointmentStatus = (typeof APPOINTMENT_STATUSES)[number];

// Only ever a valid transition target — same reasoning as the backend's
// AppointmentTransitionTarget (app/appointments/models.py): there is no
// path that submits "scheduled".
export type AppointmentTransitionTarget = "completed" | "cancelled";

export interface AppointmentCreate {
  scheduled_at: string;
  notes?: string | null;
}

export interface AppointmentOut {
  id: string;
  tenant_id: string;
  project_id: string;
  created_by_user_id: string;
  scheduled_at: string;
  status: AppointmentStatus;
  notes: string | null;
  created_at: string;
}
