"""Deterministic unit evidence for the bounded local token-bucket policy."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from math import inf, nan

import pytest
from pydantic import ValidationError

from app.api.rate_limit import RateLimitDecision, RateLimiter, TokenBucket, _BucketEntry


class FakeMonotonic:
    """A test-controlled monotonic source that can also model hostile clock output."""

    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def _bucket(clock: FakeMonotonic, **kwargs: int) -> TokenBucket:
    return TokenBucket(
        capacity=kwargs.get("capacity", 2),
        window_seconds=kwargs.get("window_seconds", 10),
        max_keys=kwargs.get("max_keys", 3),
        idle_ttl_seconds=kwargs.get("idle_ttl_seconds", 10),
        monotonic=clock,
    )


def test_rate_models_preserve_frozen_decisions_and_mutable_bucket_state() -> None:
    decision = RateLimitDecision(allowed=True)

    assert decision == RateLimitDecision(allowed=True)
    assert hash(decision) == hash(RateLimitDecision(allowed=True))
    with pytest.raises(ValidationError):
        decision.allowed = False
    with pytest.raises(ValidationError):
        RateLimitDecision(allowed=1)

    entry = _BucketEntry(tokens=1.0, refilled_at=2.0, last_seen=2.0)
    entry.tokens -= 0.25
    assert entry.tokens == 0.75
    with pytest.raises(ValidationError):
        entry.tokens = "0.5"  # type: ignore[assignment]
    assert entry.tokens == 0.75


def test_bucket_consumes_capacity_refills_and_rounds_positive_retry_after() -> None:
    clock = FakeMonotonic()
    bucket = _bucket(clock, capacity=3, window_seconds=6)

    assert [bucket.consume("peer").allowed for _ in range(3)] == [True, True, True]
    assert bucket.consume("peer").retry_after == 2
    clock.value = 1.9
    assert bucket.consume("peer").retry_after == 1
    clock.value = 2.0
    assert bucket.consume("peer").allowed is True


def test_backward_monotonic_time_is_an_unexpected_fail_closed_state() -> None:
    clock = FakeMonotonic(10.0)
    bucket = _bucket(clock, capacity=1, window_seconds=10, max_keys=1, idle_ttl_seconds=10)

    assert bucket.consume("a").allowed is True
    clock.value = 5.0
    with pytest.raises(RuntimeError, match="moved backwards"):
        bucket.consume("a")
    clock.value = 20.0
    assert bucket.consume("a").allowed is True


@pytest.mark.parametrize("invalid_now", [nan, inf, -inf])
def test_nonfinite_clock_values_are_unexpected_fail_closed_state_without_poisoning_future_requests(
    invalid_now: float,
) -> None:
    clock = FakeMonotonic(invalid_now)
    bucket = _bucket(clock, capacity=1, window_seconds=10)

    with pytest.raises(RuntimeError, match="nonfinite"):
        bucket.consume("peer")
    clock.value = 0.0
    assert bucket.consume("peer").allowed is True


def test_bucket_is_thread_safe_at_the_capacity_boundary() -> None:
    clock = FakeMonotonic()
    bucket = _bucket(clock, capacity=10, window_seconds=60, idle_ttl_seconds=60)

    with ThreadPoolExecutor(max_workers=16) as executor:
        decisions = list(executor.map(lambda _: bucket.consume("shared").allowed, range(64)))

    assert decisions.count(True) == 10
    assert decisions.count(False) == 54


def test_idle_entries_are_evicted_before_an_unseen_key_is_admitted() -> None:
    clock = FakeMonotonic()
    bucket = _bucket(clock, capacity=1, window_seconds=10, max_keys=1, idle_ttl_seconds=10)

    assert bucket.consume("old").allowed is True
    clock.value = 10.0
    assert bucket.consume("new").allowed is True
    assert bucket.consume("old").allowed is False


def test_active_saturation_fails_closed_for_unseen_keys_but_keeps_known_keys() -> None:
    clock = FakeMonotonic()
    bucket = _bucket(clock, capacity=2, window_seconds=10, max_keys=1, idle_ttl_seconds=10)

    assert bucket.consume("known").allowed is True
    assert bucket.consume("unseen").allowed is False
    assert bucket.consume("known").allowed is True
    assert bucket.consume("unseen").retry_after == 5


def test_a_new_limiter_instance_resets_local_process_state() -> None:
    clock = FakeMonotonic()
    first = _bucket(clock, capacity=1)
    assert first.consume("peer").allowed is True
    assert first.consume("peer").allowed is False

    restarted = _bucket(clock, capacity=1)
    assert restarted.consume("peer").allowed is True


def test_separate_auth_and_bookmark_buckets_are_shared_only_within_their_policy() -> None:
    clock = FakeMonotonic()
    limiter = RateLimiter(
        enabled=True,
        auth_requests=1,
        auth_window_seconds=10,
        bookmark_requests=1,
        bookmark_window_seconds=10,
        max_keys=2,
        idle_ttl_seconds=10,
        monotonic=clock,
    )

    assert limiter.consume_auth("127.0.0.1").allowed is True
    assert limiter.consume_auth("127.0.0.1").allowed is False
    assert limiter.consume_bookmark(7).allowed is True
    assert limiter.consume_bookmark(8).allowed is True
    assert limiter.consume_bookmark(7).allowed is False


def test_rate_limiter_hmacs_domain_separated_identity_keys_before_bucket_storage() -> None:
    clock = FakeMonotonic()
    key = b"deterministic-rate-limit-key"
    limiter = RateLimiter(
        enabled=True,
        auth_requests=1,
        auth_window_seconds=10,
        bookmark_requests=1,
        bookmark_window_seconds=10,
        max_keys=2,
        idle_ttl_seconds=10,
        monotonic=clock,
        identity_key=key,
    )
    same_key_limiter = RateLimiter(
        enabled=True,
        auth_requests=1,
        auth_window_seconds=10,
        bookmark_requests=1,
        bookmark_window_seconds=10,
        max_keys=2,
        idle_ttl_seconds=10,
        monotonic=clock,
        identity_key=key,
    )
    peer = "198.51.100.27"

    assert limiter.consume_auth(peer).allowed is True
    assert limiter.consume_bookmark(27).allowed is True
    stored = set(limiter._auth._entries) | set(limiter._bookmarks._entries)
    assert stored and all(len(value) == 64 for value in stored)
    assert peer not in stored and "27" not in stored
    assert limiter._opaque_key("auth", peer) == same_key_limiter._opaque_key("auth", peer)
    assert limiter._opaque_key("auth", peer) != limiter._opaque_key("bookmark", peer)


def test_rejection_events_are_once_per_opaque_key_policy_and_window() -> None:
    clock = FakeMonotonic()
    limiter = RateLimiter(
        enabled=True,
        auth_requests=1,
        auth_window_seconds=10,
        bookmark_requests=1,
        bookmark_window_seconds=10,
        max_keys=3,
        idle_ttl_seconds=10,
        monotonic=clock,
        identity_key=b"deterministic-rate-limit-key",
    )

    assert limiter.consume_auth("peer-a").allowed is True
    first = limiter.consume_auth("peer-a")
    repeated = limiter.consume_auth("peer-a")
    assert first.emit_rejection_event is True and first.capacity_exhausted is False
    assert repeated.emit_rejection_event is False and repeated.capacity_exhausted is False
    clock.value = 10.0
    assert limiter.consume_auth("peer-a").allowed is True
    next_window = limiter.consume_auth("peer-a")
    assert next_window.emit_rejection_event is True


def test_rejection_event_state_is_isolated_by_policy_and_opaque_key() -> None:
    clock = FakeMonotonic()
    limiter = RateLimiter(
        enabled=True,
        auth_requests=1,
        auth_window_seconds=10,
        bookmark_requests=1,
        bookmark_window_seconds=10,
        max_keys=3,
        idle_ttl_seconds=10,
        monotonic=clock,
        identity_key=b"deterministic-rate-limit-key",
    )

    assert limiter.consume_auth("peer-a").allowed is True
    assert limiter.consume_auth("peer-a").emit_rejection_event is True
    assert limiter.consume_auth("peer-b").allowed is True
    assert limiter.consume_auth("peer-b").emit_rejection_event is True
    assert limiter.consume_bookmark(1).allowed is True
    assert limiter.consume_bookmark(1).emit_rejection_event is True


def test_capacity_saturation_events_are_global_once_per_policy_window() -> None:
    clock = FakeMonotonic()
    limiter = RateLimiter(
        enabled=True,
        auth_requests=1,
        auth_window_seconds=10,
        bookmark_requests=1,
        bookmark_window_seconds=10,
        max_keys=1,
        idle_ttl_seconds=10,
        monotonic=clock,
        identity_key=b"deterministic-rate-limit-key",
    )

    assert limiter.consume_auth("active").allowed is True
    first = limiter.consume_auth("unseen-one")
    repeated = limiter.consume_auth("unseen-two")
    assert first.capacity_exhausted is True and first.emit_rejection_event is True
    assert repeated.capacity_exhausted is True and repeated.emit_rejection_event is False
    clock.value = 10.0
    assert limiter.consume_auth("active").allowed is True
    next_window = limiter.consume_auth("unseen-three")
    assert next_window.capacity_exhausted is True and next_window.emit_rejection_event is True


def test_disabled_limiter_bypasses_policy_without_creating_a_test_only_special_case() -> None:
    limiter = RateLimiter(
        enabled=False,
        auth_requests=1,
        auth_window_seconds=10,
        bookmark_requests=1,
        bookmark_window_seconds=10,
        max_keys=1,
        idle_ttl_seconds=10,
        monotonic=FakeMonotonic(),
    )

    assert all(limiter.consume_auth("peer").allowed for _ in range(3))
    assert all(limiter.consume_bookmark(1).allowed for _ in range(3))


def test_rate_limiter_rejects_an_empty_injected_identity_key() -> None:
    with pytest.raises(ValueError, match="identity_key"):
        RateLimiter(
            enabled=True,
            auth_requests=1,
            auth_window_seconds=10,
            bookmark_requests=1,
            bookmark_window_seconds=10,
            max_keys=1,
            idle_ttl_seconds=10,
            identity_key=b"",
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"capacity": 0}, "capacity"),
        ({"window_seconds": 0}, "window_seconds"),
        ({"max_keys": 0}, "max_keys"),
        ({"idle_ttl_seconds": 9}, "idle_ttl_seconds"),
    ],
)
def test_bucket_constructor_rejects_invalid_local_policy_values(
    kwargs: dict[str, int], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _bucket(FakeMonotonic(), **kwargs)
