import Link from "next/link";

import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { FolderIcon, PlusIcon, UsersIcon } from "@/components/ui/icons";

const ACTIONS = [
  { label: "New Quote", href: "/quotes/new", icon: PlusIcon },
  { label: "New Customer", href: "/customers/new", icon: UsersIcon },
  { label: "New Project", href: "/projects/new", icon: FolderIcon },
];

export function QuickActions() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Quick Actions</CardTitle>
      </CardHeader>
      <div className="grid grid-cols-1 gap-2 p-5 pt-4 sm:grid-cols-3">
        {ACTIONS.map((action) => {
          const ActionIcon = action.icon;

          return (
            <Link
              key={action.href}
              href={action.href}
              className="flex items-center gap-2.5 rounded-lg border border-border px-4 py-3 text-sm font-medium text-foreground transition-colors hover:border-accent/50 hover:bg-surface-hover"
            >
              <ActionIcon className="h-4 w-4 text-accent" />
              {action.label}
            </Link>
          );
        })}
      </div>
    </Card>
  );
}
