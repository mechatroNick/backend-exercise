# ADR-006: Engineering verification and closure evidence

- Status: Accepted
- Date: 2026-08-06
- Decision owner: Repository owner
- Affected tracks: 00-08
- Affected SPEC versions: 1.1
- Supersedes: None
- Superseded by: None

## Context

The repository has a shared engineering verification guideline, but the completed
Track 00 baseline does not yet record an ADR that makes its evidence and closure
process binding across delivery tracks. Without a governing decision, later track
plans could treat planned commands, code presence, or documentation-only checks as
completion evidence.

The assessment, accepted product decisions, and any stricter track-specific rules
remain authoritative for their respective contracts. Track 00 is documentation-only;
its verifier can prove documentation integrity, but cannot prove executable behavior.

## Decision

Adopt the shared [engineering verification guideline](../../docs/ENGINEERING-VERIFICATION-GUIDELINE.md)
as the binding process for closure and evidence across Tracks 00-08. It requires
honest status and evidence receipts: an unrun, planned, blocked, or skipped command
is not a passing result.

Track 00 retains its documentation-only exception. Its closure evidence is the
read-only documentation gate and its recorded receipt; it makes no unit, API,
migration, database, structured-log, or runtime claim. Each executable track must
provide deterministic tests and a real-process Bash harness in addition to the
other checks required by its SPEC and governing ADRs.

This decision governs verification process only. It preserves the authority of the
supplied assessment, accepted ADRs, stricter track rules, and all existing product
semantics.

## Alternatives considered

| Alternative | Benefits | Costs and risks | Reason not selected |
| --- | --- | --- | --- |
| Bind the shared guideline through this ADR | One traceable closure contract with preserved stronger authorities | Requires each executable track to record real evidence | Selected |
| Leave the guideline as ungoverned documentation | No additional ADR | Closure expectations can be interpreted inconsistently | Does not provide durable governance |
| Treat code presence or planned commands as completion | Fast apparent progress | Allows unevidenced behavior to be marked complete | Contradicts honest closure evidence |
| Require runtime evidence from Track 00 | Uniform-looking receipts | Claims behavior that documentation-only artifacts cannot prove | Inapplicable to the documentation baseline |

## Consequences

### Positive

- Evidence and status language are consistent across Tracks 00-08.
- Executable tracks have both deterministic and real-process verification obligations.
- Track 00's limited documentation evidence remains explicit and honest.

### Negative and risks

- Each executable track must maintain a portable Bash harness and a complete receipt.
- A track cannot close merely because code, a test file, or a planned command exists.

### Follow-up

- Update Track 00 to SPEC version 1.1 and record the governance correction.
- Revalidate the six-ADR documentation gate and record its actual result.
- Tracks 01-08 apply this binding process when they next revise or close their own
  evidence; their product semantics are unchanged by this ADR.

## Evidence and references

- [Engineering verification guideline](../../docs/ENGINEERING-VERIFICATION-GUIDELINE.md)
- [Track 00 specification](../00-contract-baseline/SPEC.md)
- [Track 00 test report](../00-contract-baseline/TEST-REPORT.md)
