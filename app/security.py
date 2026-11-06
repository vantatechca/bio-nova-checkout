"""Authentication helpers: store API keys, admin tokens, login throttling, client IP."""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
from collections import deque

from fastapi import Request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.errors import TooManyRequests


def constant_time_equals(a: str, b: str) -> bool:
    """Compares via fixed-length digests so neither content nor length leaks through timing."""
    return hmac.compare_digest(hashlib.sha256(a.encode()).digest(), hashlib.sha256(b.encode()).digest())


def bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    return header[7:].strip() if header.lower().startswith("bearer ") else ""


def client_ip(request: Request) -> str:
    """The caller's address. Behind a proxy, enable TRUST_PROXY (uvicorn then resolves X-Forwarded-For)."""
    return request.client.host if request.client else "unknown"


class AdminTokens:
    """Stateless signed tokens: they survive restarts and work across multiple app instances."""

    SALT = "admin-token"

    @classmethod
    def issue(cls, secret: str) -> str:
        return URLSafeTimedSerializer(secret, salt=cls.SALT).dumps({"role": "admin"})

    @classmethod
    def verify(cls, secret: str, token: str, max_age_seconds: int) -> bool:
        if not token or not secret:
            return False
        try:
            data = URLSafeTimedSerializer(secret, salt=cls.SALT).loads(token, max_age=max_age_seconds)
        except BadSignature:  # includes SignatureExpired
            return False
        return data.get("role") == "admin"


class LoginRateLimiter:
    """Allows ``max_failures`` wrong passwords per client per window (in-memory, per process)."""

    def __init__(self, max_failures: int = 10, window_seconds: int = 15 * 60) -> None:
        self.max_failures, self.window = max_failures, window_seconds
        self._failures: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        with self._lock:
            count, reset_at = self._failures.get(key, (0, 0.0))
            if reset_at > time.monotonic() and count >= self.max_failures:
                raise TooManyRequests("Too many attempts, try again later")

    def record_failure(self, key: str) -> None:
        with self._lock:
            count, reset_at = self._failures.get(key, (0, 0.0))
            if reset_at <= time.monotonic():
                count, reset_at = 0, time.monotonic() + self.window
            self._failures[key] = (count + 1, reset_at)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


class SlidingWindowLimiter:
    """Allows ``max_events`` calls per client in any ``window_seconds`` (in-memory, per process)."""

    def __init__(self, max_events: int, window_seconds: float) -> None:
        self.max_events, self.window = max_events, window_seconds
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> None:
        """Records a call; raises ``TooManyRequests`` when the client is over its allowance."""
        now = time.monotonic()
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and events[0] <= now - self.window:
                events.popleft()
            if len(events) >= self.max_events:
                raise TooManyRequests("Too many requests, please wait a moment and try again")
            events.append(now)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


login_limiter = LoginRateLimiter()
# The Shopify cart endpoint is public (called from the storefront's browser), so it is throttled per client.
shopify_limiter = SlidingWindowLimiter(max_events=20, window_seconds=60)
