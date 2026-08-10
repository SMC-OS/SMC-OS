import { ComingSoon } from "@/components/shell/ComingSoon";

export default function SettingsPage() {
  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Settings
        </h1>
        <p className="mt-1 text-sm text-muted">
          Account, team, and workspace settings.
        </p>
      </div>

      <ComingSoon
        title="Settings"
        description="Login exists now, but there's no account settings to configure yet. Staff management and permissions follow in v1.0."
        sprint="v1.0"
      />
    </div>
  );
}
