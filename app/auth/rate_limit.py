"""In-process fixed-window brute-force throttle for POST /auth/login.

Sprint 026 (docs/SPRINTS/sprint-026.md Contract B) — no Redis or shared
cache exists in this stack, so this is deliberately in-memory and
per-process: it protects a single running API instance and resets on
restart/redeploy, the same accepted single-instance limitation as
UPLOAD_DIR (ADR-032). That's a real, accepted limitation, not a
distributed rate limiter — it is meaningful against today's actual
deployment (one Railway API instance) and against an unthrottled
brute-force script, which is the verified real gap this closes.

Only failed attempts count toward the limit — a successful login always
clears the counter for that email via reset(), so normal use (including
tests that log in the same account many times) is never affected.
"""

import threading
import time
from dataclasses import dataclass

from fastapi import HTTPException, status


@dataclass
class _Window:
    count: int = 0
    started_at: float = 0.0


class LoginRateLimiter:
    def __init__(self, *, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._windows: dict[str, _Window] = {}

    @staticmethod
    def _key(email: str) -> str:
        return email.strip().lower()

    def check(self, email: str, *, max_attempts: int, window_seconds: float) -> None:
        key = self._key(email)
        now = self._clock()
        with self._lock:
            window = self._windows.get(key)
            if window is None or now - window.started_at >= window_seconds:
                return
            if window.count >= max_attempts:
                retry_after = max(0, int(window_seconds - (now - window.started_at)) + 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many failed login attempts. Try again later.",
                    headers={"Retry-After": str(retry_after)},
                )

    def record_failure(self, email: str, *, window_seconds: float) -> None:
        key = self._key(email)
        now = self._clock()
        with self._lock:
            window = self._windows.get(key)
            if window is None or now - window.started_at >= window_seconds:
                self._windows[key] = _Window(count=1, started_at=now)
            else:
                window.count += 1

    def reset(self, email: str) -> None:
        key = self._key(email)
        with self._lock:
            self._windows.pop(key, None)


login_rate_limiter = LoginRateLimiter()
