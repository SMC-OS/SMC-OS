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
import { findStage, nextStages, stageLabel, stageTone } from "@/lib/projects";
import { CommunicationTimeline } from "@/components/communications/CommunicationTimeline";
import { ProjectForm } from "@/components/projects/ProjectForm";
import { ProjectTasksPanel } from "@/components/projects/ProjectTasksPanel";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";
import { EditIcon } from "@/components/ui/icons";
import type { Trade } from "@/types/quote";
import { formatDate, formatMoney, formatRelativeTime } from "@/lib/utils";
import type { AppointmentOut, AppointmentTransitionTarget } from "@/types/appointment";
import type { Customer } from "@/types/customer";
import type { PipelineStage, Project } from "@/types/project";
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
  // Sprint 036 (Workstream F) — inline edit, reusing the same form the
  // create page uses so the two cannot drift apart.
  const [editing, setEditing] = useState(false);
  const [trades, setTrades] = useState<Trade[]>([]);
  const { currency } = useWorkspace();
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

  // Sprint 039 (Workstream D) — this tenant's own stages and the moves
  // each one allows, so the actions offered below are exactly the ones the
  // backend will accept.
  const [stages, setStages] = useState<PipelineStage[] | null>(null);
  const [pendingStage, setPendingStage] = useState<string | null>(null);

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

  function loadPipeline() {
    // A failed pipeline fetch degrades this panel to read-only rather than
    // erroring the whole page — someone came here to read a job, and the
    // stage controls are not the only thing on the screen.
    api
      .getProjectPipeline()
      .then((pipeline) => setStages(pipeline.stages))
      .catch(() => {});
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
    loadPipeline();
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
    // Sprint 036 — the trade vocabulary, so this page can render
    // "Roofing" rather than the stored key "roofing".
    api.getTrades().then(setTrades).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isReady, isAuthenticated, params.id, canManageAppointments, canAssign]);

  if (!isReady || !isAuthenticated) return null;

  const tradeLabel =
    trades.find((trade) => trade.key === project?.project_type)?.label ?? null;

  const currentStage = project ? findStage(stages, project.status) : undefined;
  const transitions = project ? nextStages(stages, project.status) : [];
  // Forward moves versus the two side states. Split so "put this job on
  // hold" never sits in the same visual slot as "move it to the next
  // stage" — they are different kinds of decision, and one of them is
  // hard to explain to a customer afterwards.
  const forwardMoves = transitions.filter((stage) => !stage.is_side_state);
  const sideMoves = transitions.filter((stage) => stage.is_side_state);
  const onHold = project?.status_role === "on_hold";

  async function handleStageChange(stageKey: string) {
    if (!project) return;
    setAdvancing(true);
    setPendingStage(stageKey);
    setOperationsError(null);
    try {
      const updated = await api.updateProjectStatus(project.id, stageKey);
      // The server's returned Project is authoritative — applied only
      // after a successful response, never optimistically.
      setProject(updated);
    } catch (err) {
      setOperationsError(
        err instanceof ApiError && err.status === 409
          ? "That move isn't available from this stage any more. Reload to see where this job is now."
          : err instanceof ApiError
            ? err.message
            : "Something went wrong."
      );
    } finally {
      setAdvancing(false);
      setPendingStage(null);
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
    project.status_role === "lead" &&
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
        <Link href="/projects" className="tap-link text-sm text-muted hover:text-foreground">
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

      {project && editing && (
        <div className="mb-6">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h1 className="text-xl font-semibold tracking-tight text-foreground">
              Edit project
            </h1>
            <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
          <ProjectForm
            initial={project}
            submitLabel="Save changes"
            onSubmit={async (values) => {
              setProject(await api.updateProject(project.id, values));
              setEditing(false);
            }}
          />
        </div>
      )}

      {project && !editing && (
        <Card>
          <CardContent>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <h1 className="truncate text-xl font-semibold tracking-tight text-foreground sm:text-2xl">
                  {project.name}
                </h1>
                <p className="text-xs text-muted">
                  {tradeLabel ? `${tradeLabel} · ` : ""}
                  Started {formatRelativeTime(project.created_at)}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Badge tone={stageTone(project.status_role)}>
                  {stageLabel(stages, project.status)}
                </Badge>
                <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
                  <EditIcon className="h-4 w-4" />
                  Edit
                </Button>
              </div>
            </div>

            {/* Sprint 036 (Workstream F) — the job, not just its name.
                Every field renders an em dash when absent rather than
                being hidden: a start date you have not set is information
                worth seeing on a project page. */}
            <dl className="mt-6 grid grid-cols-1 gap-4 border-t border-border pt-4 sm:grid-cols-2">
              <div className="min-w-0">
                <dt className="text-xs font-medium text-muted">Customer</dt>
                <dd className="truncate text-sm text-foreground">
                  {customer ? (
                    <Link
                      href={`/customers/${customer.id}`}
                      className="text-accent hover:underline"
                    >
                      {customer.company_name || customer.name}
                    </Link>
                  ) : (
                    "—"
                  )}
                </dd>
              </div>
              <div className="min-w-0">
                <dt className="text-xs font-medium text-muted">Value</dt>
                <dd className="text-sm text-foreground">
                  {project.estimated_value != null
                    ? formatMoney(project.estimated_value, currency)
                    : "—"}
                </dd>
              </div>
              <div className="min-w-0">
                <dt className="text-xs font-medium text-muted">Starts</dt>
                <dd className="text-sm text-foreground">{formatDate(project.start_date)}</dd>
              </div>
              <div className="min-w-0">
                <dt className="text-xs font-medium text-muted">Target completion</dt>
                <dd className="text-sm text-foreground">
                  {formatDate(project.target_completion_date)}
                </dd>
              </div>
              <div className="min-w-0 sm:col-span-2">
                <dt className="text-xs font-medium text-muted">Site</dt>
                <dd className="text-sm text-foreground">
                  {[
                    project.site_address_line1,
                    project.site_address_line2,
                    project.site_city,
                    project.site_postcode,
                  ]
                    .filter(Boolean)
                    .join(", ") || "—"}
                </dd>
              </div>
              {project.description && (
                <div className="min-w-0 sm:col-span-2">
                  <dt className="text-xs font-medium text-muted">Description</dt>
                  <dd className="whitespace-pre-wrap text-sm text-foreground">
                    {project.description}
                  </dd>
                </div>
              )}
              <div className="min-w-0 sm:col-span-2">
                <dt className="text-xs font-medium text-muted">Notes</dt>
                <dd className="whitespace-pre-wrap text-sm text-foreground">
                  {project.notes ?? "—"}
                </dd>
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
                {!canManageAppointments ? (
                  // Permission-denied is stated, not silently hidden:
                  // someone who cannot move a job should understand why
                  // the controls are absent rather than assume the page
                  // is broken.
                  <p className="text-sm text-muted">
                    Only an owner or a member of staff can move a job through
                    the pipeline.
                  </p>
                ) : currentStage?.is_terminal ? (
                  <p className="text-sm text-muted">
                    This job is closed. Nothing more happens to it.
                  </p>
                ) : transitions.length === 0 ? (
                  <p className="text-sm text-muted">
                    No stage changes are available for this job.
                  </p>
                ) : (
                  <div className="flex flex-col gap-3">
                    {forwardMoves.length > 0 && (
                      <div>
                        {onHold && (
                          <p className="mb-2 text-xs font-medium text-muted">
                            Resume this job at
                          </p>
                        )}
                        <div className="flex flex-wrap gap-2">
                          {forwardMoves.map((stage, index) => (
                            <Button
                              key={stage.key}
                              variant={index === 0 ? "primary" : "outline"}
                              onClick={() => handleStageChange(stage.key)}
                              disabled={advancing}
                            >
                              {advancing && pendingStage === stage.key
                                ? "Saving…"
                                : onHold
                                  ? stage.label
                                  : `Advance to ${stage.label}`}
                            </Button>
                          ))}
                        </div>
                      </div>
                    )}

                    {sideMoves.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {sideMoves.map((stage) => (
                          <Button
                            key={stage.key}
                            variant={stage.role === "cancelled" ? "danger" : "secondary"}
                            size="sm"
                            onClick={() => handleStageChange(stage.key)}
                            disabled={advancing}
                          >
                            {advancing && pendingStage === stage.key
                              ? "Saving…"
                              : stage.role === "cancelled"
                                ? "Cancel this job"
                                : `Put on ${stage.label.toLowerCase()}`}
                          </Button>
                        ))}
                      </div>
                    )}
                  </div>
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
      {project && !editing && <ProjectTasksPanel projectId={project.id} />}

      {/* Sprint 039 (Workstream A) — what has actually been said to this
          customer about this job, and whether it arrived. */}
      {project && !editing && (
        <div className="mt-6">
          <CommunicationTimeline
            title="Communications"
            filters={{ projectId: project.id }}
            emptyTitle="Nothing sent about this job yet"
            emptyDescription="Emails GeoCore sends about this project will appear here."
          />
        </div>
      )}

    </div>
  );
}
