"use client";

import { useEffect } from "react";

import { captureUtmParams, track } from "../start/tracker";

/**
 * Mount-once landing tracker for /founding-100. Renders nothing.
 *
 * Reuses the /start tracking layer unchanged: UTM parameters are captured
 * (persisted only with the "preferences" consent) and the view event is
 * pushed to the dataLayer only with the "analytics" consent. Nothing is
 * sent anywhere by this component itself.
 */
export function FoundingTracker() {
  useEffect(() => {
    const utm = captureUtmParams();
    track("founding_100_view", {
      page: "/founding-100",
      ...utm,
      has_utm: Object.keys(utm).length > 0,
    });
  }, []);
  return null;
}
