"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Field, Input, Select } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api";
import { PROJECT_STATUS_LABEL, PROJECT_STATUS_TONE } from "@/lib/projects";
import { formatRelativeTime } from "@/lib/utils";
import { PROJECT_STATUSES } from "@/types/project";
import type { AppointmentOut, AppointmentTransitionTarget } from "@/types/appointment";
import type { Customer } from "@/types/customer";
import type { Project } from "@/types/project";
import type { TeamMemberOut } from "@/types/user";

const APPOINTMENT_STATUS_TONE: Record<AppointmentOut["status"], "info" | "success" | "neutral"> = {
  scheduled: "info",
  completed: "success",
  cancelled: "neutral",
};

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { isAuthenticated, isReady, role } = useAuth();
  const [project, setProject] = useState<Project | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [advancing, setAdvancing] = useState(false);

  // Sprint 021 — enquiry-to-customer conversion (docs/SPRINTS/sprint-021.md).
  const [showConvertForm, setShowConvertForm] = useState(false);
  const [convertName, setConvertName] = useState("");
  const [convertEmail, setConvertEmail] = useState("");
  const [convertPhone, setConvertPhone] = useState("");
  const [converting, setConverting] = useState(false);

  // Sprint 022 — site visit scheduling (docs/SPRINTS/sprint-022.md).
  const [appointments, setAppointments] = useState<AppointmentOut[] | null>(null);
  const [appointmentError, setAppointmentError] = useState<string | null>(null);
  const [showScheduleForm, setShowScheduleForm] = useState(false);
  const [scheduleAt, setScheduleAt] = useState("");
  const [scheduleNotes, setScheduleNotes] = useState("");
  const [scheduling, setScheduling] = useState(false);
  const [transitioningId, setTransitioningId] = useState<string | null>(null);

  // Sprint 023 — project operations (docs/SPRINTS/sprint-023.md).
  const [teamMembers, setTeamMembers] = useState<TeamMemberOut[] | null>(null);
  const [operationsError, setOperationsError] = useState<string | null>(null);
  const [assigning, setAssigning] = useState(false);

  function load() {
    api
      .getProject(params.id)
      .then((p) => {
        setProject(p);
        if (p.customer_id) {
          api.getCustomer(p.customer_id).then(setCustomer).catch(() => {});
        }
      })
      .catch((err) =>
        setError(
          err instanceof ApiError && err.status === 404
            ? "Project not found."
            : "Something went wrong."
        )
      );
  }

  function loadAppointments() {
    api
      .getProjectAppointments(params.id)
      .then(setAppointments)
      .catch((err) =>
        setAppointmentError(err instanceof ApiError ? err.message : "Something went wrong.")
      );
  }

  const canManageAppointments = role === "Owner" || role === "Staff";
  const canAssign = role === "Owner";

  useEffect(() => {
    if (!isReady) return;
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }
    load();
    // Appointments are Owner/Staff only server-side (require_role(OWNER,
    // STAFF)) — same RBAC gating as convert-to-customer, so a caller
    // without that role never even requests the list.
    if (canManageAppointments) loadAppointments();
    // The team-member list backs the Owner-only Assign control — a
    // non-Owner never requests it.
    if (canAssign) {
      api
        .getUsers()
        .then(setTeamMembers)
        .catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isReady, isAuthenticated, params.id, canManageAppointments, canAssign]);

  if (!isReady || !isAuthenticated) return null;

  const currentIndex = project ? PROJECT_STATUSES.indexOf(project.status) : -1;
  const nextStatus =
    currentIndex >= 0 && currentIndex < PROJECT_STATUSES.length - 1
      ? PROJECT_STATUSES[currentIndex + 1]
      : null;

  async function handleAdvance() {
    if (!project || !nextStatus) return;
    setAdvancing(true);
    try {
      const updated = await api.updateProjectStatus(project.id, nextStatus);
      setProject(updated);
    } catch (err) {
      setOperationsError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setAdvancing(false);
    }
  }

  async function handleAssign(e: React.ChangeEvent<HTMLSelectElement>) {
    if (!project) return;
    const value = e.target.value;
    const assignedUserId = value === "" ? null : value;
    setAssigning(true);
    try {
      const updated = await api.assignProject(project.id, assignedUserId);
      // The server's returned Project is authoritative — applied only
      // after a successful response, never optimistically.
      setProject(updated);
    } catch (err) {
      setOperationsError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setAssigning(false);
    }
  }

  const showConvertAction =
    !!project &&
    project.status === "enquiry" &&
    project.customer_id == null &&
    canManageAppointments;

  async function handleConvert(e: React.FormEvent) {
    e.preventDefault();
    if (!project) return;
    setConverting(true);
    try {
      const convertedCustomer = await api.convertProjectToCustomer(project.id, {
        name: convertName,
        email: convertEmail || null,
        phone: convertPhone || null,
      });
      // The server's returned Customer is authoritative — applied only
      // after a successful response, never optimistically.
      setCustomer(convertedCustomer);
      setProject({ ...project, customer_id: convertedCustomer.id });
      setShowConvertForm(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setConverting(false);
    }
  }

  async function handleSchedule(e: React.FormEvent) {
    e.preventDefault();
    if (!project || !scheduleAt) return;
    setScheduling(true);
    try {
      // datetime-local has no timezone of its own — Date() interprets it
      // as local time, and toISOString() converts that to a tz-aware UTC
      // string, satisfying the backend's naive-datetime rejection
      // (app/appointments/models.py's scheduled_at validator).
      const created = await api.createAppointment(project.id, {
        scheduled_at: new Date(scheduleAt).toISOString(),
        notes: scheduleNotes || null,
      });
      setAppointments((prev) => [...(prev ?? []), created]);
      setShowScheduleForm(false);
      setScheduleAt("");
      setScheduleNotes("");
    } catch (err) {
      setAppointmentError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setScheduling(false);
    }
  }

  async function handleTransition(id: string, target: AppointmentTransitionTarget) {
    setTransitioningId(id);
    try {
      const updated =
        target === "completed" ? await api.completeAppointment(id) : await api.cancelAppointment(id);
      // The server's returned Appointment is authoritative — applied only
      // after a successful response, never optimistically.
      setAppointments((prev) =>
        (prev ?? []).map((appointment) => (appointment.id === id ? updated : appointment))
      );
    } catch (err) {
      setAppointmentError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setTransitioningId(null);
    }
  }

  return (
    <div className="mx-auto max-w-xl">
      <div className="mb-6">
        <Link href="/projects" className="text-sm text-muted hover:text-foreground">
          &larr; Projects
        </Link>
      </div>

      {error && (
        <Card>
          <CardContent>
            <p className="text-sm text-danger">{error}</p>
          </CardContent>
        </Card>
      )}

      {!error && !project && <p className="text-sm text-muted">Loading…</p>}

      {project && (
        <Card>
          <CardContent>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h1 className="text-xl font-semibold tracking-tight text-foreground">
                  {project.name}
                </h1>
                <p className="text-xs text-muted">
                  Started {formatRelativeTime(project.created_at)}
                </p>
              </div>
              <Badge tone={PROJECT_STATUS_TONE[project.status]}>
                {PROJECT_STATUS_LABEL[project.status]}
              </Badge>
            </div>

            <dl className="mt-6 space-y-3 border-t border-border pt-4">
              <div>
                <dt className="text-xs font-medium text-muted">Customer</dt>
                <dd className="text-sm text-foreground">
                  {customer ? (
                    <Link
                      href={`/customers/${customer.id}`}
                      className="text-accent hover:underline"
                    >
                      {customer.name}
                    </Link>
                  ) : (
                    "—"
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-muted">Notes</dt>
                <dd className="text-sm text-foreground">{project.notes ?? "—"}</dd>
              </div>
            </dl>

            <div className="mt-6 border-t border-border pt-4">
              <h2 className="text-sm font-semibold text-foreground">Project Operations</h2>

              {operationsError && (
                <p className="mt-2 text-sm text-danger">{operationsError}</p>
              )}

              <dl className="mt-3 space-y-3">
                <div>
                  <dt className="text-xs font-medium text-muted">Assigned to</dt>
                  <dd className="text-sm text-foreground">
                    {canAssign ? (
                      <Select
                        aria-label="Assigned to"
                        value={project.assigned_user_id ?? ""}
                        onChange={handleAssign}
                        disabled={assigning || !teamMembers}
                      >
                        <option value="">Unassigned</option>
                        {(teamMembers ?? []).map((member) => (
                          <option key={member.id} value={member.id}>
                            {member.name}
                          </option>
                        ))}
                      </Select>
                    ) : (
                      (teamMembers?.find((m) => m.id === project.assigned_user_id)?.name ??
                        (project.assigned_user_id ? project.assigned_user_id : "Unassigned"))
                    )}
                  </dd>
                </div>
              </dl>

              <div className="mt-4">
                {!canManageAppointments ? null : nextStatus ? (
                  <Button onClick={handleAdvance} disabled={advancing}>
                    {advancing
                      ? "Advancing…"
                      : `Advance to ${PROJECT_STATUS_LABEL[nextStatus]}`}
                  </Button>
                ) : (
                  <p className="text-sm text-muted">
                    This project has completed the pipeline.
                  </p>
                )}
              </div>
            </div>

            {showConvertAction && (
              <div className="mt-6 border-t border-border pt-4">
                {showConvertForm ? (
                  <form onSubmit={handleConvert} className="flex flex-col gap-4">
                    <Field label="Full name" htmlFor="convert-name">
                      <Input
                        id="convert-name"
                        required
                        value={convertName}
                        onChange={(e) => setConvertName(e.target.value)}
                        placeholder="e.g. James Okafor"
                      />
                    </Field>
                    <Field label="Email" htmlFor="convert-email">
                      <Input
                        id="convert-email"
                        type="email"
                        value={convertEmail}
                        onChange={(e) => setConvertEmail(e.target.value)}
                        placeholder="james@example.com"
                      />
                    </Field>
                    <Field label="Phone" htmlFor="convert-phone">
                      <Input
                        id="convert-phone"
                        value={convertPhone}
                        onChange={(e) => setConvertPhone(e.target.value)}
                        placeholder="07123 456789"
                      />
                    </Field>
                    <Button type="submit" disabled={converting}>
                      {converting ? "Saving…" : "Save customer"}
                    </Button>
                  </form>
                ) : (
                  <Button onClick={() => setShowConvertForm(true)} variant="outline">
                    Convert to Customer
                  </Button>
                )}
              </div>
            )}

            {canManageAppointments && (
              <div className="mt-6 border-t border-border pt-4">
                <h2 className="text-sm font-semibold text-foreground">Site Visits</h2>

                {appointmentError && (
                  <p className="mt-2 text-sm text-danger">{appointmentError}</p>
                )}

                <ul className="mt-3 space-y-2">
                  {(appointments ?? []).map((appointment) => (
                    <li
                      key={appointment.id}
                      className="flex items-center justify-between gap-3 rounded-md border border-border p-3"
                    >
                      <div>
                        <p className="text-sm text-foreground">
                          {new Date(appointment.scheduled_at).toLocaleString()}
                        </p>
                        {appointment.notes && (
                          <p className="text-xs text-muted">{appointment.notes}</p>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge tone={APPOINTMENT_STATUS_TONE[appointment.status]}>
                          {appointment.status}
                        </Badge>
                        {appointment.status === "scheduled" && (
                          <>
                            <Button
                              variant="outline"
                              onClick={() => handleTransition(appointment.id, "completed")}
                              disabled={transitioningId === appointment.id}
                            >
                              Complete
                            </Button>
                            <Button
                              variant="outline"
                              onClick={() => handleTransition(appointment.id, "cancelled")}
                              disabled={transitioningId === appointment.id}
                            >
                              Cancel
                            </Button>
                          </>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>

                {appointments && appointments.length === 0 && (
                  <p className="mt-2 text-sm text-muted">No site visits scheduled yet.</p>
                )}

                <div className="mt-4">
                  {showScheduleForm ? (
                    <form onSubmit={handleSchedule} className="flex flex-col gap-4">
                      <Field label="Date & time" htmlFor="schedule-at">
                        <Input
                          id="schedule-at"
                          type="datetime-local"
                          required
                          value={scheduleAt}
                          onChange={(e) => setScheduleAt(e.target.value)}
                        />
                      </Field>
                      <Field label="Notes" htmlFor="schedule-notes">
                        <Input
                          id="schedule-notes"
                          value={scheduleNotes}
                          onChange={(e) => setScheduleNotes(e.target.value)}
                          placeholder="e.g. Measure kitchen worktop"
                        />
                      </Field>
                      <Button type="submit" disabled={scheduling}>
                        {scheduling ? "Scheduling…" : "Save site visit"}
                      </Button>
                    </form>
                  ) : (
                    <Button onClick={() => setShowScheduleForm(true)} variant="outline">
                      Schedule Site Visit
                    </Button>
                  )}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
