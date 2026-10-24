"""Thread-safe login rate limiter using in-memory sliding window."""

from __future__ import annotations

import threading
import time

from app.core.errors import AppException


class LoginRateLimiter:
    """Sliding-window in-memory rate limiter to mitigate brute-force credential stuffing."""

    def __init__(self, max_attempts: int = 5, window_seconds: int = 60):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        """Verify whether the key has exceeded permitted failed attempts within window."""
        now = time.monotonic()
        with self._lock:
            timestamps = self._failures.get(key, [])
            # Prune old timestamps
            active_timestamps = [t for t in timestamps if now - t < self.window_seconds]
            self._failures[key] = active_timestamps

            if len(active_timestamps) >= self.max_attempts:
                retry_after = int(self.window_seconds - (now - active_timestamps[0])) + 1
                raise AppException(
                    message=f"Too many failed login attempts. Please try again in {retry_after} seconds.",
                    status_code=429,
                    error_code="RATE_LIMIT_EXCEEDED",
                    details={"retry_after_seconds": max(1, retry_after)},
                )

    def record_failure(self, key: str) -> None:
        """Record an unauthenticated attempt timestamp."""
        now = time.monotonic()
        with self._lock:
            timestamps = self._failures.setdefault(key, [])
            timestamps.append(now)

    def record_success(self, key: str) -> None:
        """Reset counter upon successful authentication."""
        with self._lock:
            self._failures.pop(key, None)

    def reset(self) -> None:
        """Clear all rate limiter state (for tests)."""
        with self._lock:
            self._failures.clear()


login_rate_limiter = LoginRateLimiter(max_attempts=5, window_seconds=60)
