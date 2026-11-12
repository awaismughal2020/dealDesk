# ADR 0008: Local authentication by default, OIDC mode for a real identity provider

Status: accepted

## Decision
Local mode (default, offline): Argon2id passwords with a NIST-style policy, EdDSA access tokens
(15 minutes, kid header, strict claim and algorithm checks), rotating refresh tokens stored as
hashes with family revocation on reuse, lockout and rate limits. OIDC mode: the API validates the
provider's tokens via a cached JWKS (issuer, audience, expiry with skew, algorithm allowlist) and
maps a configured claim to roles; the front end runs Authorization Code with PKCE in server routes.
Both implement one `AuthPort`. The database role is authoritative in local mode; the IdP's in OIDC
mode.

## Consequences
The demo needs no external services; production can plug in an IdP by configuration. The optional
Keycloak Compose profile was cut (OIDC is tested with a mocked JWKS instead).
