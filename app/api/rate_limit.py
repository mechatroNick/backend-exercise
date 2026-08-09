"""Local, bounded token-bucket rate limiting for selected public API operations."""

from __future__ import annotations

import hashlib
import hmac
import math
import secrets
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """The deterministic outcome of consuming one request token."""

    allowed: bool
    retry_after: int | None = None
    emit_rejection_event: bool = False
    capacity_exhausted: bool = False


@dataclass(slots=True)
class _BucketEntry:
    """Mutable internal state for one bounded bucket key."""

    tokens: float
    refilled_at: float
    last_seen: float
    last_rejection_event_at: float | None = None


class TokenBucket:
    """A thread-safe, bounded, monotonic token bucket with injectable time."""

    def __init__(
        self,
        *,
        capacity: int,
        window_seconds: int,
        max_keys: int,
        idle_ttl_seconds: int,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        if window_seconds < 1:
            raise ValueError("window_seconds must be positive")
        if max_keys < 1:
            raise ValueError("max_keys must be positive")
        if idle_ttl_seconds < window_seconds:
            raise ValueError("idle_ttl_seconds must cover the rate-limit window")
        self._capacity = capacity
        self._window_seconds = window_seconds
        self._max_keys = max_keys
        self._idle_ttl_seconds = idle_ttl_seconds
        self._monotonic = monotonic
        self._refill_rate = capacity / window_seconds
        self._entries: OrderedDict[str, _BucketEntry] = OrderedDict()
        self._lock = RLock()
        self._last_observed_at: float | None = None
        self._last_capacity_rejection_event_at: float | None = None

    def consume(self, key: str) -> RateLimitDecision:
        """Consume one token or fail closed with a positive integer retry delay."""
        with self._lock:
            now = self._monotonic()
            if not math.isfinite(now):
                raise RuntimeError("rate limiter monotonic clock is nonfinite")
            if self._last_observed_at is not None and now < self._last_observed_at:
                raise RuntimeError("rate limiter monotonic clock moved backwards")
            self._last_observed_at = now
            self._evict_idle_entries(now)
            entry = self._entries.get(key)
            if entry is None:
                if len(self._entries) >= self._max_keys:
                    return RateLimitDecision(
                        allowed=False,
                        retry_after=self._minimum_retry_after(),
                        emit_rejection_event=self._capacity_rejection_event_due(now),
                        capacity_exhausted=True,
                    )
                entry = _BucketEntry(
                    tokens=float(self._capacity),
                    refilled_at=now,
                    last_seen=now,
                )
                self._entries[key] = entry
            else:
                self._refill(entry, now)
                entry.last_seen = now
                self._entries.move_to_end(key)

            if entry.tokens >= 1:
                entry.tokens -= 1
                return RateLimitDecision(allowed=True)
            return RateLimitDecision(
                allowed=False,
                retry_after=self._retry_after(entry.tokens),
                emit_rejection_event=self._entry_rejection_event_due(entry, now),
            )

    def _evict_idle_entries(self, now: float) -> None:
        """Remove idle opaque-key entries in least-recently-used order."""
        for key, entry in tuple(self._entries.items()):
            if now >= entry.last_seen and now - entry.last_seen >= self._idle_ttl_seconds:
                del self._entries[key]

    def _refill(self, entry: _BucketEntry, now: float) -> None:
        """Refill from a non-decreasing monotonic point and clamp to capacity."""
        if now <= entry.refilled_at:
            return
        entry.tokens = min(
            float(self._capacity),
            entry.tokens + (now - entry.refilled_at) * self._refill_rate,
        )
        entry.refilled_at = now

    def _minimum_retry_after(self) -> int:
        return max(1, math.ceil(1 / self._refill_rate))

    def _retry_after(self, tokens: float) -> int:
        return max(1, math.ceil((1 - tokens) / self._refill_rate))

    def _entry_rejection_event_due(self, entry: _BucketEntry, now: float) -> bool:
        """Allow at most one ordinary rejection event per opaque key/window."""
        if (
            entry.last_rejection_event_at is not None
            and now - entry.last_rejection_event_at < self._window_seconds
        ):
            return False
        entry.last_rejection_event_at = now
        return True

    def _capacity_rejection_event_due(self, now: float) -> bool:
        """Allow at most one saturation event per local policy/window."""
        if (
            self._last_capacity_rejection_event_at is not None
            and now - self._last_capacity_rejection_event_at < self._window_seconds
        ):
            return False
        self._last_capacity_rejection_event_at = now
        return True


class RateLimiter:
    """Separate shared buckets for public authentication and verified bookmark traffic."""

    def __init__(
        self,
        *,
        enabled: bool,
        auth_requests: int,
        auth_window_seconds: int,
        bookmark_requests: int,
        bookmark_window_seconds: int,
        max_keys: int,
        idle_ttl_seconds: int,
        monotonic: Callable[[], float] = time.monotonic,
        identity_key: bytes | None = None,
    ) -> None:
        self.enabled = enabled
        if identity_key is not None and not identity_key:
            raise ValueError("identity_key must not be empty")
        self._identity_key = (
            bytes(identity_key) if identity_key is not None else secrets.token_bytes(32)
        )
        self._auth = TokenBucket(
            capacity=auth_requests,
            window_seconds=auth_window_seconds,
            max_keys=max_keys,
            idle_ttl_seconds=idle_ttl_seconds,
            monotonic=monotonic,
        )
        self._bookmarks = TokenBucket(
            capacity=bookmark_requests,
            window_seconds=bookmark_window_seconds,
            max_keys=max_keys,
            idle_ttl_seconds=idle_ttl_seconds,
            monotonic=monotonic,
        )

    def consume_auth(self, peer_ip: str) -> RateLimitDecision:
        """Consume from the shared socket-peer authentication policy bucket."""
        return (
            RateLimitDecision(allowed=True)
            if not self.enabled
            else self._auth.consume(self._opaque_key("auth", peer_ip))
        )

    def consume_bookmark(self, user_id: int) -> RateLimitDecision:
        """Consume from the shared already-authenticated-user policy bucket."""
        return (
            RateLimitDecision(allowed=True)
            if not self.enabled
            else self._bookmarks.consume(self._opaque_key("bookmark", str(user_id)))
        )

    def _opaque_key(self, policy: str, identity: str) -> str:
        """Derive a process-local domain-separated opaque bucket key without retaining identity."""
        message = policy.encode("ascii") + b"\x00" + identity.encode("utf-8")
        return hmac.new(self._identity_key, message, hashlib.sha256).hexdigest()


__all__ = ["RateLimitDecision", "RateLimiter", "TokenBucket"]
