# ADR-002: Bookmark API contract and timestamp semantics

- Status: Accepted
- Date: 2026-08-05
- Decision owners: Repository owner
- Affected tracks: 01, 02, 03, 04, 05
- Affected SPEC versions: Baseline
- Supersedes: None
- Superseded by: None

## Context

The assessment specifies registration and login paths, a bookmark creation example,
filter names, and an error shape, but leaves most CRUD response semantics and date
boundaries open. These choices must be explicit so implementation, OpenAPI, and
contract tests do not diverge.

## Decision

### Resources and errors

- Use `/api/auth/register` and `/api/auth/login` exactly as specified.
- Use `/api/bookmarks` for collection create/list and
  `/api/bookmarks/{bookmark_id}` for detail, partial update, and delete.
- Use PATCH for partial updates and return the updated public bookmark DTO.
- Return 204 with no body after successful deletion.
- Return 422 for request/query validation, 409 for uniqueness conflicts, 401 for
  missing or invalid authentication, and 404 for missing or other-user bookmark
  identifiers.
- Every error uses the documented `{ "error": { "code", "message", "details" } }`
  envelope. OpenAPI documents reusable success and error schemas and representative
  examples for every operation.

### Search and pagination

- `q` is a case-insensitive substring search over bookmark title only.
- `tag` is an exact match after tag normalization.
- `from` and `to` filter `created_at`; `updated_from` and `updated_to` filter
  `updated_at`.
- Date inputs use `YYYY-MM-DD` and inclusive UTC calendar-day semantics. Inclusive
  upper dates are implemented as an exclusive comparison with the next UTC
  midnight.
- Created and updated ranges combine with AND. Open-ended ranges are allowed;
  reversed ranges return 422.
- Pagination uses `page` and `page_size`, defaults to page 1 and 20 items, caps page
  size at 100, returns a total count, and orders by `created_at DESC, id DESC`.

### Bookmark and tag mutation

- Bookmark URLs accept HTTP and HTTPS. Duplicate bookmark URLs for the same user are
  allowed because the assessment does not require URL uniqueness.
- Tag input is trimmed, lowercased, empty values are rejected, and duplicates in one
  request are removed while preserving a deterministic response order.
- Tag names are globally unique as required by the assessment. Unused tag rows are
  retained; bookmark deletion removes only association rows.
- PATCH distinguishes omitted fields from explicit nulls using a dedicated update
  DTO and `model_dump(exclude_unset=True)`.
- An empty or semantically identical PATCH returns the current resource without a
  database update.

### Timestamps

- Capture one UTC instant on creation and assign it to both `created_at` and
  `updated_at`.
- `created_at` is immutable and absent from mutation DTOs.
- Every material scalar or tag-association change advances `updated_at`.
- Tag-only changes advance `updated_at` even though the relationship write occurs in
  the link table.
- Empty, identical, rejected, unauthorized, and rolled-back updates do not advance
  either timestamp.
- Timestamp tests use a controllable clock rather than wall-clock sleeps.

## Alternatives considered

| Alternative | Benefits | Costs and risks | Reason not selected |
| --- | --- | --- | --- |
| PUT and PATCH | Broader conventional API | Duplicated mutation semantics and examples | PATCH fully covers the exercise |
| 403 for another user's bookmark | Explicit authorization result | Reveals resource existence | 404 provides resource concealment |
| Datetime filter inputs | Sub-day precision | More timezone and inclusive-upper-bound ambiguity | The brief asks for date ranges |
| Automatically touching every PATCH | Simple implementation | Makes `updated_at` report requests rather than material changes | Material-change semantics are more useful and testable |

## Consequences

### Positive

- Public behavior is deterministic and contract-testable.
- Timestamp invariants cover scalar and relationship-only mutations.
- Date filters avoid end-of-day precision errors.

### Negative and risks

- The four date parameters extend the minimum assessment contract.
- Duplicate URLs can represent the same page more than once and must be explained.
- Material no-op detection adds service-layer logic.

### Follow-up

- Include request, response, query, and error examples in OpenAPI.
- Test timestamp boundaries, tag-only updates, no-op updates, and cross-user access.
- Keep creation, association replacement, timestamp mutation, and commit within one
  service-owned transaction.

## Evidence and references

- [Assessment](../../.docs/Technical%20Assessment%20Senior%20Software_Engineer.pdf)
- [SQLModel partial updates](https://sqlmodel.tiangolo.com/tutorial/fastapi/update/)
