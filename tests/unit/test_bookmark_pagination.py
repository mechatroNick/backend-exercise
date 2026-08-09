"""Deterministic hostile-input evidence for authenticated bookmark cursors."""

from __future__ import annotations

import hashlib
import hmac
import json
from base64 import urlsafe_b64decode
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr

from app.bookmarks.pagination import (
    BookmarkCursorCodec,
    CursorBoundary,
    _b64decode,
    _b64encode,
    _parse_timestamp,
)
from app.bookmarks.schemas import BookmarkQuery
from app.core.errors import InvalidCursorError

_NOW = datetime(2026, 8, 9, 3, 0, tzinfo=UTC)
_QUERY = BookmarkQuery(tag="python", q="fictional", page_size=2)


def _codec() -> BookmarkCursorCodec:
    return BookmarkCursorCodec(secret=SecretStr("cursor-test-secret"), ttl_seconds=900)


def _token(codec: BookmarkCursorCodec, payload: object) -> str:
    encoded = _b64encode(json.dumps(payload, separators=(",", ":")).encode("ascii"))
    signature = _b64encode(hmac.new(codec._key, encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def _valid_token(codec: BookmarkCursorCodec) -> str:
    return codec.encode(
        owner_id=7,
        query=_QUERY,
        boundary=CursorBoundary(created_at=_NOW - timedelta(seconds=1), bookmark_id=12, page=2),
        now=_NOW,
    )


def test_cursor_round_trip_is_canonical_and_expires_at_the_exact_second() -> None:
    codec = _codec()
    token = _valid_token(codec)

    assert token == _valid_token(codec)
    assert codec.decode(token, owner_id=7, query=_QUERY, now=_NOW) == CursorBoundary(
        created_at=_NOW - timedelta(seconds=1), bookmark_id=12, page=2
    )
    assert codec.decode(token, owner_id=7, query=_QUERY, now=_NOW + timedelta(seconds=899))
    with pytest.raises(InvalidCursorError):
        codec.decode(token, owner_id=7, query=_QUERY, now=_NOW + timedelta(seconds=900))


@pytest.mark.parametrize(
    "value",
    [
        "",
        "not-a-token",
        ".",
        "a.b.c",
        "a=.b",
        "a.@@@",
        "a" * 2049,
    ],
)
def test_malformed_or_oversized_cursor_is_one_fixed_error(value: str) -> None:
    with pytest.raises(InvalidCursorError) as raised:
        _codec().decode(value, owner_id=7, query=_QUERY, now=_NOW)
    assert raised.value.code == "invalid_cursor"
    assert raised.value.message == "Cursor is invalid or expired."


def test_signed_noncanonical_duplicate_and_payload_shape_tokens_are_rejected() -> None:
    codec = _codec()
    valid = _valid_token(codec)
    encoded, _signature = valid.split(".")
    canonical = json.loads(urlsafe_b64decode(encoded + "=="))
    cases: tuple[object, ...] = (
        {**canonical, "extra": 1},
        {key: value for key, value in canonical.items() if key != "exp"},
        {**canonical, "v": 2},
        {**canonical, "ft": 1},
        {**canonical, "id": True},
        {**canonical, "ca": "2026-08-09T03:00:00Z"},
    )
    duplicate_payload = (
        b'{"ca":"2026-08-09T02:59:59.000000Z","ca":"2026-08-09T02:59:59.000000Z",'
        + json.dumps(
            {key: value for key, value in canonical.items() if key != "ca"},
            separators=(",", ":"),
        ).encode("ascii")[1:]
    )
    for payload in cases:
        with pytest.raises(InvalidCursorError):
            _codec().decode(_token(codec, payload), owner_id=7, query=_QUERY, now=_NOW)
    duplicate_encoded = _b64encode(duplicate_payload)
    duplicate_signature = _b64encode(
        hmac.new(codec._key, duplicate_encoded.encode("ascii"), hashlib.sha256).digest()
    )
    with pytest.raises(InvalidCursorError):
        codec.decode(
            f"{duplicate_encoded}.{duplicate_signature}", owner_id=7, query=_QUERY, now=_NOW
        )


@pytest.mark.parametrize(
    ("owner_id", "query", "now"),
    [
        (8, _QUERY, _NOW),
        (7, BookmarkQuery(tag="rust", q="fictional", page_size=2), _NOW),
        (7, BookmarkQuery(tag="python", q="fictional", page_size=3), _NOW),
        (7, _QUERY, _NOW - timedelta(seconds=1)),
    ],
)
def test_cursor_is_bound_to_owner_filter_page_size_and_time(
    owner_id: int, query: BookmarkQuery, now: datetime
) -> None:
    with pytest.raises(InvalidCursorError):
        _codec().decode(_valid_token(_codec()), owner_id=owner_id, query=query, now=now)


def test_cursor_tampering_never_reveals_a_distinguishing_error() -> None:
    codec = _codec()
    token = _valid_token(codec)
    altered = token[:-1] + ("A" if token[-1] != "A" else "B")

    with pytest.raises(InvalidCursorError) as raised:
        codec.decode(altered, owner_id=7, query=_QUERY, now=_NOW)
    assert str(raised.value) == "Cursor is invalid or expired."


def test_private_decoders_reject_non_url_safe_noncanonical_and_non_utc_values() -> None:
    for value in ("@", "A"):
        with pytest.raises(ValueError):
            _b64decode(value)
    with pytest.raises(ValueError):
        _parse_timestamp("2026-08-09T03:00:00+00:00")


def test_private_base64_decoder_defends_its_reencoding_invariant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.bookmarks.pagination as pagination

    monkeypatch.setattr(pagination, "_b64encode", lambda _value: "different")
    with pytest.raises(ValueError):
        pagination._b64decode("AA")


def test_signed_but_noncanonical_json_is_rejected_before_payload_interpretation() -> None:
    codec = _codec()
    valid = _valid_token(codec)
    encoded, _signature = valid.split(".")
    canonical = json.loads(urlsafe_b64decode(encoded + "=="))
    unordered = {key: canonical[key] for key in reversed(tuple(canonical))}

    with pytest.raises(InvalidCursorError):
        codec.decode(_token(codec, unordered), owner_id=7, query=_QUERY, now=_NOW)


def test_payload_contains_only_opaque_owner_and_filter_tags() -> None:
    first_codec = _codec()
    second_codec = BookmarkCursorCodec(secret=SecretStr("different-cursor-secret"), ttl_seconds=900)
    first = json.loads(urlsafe_b64decode(_valid_token(first_codec).split(".")[0] + "=="))
    second = json.loads(urlsafe_b64decode(_valid_token(second_codec).split(".")[0] + "=="))
    other_owner = json.loads(
        urlsafe_b64decode(
            first_codec.encode(
                owner_id=8,
                query=_QUERY,
                boundary=CursorBoundary(
                    created_at=_NOW - timedelta(seconds=1), bookmark_id=12, page=2
                ),
                now=_NOW,
            ).split(".")[0]
            + "=="
        )
    )
    other_filter = json.loads(
        urlsafe_b64decode(
            first_codec.encode(
                owner_id=7,
                query=BookmarkQuery(tag="rust", q="fictional", page_size=2),
                boundary=CursorBoundary(
                    created_at=_NOW - timedelta(seconds=1), bookmark_id=12, page=2
                ),
                now=_NOW,
            ).split(".")[0]
            + "=="
        )
    )

    assert set(first) == {"v", "ot", "ft", "ca", "id", "p", "ps", "iat", "exp"}
    assert "o" not in first and "f" not in first
    assert 7 not in first.values() and "python" not in str(first) and "fictional" not in str(first)
    assert first["ot"] != other_owner["ot"]
    assert first["ft"] != other_filter["ft"]
    assert first["ot"] != second["ot"] and first["ft"] != second["ft"]
