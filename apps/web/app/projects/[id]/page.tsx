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
import { ProjectForm } from "@/components/projects/ProjectForm";
import { ProjectOverview } from "@/components/projects/ProjectOverview";
import { ProjectTasksPanel } from "@/components/projects/ProjectTasksPanel";
import { Project360Shell } from "@/components/projects/Project360Shell";
import type { Project360Tab } from "@/components/projects/Project360Shell";
import { WorkflowHistory } from "@/components/projects/WorkflowHistory";
import { WorkflowProgress } from "@/components/projects/WorkflowProgress";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";
import type { Trade } from "@/types/quote";
import type { AppointmentOut, AppointmentTransitionTarget } from "@/types/appointment";
import type { Customer } from "@/types/customer";
import type { Project } from "@/types/project";
import type { TeamMemberOut } from "@/types/user";
import type { ProjectWorkflowDetail, WorkflowHistoryEntry, WorkflowTransitionOption } from "@/types/workflow";

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

  // GeoCore Premium OS Plan 01 (Sprint 040, Task 8) — the trade-adaptive
  // workflow engine's own Project 360 tabs.
  const [workflowDetail, setWorkflowDetail] = useState<ProjectWorkflowDetail | null>(null);
  const [workflowHistory, setWorkflowHistory] = useState<WorkflowHistoryEntry[] | null>(null);
  const [workflowError, setWorkflowError] = useState<string | null>(null);
  const [transitioningStageKey, setTransitioningStageKey] = useState<string | null>(null);

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

  function loadWorkflow() {
    api
      .getProjectWorkflow(params.id)
      .then(setWorkflowDetail)
      .catch((err) =>
        setWorkflowError(err instanceof ApiError ? err.message : "Something went wrong.")
      );
    api
      .getProjectWorkflowHistory(params.id)
      .then(setWorkflowHistory)
      .catch(() => {});
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
    loadWorkflow();
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

  async function handleAppointmentTransition(id: string, target: AppointmentTransitionTarget) {
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

  async function handleWorkflowTransition(option: WorkflowTransitionOption) {
    if (!project) return;
    setWorkflowError(null);
    setTransitioningStageKey(option.stage_key);
    try {
      const updated = await api.transitionProjectWorkflow(project.id, option.stage_key);
      // The server's returned Project is authoritative — applied only
      // after a successful response, never optimistically.
      setProject(updated);
      // Re-fetch rather than derive locally: the newly-current stage's own
      // allowed_transitions/blocked_requirements are the backend's alone
      // to compute (gates, the graph, Resume's per-project target).
      loadWorkflow();
    } catch (err) {
      setWorkflowError(
        err instanceof ApiError
          ? err.status === 409
            ? "This move isn't available right now — try refreshing."
            : err.message
          : "Something went wrong."
      );
    } finally {
      setTransitioningStageKey(null);
    }
  }

  if (!project) {
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
        {!error && <p className="text-sm text-muted">Loading…</p>}
      </div>
    );
  }

  if (editing) {
    return (
      <div className="mx-auto max-w-xl">
        <div className="mb-6">
          <Link href="/projects" className="tap-link text-sm text-muted hover:text-foreground">
            &larr; Projects
          </Link>
        </div>
        <div className="mb-4 flex items-center justify-between gap-3">
          <h1 className="text-xl font-semibold tracking-tight text-foreground">Edit project</h1>
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
    );
  }

  const tabs: Project360Tab[] = [
    {
      key: "overview",
      label: "Overview",
      content: (
        <ProjectOverview
          project={project}
          customer={customer}
          currency={currency}
          showConvertAction={showConvertAction}
          showConvertForm={showConvertForm}
          convertName={convertName}
          convertEmail={convertEmail}
          convertPhone={convertPhone}
          converting={converting}
          onConvertNameChange={setConvertName}
          onConvertEmailChange={setConvertEmail}
          onConvertPhoneChange={setConvertPhone}
          onShowConvertForm={() => setShowConvertForm(true)}
          onConvertSubmit={handleConvert}
        />
      ),
    },
    {
      key: "workflow",
      label: "Workflow",
      content: (
        <div>
          {workflowError && <p className="mb-3 text-sm text-danger">{workflowError}</p>}
          {workflowDetail ? (
            <WorkflowProgress
              detail={workflowDetail}
              canManage={canManageAppointments}
              pendingKey={transitioningStageKey}
              onTransition={handleWorkflowTransition}
            />
          ) : (
            !workflowError && <p className="text-sm text-muted">Loading…</p>
          )}
        </div>
      ),
    },
  ];

  if (canManageAppointments) {
    tabs.push({
      key: "schedule",
      label: "Schedule",
      content: (
        <div>
          {appointmentError && <p className="mb-3 text-sm text-danger">{appointmentError}</p>}

          <ul className="space-y-2">
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
                        onClick={() => handleAppointmentTransition(appointment.id, "completed")}
                        disabled={transitioningId === appointment.id}
                      >
                        Complete
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => handleAppointmentTransition(appointment.id, "cancelled")}
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
      ),
    });
  }

  tabs.push({
    key: "team",
    label: "Team",
    content: (
      <div>
        {operationsError && <p className="mb-3 text-sm text-danger">{operationsError}</p>}
        <dl>
          <div>
            <dt className="text-xs font-medium text-muted">Assigned to</dt>
            <dd className="mt-1 text-sm text-foreground">
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
      </div>
    ),
  });

  tabs.push({
    key: "tasks",
    label: "Tasks",
    content: <ProjectTasksPanel projectId={project.id} />,
  });

  tabs.push({
    key: "timeline",
    label: "Timeline",
    content: workflowHistory ? (
      <WorkflowHistory history={workflowHistory} />
    ) : (
      <p className="text-sm text-muted">Loading…</p>
    ),
  });

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6">
        <Link href="/projects" className="tap-link text-sm text-muted hover:text-foreground">
          &larr; Projects
        </Link>
      </div>

      {error && (
        <Card className="mb-4">
          <CardContent>
            <p className="text-sm text-danger">{error}</p>
          </CardContent>
        </Card>
      )}

      <Project360Shell project={project} tradeLabel={tradeLabel} onEdit={() => setEditing(true)} tabs={tabs} />
    </div>
  );
}
