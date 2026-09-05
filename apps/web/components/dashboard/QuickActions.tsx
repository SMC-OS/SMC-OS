import Link from "next/link";

import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import {
  CalendarIcon,
  FileTextIcon,
  FolderIcon,
  UsersIcon,
  ZapIcon,
} from "@/components/ui/icons";

/**
 * Sprint 036 (Workstream C) — the actions a construction business
 * actually starts its day with. "New quote" leads because it is the
 * revenue-generating one, and it goes to the general construction quote
 * builder rather than the stone form.
 */
const ACTIONS = [
  { label: "New quote", href: "/quotes/new", icon: FileTextIcon },
  { label: "New customer", href: "/customers/new", icon: UsersIcon },
  { label: "New project", href: "/projects/new", icon: FolderIcon },
  { label: "Calendar", href: "/calendar", icon: CalendarIcon },
  { label: "Automations", href: "/automations", icon: ZapIcon },
];

export function QuickActions() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Quick actions</CardTitle>
      </CardHeader>
      <div className="grid grid-cols-1 gap-2 p-5 pt-4 sm:grid-cols-2 lg:grid-cols-1">
        {ACTIONS.map((action) => {
          const ActionIcon = action.icon;

          return (
            <Link
              key={action.href}
              href={action.href}
              className="flex items-center gap-2.5 rounded-lg border border-border px-4 py-3 text-sm font-medium text-foreground transition-colors hover:border-border-strong hover:bg-surface-hover"
            >
              <ActionIcon className="h-4 w-4 shrink-0 text-accent" />
              <span className="truncate">{action.label}</span>
            </Link>
          );
        })}
      </div>
    </Card>
  );
}
