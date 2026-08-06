"""Canonical, transport-independent identity validation helpers."""

from __future__ import annotations

import re

from email_validator import EmailNotValidError, validate_email

from app.core.errors import ValidationApplicationError

_USERNAME_PATTERN = re.compile(r"^[a-z0-9._-]{3,80}$")


def _require_string(value: object) -> str:
    if not isinstance(value, str):
        raise ValidationApplicationError() from None
    return value


def canonicalize_email(value: object) -> str:
    """Trim, lowercase, and syntax-check an email without accepting display forms."""
    canonical = _require_string(value).strip().lower()
    if not canonical:
        raise ValidationApplicationError() from None
    try:
        normalized = validate_email(canonical, check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        raise ValidationApplicationError() from None
    return normalized


def canonicalize_username(value: object) -> str:
    """Trim, lowercase, and enforce the fixed ASCII username policy."""
    canonical = _require_string(value).strip().lower()
    if _USERNAME_PATTERN.fullmatch(canonical) is None:
        raise ValidationApplicationError() from None
    return canonical


__all__ = ["canonicalize_email", "canonicalize_username"]
