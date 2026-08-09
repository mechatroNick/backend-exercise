# ADR-008: Pydantic internal models and typed lifecycle events

- Status: Accepted
- Date: 2026-08-09
- Owners: Primary engineering thread
- Scope: Track 09 internal representation and observability source contract

## Context

The delivered service uses standard-library dataclasses for internal value objects,
validated domain events, worker state, mutable rate buckets, seed results, and a test
query-plan helper. Public request/response DTOs already use Pydantic v2. Track 09 must
replace all dataclasses with Pydantic and represent application lifecycle event names
as enum values without changing public or operational behavior.

Pydantic `BaseModel` is keyword-only, validates on construction, is mutable by
default, and can coerce inputs unless configured otherwise. A blind decorator swap
would therefore change positional construction, exception types, strictness,
immutability, equality/hash behavior, and mutable bucket updates. Some existing
classes also enforce cross-field invariants that must remain explicit.

## Decision

Use Pydantic v2 `BaseModel` for every current dataclass, including the test helper.
Each model declares its actual contract rather than relying on defaults:

- immutable internal values use `ConfigDict(frozen=True, strict=True,
  extra="forbid")` unless a documented field needs a narrower compatible rule;
- deliberately mutable internal state, including rate buckets, uses explicit mutable
  configuration and remains protected by its existing synchronization boundary;
- cross-field event/current-stats invariants use field/model validators with the same
  accepted/rejected semantic set and safe error handling;
- construction becomes explicit keyword construction; no public response model or
  OpenAPI schema is substituted merely to reuse an internal model;
- code never starts serializing an internal model into logs or tokens accidentally;
  existing canonical cursor/event/log payload construction remains authoritative;
- tests assert semantic immutability, validation, equality/hash/state behavior, and
  error safety rather than standard-library dataclass implementation details.

Define `ApplicationLifecycleEvent` as a `StrEnum` containing exactly the five
`application.*` lifecycle values. Use enum members at the application lifecycle log
call sites. Keep the generic logging boundary accepting extensible string values so
component, framework, safe fallback, and future events are not forced into one closed
global registry. Because `StrEnum` members are strings, emitted JSON values remain
byte-for-byte compatible.

## Consequences

Internal construction receives explicit validation and consistent Pydantic v2 model
introspection. Model creation may cost slightly more, which is acceptable for this
assessment but must not add per-request unbounded work or change the O(1) bounded rate
state behavior. Assignment to frozen models raises Pydantic validation errors rather
than `FrozenInstanceError`; this is internal/test-only and public boundaries remain
unchanged.

The conversion must be reviewed by semantic group, with focused concurrency,
invariant, serialization, cursor compatibility, stats fallback, seed, readiness, and
logging tests before the full suite. No database migration is required.

## Rejected alternatives

- `pydantic.dataclasses.dataclass`: still a dataclass and does not fulfill the owner
  request to replace dataclass use.
- One shared frozen base for all models: breaks deliberately mutable rate/worker state.
- Pydantic defaults without strict/extra configuration: permits coercion or ignored
  input that can weaken internal invariants.
- A closed enum for every log event: unnecessarily constrains the generic logging
  framework and expands a lifecycle-specific requirement.
- Keeping dataclasses only for private/test objects: contradicts the comprehensive
  replacement requirement and leaves two model systems for the same internal role.

## Verification

Source inventory must find no `dataclasses` import or `@dataclass` decorator in app or
tests. Focused model tests cover immutable assignment, mutable bucket updates under
concurrency, extra/coercive/invalid values, event UUID/time invariants, stats
source/timestamp invariants, cursor round-trip and legacy token compatibility, seed
summary/log safety, and query-plan helper equality. Full type, warning, coverage,
OpenAPI/runtime, Track 01–06/08, and Docker gates must remain green.

