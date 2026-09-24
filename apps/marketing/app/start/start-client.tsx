"use client";

import { useEffect, useSyncExternalStore, type ReactNode } from "react";

import { initStartTracking, signupUrl, track } from "./tracker";

/** Mount-once tracker bootstrap for the /start page. Renders nothing. */
export function StartTracker() {
  useEffect(() => {
    initStartTracking();
  }, []);
  return null;
}

const noopSubscribe = () => () => {};

/**
 * Signup href with persisted UTM params. The server snapshot is the plain
 * URL (crawlable, hydration-stable); after hydration React re-reads the
 * client snapshot and the href gains the stored campaign params.
 */
export function useSignupHref(base: string): string {
  return useSyncExternalStore(
    noopSubscribe,
    () => signupUrl(base),
    () => base,
  );
}

type TrackedLinkProps = {
  /** Base signup URL (no query); persisted UTM params are appended on mount. */
  href: string;
  event: string;
  eventProps?: Record<string, unknown>;
  className?: string;
  children: ReactNode;
};

/** Signup CTA link with UTM-carrying href and click tracking. */
export function TrackedLink({
  href,
  event,
  eventProps,
  className,
  children,
}: TrackedLinkProps) {
  const resolvedHref = useSignupHref(href);

  return (
    <a
      className={className}
      href={resolvedHref}
      onClick={() => {
        track(event, eventProps);
        // Every signup-bound CTA also fires signup_started. This is a
        // custom dataLayer/fbq trackCustom event only — it must NEVER be
        // mapped to Meta's standard StartTrial event, which may only fire
        // once the app confirms a trial actually exists.
        track("signup_started", { via: event, ...eventProps });
      }}
    >
      {children}
    </a>
  );
}

type TrackedAnchorProps = {
  /** Destination is used verbatim — no UTM rewriting (non-signup links). */
  href: string;
  event: string;
  eventProps?: Record<string, unknown>;
  className?: string;
  children: ReactNode;
};

/** Non-signup link (Log in, Book a demo) with click tracking only. */
export function TrackedAnchor({
  href,
  event,
  eventProps,
  className,
  children,
}: TrackedAnchorProps) {
  return (
    <a
      className={className}
      href={href}
      onClick={() => track(event, eventProps)}
    >
      {children}
    </a>
  );
}
