"""Authenticated, canonical cursor values for bookmark keyset pagination."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
from datetime import UTC, datetime

from pydantic import SecretStr

from app.bookmarks.schemas import BookmarkQuery
from app.core.clock import normalize_utc
from app.core.errors import InvalidCursorError
from app.core.internal_models import FrozenInternalModel

_VERSION = 1
_DOMAIN = b"bookmarks-api.cursor-pagination.v1"
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\Z")
_B64_PATTERN = re.compile(r"[A-Za-z0-9_-]+\Z")
_PAYLOAD_KEYS = frozenset({"v", "ot", "ft", "ca", "id", "p", "ps", "iat", "exp"})


class CursorBoundary(FrozenInternalModel):
    """The last row of one descending keyset page and its next logical ordinal."""

    created_at: datetime
    bookmark_id: int
    page: int


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    if not _B64_PATTERN.fullmatch(value):
        raise ValueError("non-url-safe base64")
    decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if _b64encode(decoded) != value:
        raise ValueError("non-canonical base64")
    return decoded


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _timestamp(value: datetime) -> str:
    normalized = normalize_utc(value)
    return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("invalid timestamp")
    parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    if _timestamp(parsed) != value:
        raise ValueError("non-canonical timestamp")
    return parsed.astimezone(UTC)


def _positive_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("invalid positive integer")
    return value


def _filter_values(query: BookmarkQuery) -> dict[str, str | None]:
    """Return canonical filter material for keyed cursor binding, never for disclosure."""
    return {
        "created_from": query.created_from.isoformat() if query.created_from is not None else None,
        "created_to": query.created_to.isoformat() if query.created_to is not None else None,
        "q": query.q,
        "tag": query.tag,
        "updated_from": query.updated_from.isoformat() if query.updated_from is not None else None,
        "updated_to": query.updated_to.isoformat() if query.updated_to is not None else None,
    }


class BookmarkCursorCodec:
    """Sign and validate fixed-shape cursor payloads without external dependencies."""

    def __init__(self, *, secret: SecretStr, ttl_seconds: int) -> None:
        self._key = hmac.new(
            secret.get_secret_value().encode("utf-8"), _DOMAIN, hashlib.sha256
        ).digest()
        self._ttl_seconds = ttl_seconds

    def _tag(self, domain: bytes, value: object) -> str:
        """Return a domain-separated opaque tag from the already derived cursor key."""
        digest = hmac.new(self._key, domain + _canonical_json(value), hashlib.sha256).digest()
        return _b64encode(digest)

    def encode(
        self,
        *,
        owner_id: int,
        query: BookmarkQuery,
        boundary: CursorBoundary,
        now: datetime,
    ) -> str:
        issued_at = int(normalize_utc(now).timestamp())
        payload = {
            "ca": _timestamp(boundary.created_at),
            "exp": issued_at + self._ttl_seconds,
            "ft": self._tag(b"filter\x00", _filter_values(query)),
            "iat": issued_at,
            "id": _positive_int(boundary.bookmark_id),
            "ot": self._tag(b"owner\x00", _positive_int(owner_id)),
            "p": _positive_int(boundary.page),
            "ps": _positive_int(query.page_size),
            "v": _VERSION,
        }
        encoded = _b64encode(_canonical_json(payload))
        signature = _b64encode(
            hmac.new(self._key, encoded.encode("ascii"), hashlib.sha256).digest()
        )
        return f"{encoded}.{signature}"

    def decode(
        self,
        value: str,
        *,
        owner_id: int,
        query: BookmarkQuery,
        now: datetime,
    ) -> CursorBoundary:
        try:
            if (
                not isinstance(value, str)
                or len(value) > 2048
                or not _TOKEN_PATTERN.fullmatch(value)
            ):
                raise ValueError("invalid token shape")
            encoded, signature = value.split(".")
            expected = hmac.new(self._key, encoded.encode("ascii"), hashlib.sha256).digest()
            if not hmac.compare_digest(_b64decode(signature), expected):
                raise ValueError("signature mismatch")
            payload_bytes = _b64decode(encoded)
            payload = json.loads(payload_bytes, object_pairs_hook=_reject_duplicates)
            if not isinstance(payload, dict) or set(payload) != _PAYLOAD_KEYS:
                raise ValueError("payload shape")
            if _canonical_json(payload) != payload_bytes:
                raise ValueError("non-canonical JSON")
            if payload["v"] != _VERSION or not all(
                isinstance(payload[key], str) for key in ("ca", "ot", "ft")
            ):
                raise ValueError("payload version or strings")
            bookmark_id = _positive_int(payload["id"])
            page = _positive_int(payload["p"])
            page_size = _positive_int(payload["ps"])
            issued_at = _positive_int(payload["iat"])
            expires_at = _positive_int(payload["exp"])
            if (
                payload["ot"] != self._tag(b"owner\x00", _positive_int(owner_id))
                or payload["ft"] != self._tag(b"filter\x00", _filter_values(query))
                or page_size != query.page_size
                or expires_at != issued_at + self._ttl_seconds
            ):
                raise ValueError("binding mismatch")
            now_seconds = int(normalize_utc(now).timestamp())
            if issued_at > now_seconds or now_seconds >= expires_at:
                raise ValueError("cursor time")
            return CursorBoundary(
                created_at=_parse_timestamp(payload["ca"]),
                bookmark_id=bookmark_id,
                page=page,
            )
        except (
            TypeError,
            ValueError,
            binascii.Error,
            json.JSONDecodeError,
            UnicodeDecodeError,
            OverflowError,
        ):
            raise InvalidCursorError() from None


__all__ = ["BookmarkCursorCodec", "CursorBoundary"]
