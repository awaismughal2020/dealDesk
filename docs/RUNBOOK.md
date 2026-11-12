# Runbook

Everything runs through Docker and Make. Ports are bound to 127.0.0.1 only.

## Start, stop, reset

| Task | Command |
| --- | --- |
| First run (secrets, build, migrate, seed) | `make demo` |
| Start or rebuild | `make up` (waits until db, api and web are healthy) |
| Stop (keep data) | `make down` |
| Follow logs | `make logs` |
| Re-run migrations and seed (idempotent) | `make seed` |
| Reset everything (deletes the database volume; keeps `.env` and keys) | `make clean && make demo` |
| Start from scratch including secrets | `make clean`, delete `.env` and `secrets/`, then `make demo` |

URLs: UI <http://localhost:3000>, API docs <http://localhost:8000/docs> (local only; disabled
outside `APP_ENV=local`). Demo credentials: the `DEMO_*` entries in `.env`.

## Health

- `GET /healthz` (API and web): process is up.
- `GET /readyz` (API): the database answers; returns 503 otherwise.
- `docker compose ps` shows health for db, api and web.

## Troubleshooting

| Symptom | Likely cause and fix |
| --- | --- |
| `POSTGRES_PASSWORD ... run make init` from Compose | `.env` is missing secrets. Run `make init` (idempotent). |
| API exits with `KeyConfigurationError` | No signing key in `secrets/jwt/`. Run `make init`. |
| API exits with a settings validation error | A value in `.env` is invalid (for example `COOKIE_SECURE=false` with `APP_ENV` other than `local`, or a real provider without its credentials). The message names the setting. |
| Sign-in always fails | Check the email and password in `.env`; after 5 failures the account is locked for 15 minutes (doubling after that). `make seed` resets demo passwords to the `.env` values. |
| 403 "CSRF check failed" | The page is served from an origin not in `ALLOWED_ORIGINS`, or cookies were cleared. Use <http://localhost:3000> and reload. |
| 429 Too many requests | Rate limit hit; wait for `Retry-After` seconds. |
| A run shows "failed" | The run detail page shows the error; details are in `make logs` under the request id. Start a new run. |
| A run is stuck in "running" after a crash | Restart the API (`make up`); interrupted runs resume from their checkpoint on start-up. |
| `make e2e` fails on sign-in | Demo users must exist: `make seed`. |

Every response carries `X-Request-ID`; quote it when reading logs. Logs never contain brief text.

## Rotate signing keys

```bash
make rotate-keys   # writes a new Ed25519 key, marks it active, keeps the previous one
make up            # the API loads both: new tokens use the new key, old ones still verify
```

Both public keys are published at `/v1/auth/jwks.json`. After the access-token lifetime (15 minutes)
the previous key is no longer needed; the next rotation removes it.

## Switch provider or auth mode

Edit `.env` and run `make up`. See the README for provider settings. For OIDC set `AUTH_MODE=oidc`
and the `OIDC_*` variables (issuer, audience, JWKS URL, client id, authorize and token URLs, role
claim). Local sign-in is then disabled and users are provisioned from the identity provider.

## Evals

- `make eval`: offline replay of recorded fixtures (fails if a prompt changed without re-recording).
- `make eval-record`: re-record fixtures after changing a prompt.
- `make eval-live`: run against the configured provider (sends the SAMPLE briefs to it).
