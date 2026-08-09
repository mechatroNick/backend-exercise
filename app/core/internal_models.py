"""Explicit Pydantic bases for private application value objects.

These models are intentionally not transport schemas.  They retain the value,
immutability, and strict-construction contracts previously expressed with
standard-library dataclasses without becoming a serialization boundary.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FrozenInternalModel(BaseModel):
    """A strict, immutable private value object with no ignored input."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class MutableInternalModel(BaseModel):
    """A strict mutable private state record with validated assignments."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


__all__ = ["FrozenInternalModel", "MutableInternalModel"]
