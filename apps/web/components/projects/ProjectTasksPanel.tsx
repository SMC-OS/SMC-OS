"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, EmptyState } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { CheckIcon, PlusIcon } from "@/components/ui/icons";
import { ApiError, api } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import type { Task } from "@/types/task";

/**
 * Tasks on a project — Sprint 036, Workstream F.
 *
 * The extensible foundation the sprint contract asks for, kept
 * deliberately small: a title, an optional due date, and done/not done.
 * There are no subtasks, dependencies, checklists or boards, because
 * establishing the right foundation is this sprint's job and building a
 * project-management suite on top of a schema that has had a tasks table
 * for a day is not.
 *
 * Tasks created here carry source_type/source_id pointing at this
 * project, which is the same link an automation's `create_task` action
 * uses — so a task a person adds and a task an automation adds appear
 * together, here and on the dashboard.
 */
export function ProjectTasksPanel({ projectId }: { projectId: string }) {
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .getTasks(undefined, 100)
      // Filtered client-side: /tasks has no source filter, and adding a
      // query parameter to the API for a list that is already bounded at
      // 100 rows per workspace would be an endpoint change for no gain.
      .then((all) =>
        setTasks(all.filter((task) => task.source_id === projectId))
      )
      .catch(() => setError("Could not load tasks."));
  }, [projectId]);

  async function addTask(event: React.FormEvent) {
    event.preventDefault();
    if (!title.trim()) return;

    setSaving(true);
    setError(null);
    try {
      const created = await api.createTask({
        title: title.trim(),
        // <input type="datetime-local"> gives a local wall-clock string
        // with no zone. new Date() interprets it in the browser's own
        // timezone, which is what the person meant, and toISOString()
        // hands the server a real UTC instant.
        due_at: dueAt ? new Date(dueAt).toISOString() : null,
        source_type: "project",
        source_id: projectId,
      });
      setTasks((current) => [...(current ?? []), created]);
      setTitle("");
      setDueAt("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add the task.");
    } finally {
      setSaving(false);
    }
  }

  async function complete(id: string) {
    try {
      const updated = await api.updateTaskStatus(id, "done");
      setTasks((current) =>
        (current ?? []).map((task) => (task.id === id ? updated : task))
      );
    } catch {
      setError("Could not update the task.");
    }
  }

  const open = (tasks ?? []).filter((task) => task.status === "open");
  const done = (tasks ?? []).filter((task) => task.status !== "open");

  return (
    <Card className="mt-6">
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle>Tasks</CardTitle>
        {open.length > 0 && <Badge tone="neutral">{open.length} open</Badge>}
      </CardHeader>

      <CardContent className="pt-4">
        <form onSubmit={addTask} className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <Field label="New task" htmlFor="taskTitle" className="flex-1">
            <Input
              id="taskTitle"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Order the sanitaryware"
            />
          </Field>
          <Field label="Due" htmlFor="taskDue" className="sm:w-56">
            <Input
              id="taskDue"
              type="datetime-local"
              value={dueAt}
              onChange={(e) => setDueAt(e.target.value)}
            />
          </Field>
          <Button type="submit" disabled={saving || !title.trim()}>
            <PlusIcon className="h-4 w-4" />
            Add
          </Button>
        </form>

        {error && <p className="mt-3 text-sm text-danger">{error}</p>}

        {tasks && tasks.length === 0 && (
          <EmptyState
            title="No tasks on this project"
            description="Add one above, or let an automation create follow-ups for you."
            className="py-8"
          />
        )}

        {open.length > 0 && (
          <ul className="mt-4 divide-y divide-border border-t border-border">
            {open.map((task) => (
              <li key={task.id} className="flex items-start gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-foreground">{task.title}</p>
                  {task.due_at && (
                    <p className="text-xs text-muted">Due {formatDateTime(task.due_at)}</p>
                  )}
                  {task.body && (
                    <p className="mt-1 whitespace-pre-wrap text-xs text-muted">{task.body}</p>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => complete(task.id)}
                  aria-label={`Mark "${task.title}" as done`}
                >
                  <CheckIcon className="h-4 w-4" />
                  <span className="hidden sm:inline">Done</span>
                </Button>
              </li>
            ))}
          </ul>
        )}

        {done.length > 0 && (
          <ul className="mt-4 divide-y divide-border border-t border-border">
            {done.map((task) => (
              <li key={task.id} className="flex items-center gap-3 py-2.5">
                <CheckIcon className="h-4 w-4 shrink-0 text-success" />
                <p className="min-w-0 flex-1 truncate text-sm text-muted line-through">
                  {task.title}
                </p>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
