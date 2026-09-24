"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

import { APP_URL } from "@/lib/site";

import { useSignupHref } from "./start-client";
import { track } from "./tracker";

const DISMISS_KEY = "geocore_start_sticky_dismissed";

const noopSubscribe = () => () => {};

function readDismissed(): boolean {
  try {
    return window.sessionStorage.getItem(DISMISS_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * Mobile-only sticky bottom CTA. Appears after the hero scrolls out of
 * view, stays dismissed once closed, and is hidden entirely at ≥768px by
 * CSS (`.start-sticky`).
 */
export function StickyCta() {
  const [pastHero, setPastHero] = useState(false);
  const [closedThisSession, setClosedThisSession] = useState(false);
  const href = useSignupHref(`${APP_URL}/signup`);
  // Server snapshot `true` keeps the bar out of the SSR HTML entirely.
  const previouslyDismissed = useSyncExternalStore(
    noopSubscribe,
    readDismissed,
    () => true,
  );

  useEffect(() => {
    const hero = document.getElementById("start-hero");
    if (!hero || !("IntersectionObserver" in window)) {
      const onScroll = () =>
        setPastHero(window.scrollY > window.innerHeight * 0.75);
      window.addEventListener("scroll", onScroll, { passive: true });
      onScroll();
      return () => window.removeEventListener("scroll", onScroll);
    }

    const observer = new IntersectionObserver(
      ([entry]) => setPastHero(!entry.isIntersecting),
      { rootMargin: "-10% 0px 0px 0px" },
    );
    observer.observe(hero);
    return () => observer.disconnect();
  }, []);

  if (previouslyDismissed || closedThisSession || !pastHero) return null;

  return (
    <div className="start-sticky" role="complementary" aria-label="Start your free trial">
      <a
        className="button button--primary start-sticky__cta"
        href={href}
        onClick={() => {
          track("sticky_trial_clicked");
          // Custom event only — never Meta's standard StartTrial (see
          // TrackedLink in start-client.tsx).
          track("signup_started", { via: "sticky_trial_clicked" });
        }}
      >
        Start free for 14 days →
      </a>
      <button
        type="button"
        className="start-sticky__close"
        aria-label="Dismiss"
        onClick={() => {
          setClosedThisSession(true);
          try {
            window.sessionStorage.setItem(DISMISS_KEY, "1");
          } catch {
            // Session storage unavailable — dismissal lasts for this mount.
          }
        }}
      >
        ×
      </button>
    </div>
  );
}
