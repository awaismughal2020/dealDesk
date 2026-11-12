# ADR 0013: API contract details

Status: accepted

## Decisions
- Errors are RFC 9457 `application/problem+json` with a request id. 4xx responses are documented in
  OpenAPI under that media type (FastAPI's default is `application/json`, so the generated schema
  is post-processed), and the generated client therefore knows the error shape.
- The OpenAPI document is committed (`web/openapi.json`); a backend test fails if it drifts and a
  front-end check fails if the generated TypeScript client is stale.
- FastAPI 0.162 stores included routers as lazy `_IncludedRouter` objects rather than flattening
  them into `app.routes`. The route-protection test therefore enumerates routes from the explicit
  `ROUTERS` list and cross-checks that set against the paths in the OpenAPI document, so a route
  added elsewhere still fails the test. (An earlier version of the test silently checked zero
  routes; the cross-check now prevents that.)
- `GET /v1/auth/csrf` and `GET /v1/auth/jwks.json` are public alongside health, sign-in and refresh:
  the first is needed before sign-in, the second publishes public keys. Neither returns user data.
