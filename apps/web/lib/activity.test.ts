/**
 * Sprint 025 finding (docs/SPRINTS/sprint-025.md): ACTIVITY_ICON/
 * ACTIVITY_TONE had drifted out of sync with the backend's ActivityType
 * enum since Sprint 020 — an unmapped type crashed the entire dashboard
 * page (RecentActivityPanel indexes these maps with no fallback). This
 * test locks every ActivityType value in as covered, so a future backend
 * enum addition that isn't mirrored here fails at compile time (the
 * Record<ActivityType, ...> type itself) and this test documents why.
 */

import { describe, expect, it } from "vitest";

import { ACTIVITY_ICON, ACTIVITY_TONE } from "./activity";
import type { ActivityType } from "@/types/activity";

const ALL_TYPES: ActivityType[] = [
  "quote_created",
  "customer_added",
  "project_created",
  "invoice_generated",
  "ai_request",
  "user_login",
  "tenant_created",
  "portal_link_created",
  "team_member_deactivated",
  "customer_message_received",
  "quote_approved",
  "quote_handed_off",
  "enquiry_converted",
  "site_visit_scheduled",
  "site_visit_completed",
  "site_visit_cancelled",
  "project_assigned",
  "project_status_changed",
];

describe("ACTIVITY_ICON / ACTIVITY_TONE coverage", () => {
  it.each(ALL_TYPES)("every ActivityType has an icon and a tone: %s", (type) => {
    expect(ACTIVITY_ICON[type]).toBeDefined();
    expect(ACTIVITY_TONE[type]).toBeDefined();
  });
});
