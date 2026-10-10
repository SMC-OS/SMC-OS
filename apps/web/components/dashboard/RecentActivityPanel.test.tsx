import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { RecentActivityPanel } from "./RecentActivityPanel";

const { activity } = vi.hoisted(() => ({ activity: { data: [] as Record<string, string>[], status: "success" } }));
vi.mock("@/hooks/useActivity", () => ({ useActivity: () => activity }));
afterEach(cleanup);

// Read the actual backend contract so new server event types cannot silently
// escape coverage by also being absent from a handwritten frontend fixture.
const backend = readFileSync(resolve(process.cwd(), "../../app/activity/models.py"), "utf8");
const enumBody = backend.split("class ActivityType(str, Enum):")[1].split("class ActivityEventCreate")[0];
const types = [...enumBody.matchAll(/^\s+[A-Z_]+ = "([a-z_]+)"/gm)].map((match) => match[1]);
it.each(types)("renders backend event %s without crashing the dashboard", (type) => {
  activity.data = [{ id: type, type, title: `Event ${type}`, description: "Audit detail", timestamp: new Date().toISOString() }];
  render(<RecentActivityPanel />);
  expect(screen.getByText(`Event ${type}`)).toBeVisible();
  expect(screen.getByText("Audit detail")).toBeVisible();
});
it("retains an unfamiliar server event with neutral presentation", () => {
  activity.data = [{ id: "future", type: "future_server_event", title: "Future event", timestamp: new Date().toISOString() }];
  render(<RecentActivityPanel />);
  expect(screen.getByText("Future event")).toBeVisible();
});
