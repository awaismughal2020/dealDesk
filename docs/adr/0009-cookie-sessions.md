# ADR 0009: Cookie sessions instead of browser-stored tokens

Status: accepted

## Decision
Tokens are delivered only in `HttpOnly; SameSite=Lax` cookies (`Secure` outside local; the API will
not start otherwise). The access cookie uses `Path=/` because pages need it for server-side checks;
the refresh cookie is scoped to `/v1/auth`. State-changing requests need a double-submit CSRF token
and an allowed Origin. Nothing is kept in `localStorage` or `sessionStorage` (an end-to-end test
checks this).

## Consequences
XSS cannot read tokens. The front end handles expiry with one silent refresh and a return to the
same page. CSRF protection is mandatory because cookies are ambient.
