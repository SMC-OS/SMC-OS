"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { PlusIcon, SearchIcon } from "@/components/ui/icons";
import { NAV_ITEMS } from "@/lib/navigation";
import { cn } from "@/lib/utils";

interface Command {
  id: string;
  label: string;
  group: "Navigate" | "Quick actions";
  icon: (typeof NAV_ITEMS)[number]["icon"];
  run: () => void;
}

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);

  const commands = useMemo<Command[]>(() => {
    const navCommands: Command[] = NAV_ITEMS.map((item) => ({
      id: `nav-${item.href}`,
      label: item.label,
      group: "Navigate",
      icon: item.icon,
      run: () => router.push(item.href),
    }));

    const quickActions: Command[] = [
      {
        id: "action-new-quote",
        label: "New Quote",
        group: "Quick actions",
        icon: PlusIcon,
        run: () => router.push("/quotes/new"),
      },
      {
        id: "action-new-customer",
        label: "New Customer",
        group: "Quick actions",
        icon: PlusIcon,
        run: () => router.push("/customers/new"),
      },
      {
        id: "action-new-project",
        label: "New Project",
        group: "Quick actions",
        icon: PlusIcon,
        run: () => router.push("/projects/new"),
      },
    ];

    return [...navCommands, ...quickActions];
  }, [router]);

  const filtered = useMemo(() => {
    if (!query.trim()) return commands;
    const q = query.toLowerCase();
    return commands.filter((c) => c.label.toLowerCase().includes(q));
  }, [commands, query]);

  // Reset local state at the moment we close, rather than reactively via an
  // effect watching `open` — avoids a synchronous setState-in-effect and
  // means the palette always opens fresh next time.
  function close() {
    setQuery("");
    setActiveIndex(0);
    onOpenChange(false);
  }

  // Global Cmd/Ctrl+K shortcut
  useEffect(() => {
    function handleKeydown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (open) {
          close();
        } else {
          onOpenChange(true);
        }
      }
      if (event.key === "Escape") close();
    }
    window.addEventListener("keydown", handleKeydown);
    return () => window.removeEventListener("keydown", handleKeydown);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- close() is stable per render and only reads current `open`/`onOpenChange`
  }, [open, onOpenChange]);

  function handleQueryChange(value: string) {
    setQuery(value);
    setActiveIndex(0);
  }

  function runActive() {
    const command = filtered[activeIndex];
    if (!command) return;
    command.run();
    close();
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 px-4 pt-24">
      <button
        type="button"
        aria-label="Close search"
        className="absolute inset-0"
        onClick={close}
      />

      <div className="relative w-full max-w-lg overflow-hidden rounded-xl border border-border bg-surface shadow-2xl">
        <div className="flex items-center gap-2 border-b border-border px-4 py-3">
          <SearchIcon className="h-4 w-4 shrink-0 text-muted" />
          <input
            autoFocus
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActiveIndex((i) => Math.max(i - 1, 0));
              } else if (e.key === "Enter") {
                e.preventDefault();
                runActive();
              }
            }}
            placeholder="Search pages and actions…"
            className="w-full bg-transparent text-sm text-foreground outline-none placeholder:text-muted"
          />
          <kbd className="hidden rounded border border-border px-1.5 py-0.5 text-[10px] text-muted sm:block">
            Esc
          </kbd>
        </div>

        <div className="max-h-80 overflow-y-auto p-2">
          {filtered.length === 0 && (
            <p className="px-3 py-6 text-center text-sm text-muted">No matches.</p>
          )}

          {(["Navigate", "Quick actions"] as const).map((group) => {
            const items = filtered.filter((c) => c.group === group);
            if (items.length === 0) return null;

            return (
              <div key={group} className="mb-1 last:mb-0">
                <p className="px-3 py-1.5 text-[11px] font-medium uppercase tracking-wide text-muted">
                  {group}
                </p>
                {items.map((command) => {
                  const index = filtered.indexOf(command);
                  const CommandIcon = command.icon;

                  return (
                    <button
                      key={command.id}
                      type="button"
                      onMouseEnter={() => setActiveIndex(index)}
                      onClick={() => {
                        command.run();
                        close();
                      }}
                      className={cn(
                        "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm",
                        index === activeIndex
                          ? "bg-accent text-accent-foreground"
                          : "text-foreground hover:bg-surface-hover"
                      )}
                    >
                      <CommandIcon className="h-4 w-4 shrink-0" />
                      {command.label}
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
