# ADR-003: Identity normalization and token security

- Status: Accepted
- Date: 2026-08-05
- Decision owners: Repository owner
- Affected tracks: 01, 02, 05
- Affected SPEC versions: Baseline
- Supersedes: None
- Superseded by: None

## Context

The assessment requires unique usernames and email addresses, secure password
hashing, and signed expiring JWTs, but does not define normalization, password
policy, token lifetime, or refresh behavior.

## Decision

- Trim and validate email input, store one lowercase canonical email value, and use
  the same canonicalization for registration and login.
- Trim usernames, accept 3-80 ASCII letters, digits, period, underscore, and hyphen,
  store them lowercase, and enforce uniqueness on the canonical value.
- Accept passwords from 15 through 128 characters, permit spaces and Unicode, and
  avoid composition rules.
- Apply consistent Unicode NFC normalization before hashing and verification. Do
  not trim, lowercase, log, or return passwords.
- Hash passwords with Argon2 through `pwdlib`; never encrypt passwords.
- Return the same generic authentication failure for an unknown email and an invalid
  password.
- Issue access-only HS256 JWTs containing a stable user subject and expiry. Default
  lifetime is 30 minutes and configurable in Settings.
- Load the JWT secret from environment-backed Settings. The application has no
  usable production secret default; tests provide an isolated secret.
- Never expose or log password hashes, passwords, JWTs, authorization headers, or
  secret-bearing configuration.

## Alternatives considered

| Alternative | Benefits | Costs and risks | Reason not selected |
| --- | --- | --- | --- |
| Preserve username display casing with a second canonical column | Richer display identity | Extra column and synchronization rules | Unnecessary for this API |
| Password composition rules | Familiar policy | Poor usability and weak security signal compared with length | Length-focused policy selected |
| Refresh tokens | Longer sessions | Rotation, revocation, storage, and more endpoints | Outside the assessment |
| Asymmetric JWT signing | Strong service-boundary properties | Key management adds no value to one local issuer/verifier | HS256 is proportionate here |

## Consequences

### Positive

- Identity uniqueness has one deterministic representation.
- Public DTO separation prevents credential fields from leaking.
- Authentication remains small enough to explain and test completely.

### Negative and risks

- Lowercase-only public usernames are a deliberate product constraint.
- Access tokens cannot be individually revoked before expiry.

### Follow-up

- Test duplicate identities with case variations.
- Test missing, malformed, tampered, expired, and valid JWTs.
- Ensure error details and logs never distinguish unknown accounts from bad
  passwords.

## Evidence and references

- [Assessment](../../.docs/Technical%20Assessment%20Senior%20Software_Engineer.pdf)
- [FastAPI JWT and password hashing guidance](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)
- [NIST password guidance](https://pages.nist.gov/800-63-4/sp800-63b.html)
