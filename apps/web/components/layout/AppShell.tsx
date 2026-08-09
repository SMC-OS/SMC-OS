import { SidebarProvider } from "./SidebarContext";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

/**
 * The shell every page in the app renders inside of (wired in
 * app/layout.tsx). Future modules — Customers, Quotes, Projects, and
 * anything after them — only need to add a route under app/; they don't
 * need to touch this file to get the sidebar, topbar, search, notifications,
 * or dark mode.
 */
export default function AppShell({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <SidebarProvider>
      <div className="flex h-screen overflow-hidden bg-background">
        <Sidebar />

        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar />

          <main className="flex-1 overflow-y-auto p-4 lg:p-8">{children}</main>
        </div>
      </div>
    </SidebarProvider>
  );
}
