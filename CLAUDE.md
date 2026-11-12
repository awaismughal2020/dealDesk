# CLAUDE.md

Project: Deal Desk MVP. The full specification is in docs/SPEC.md.

## Always
- Money and dates are computed in deterministic Python with Decimal. The LLM never does arithmetic.
- Domain code (`src/dealdesk/domain`) is pure: no I/O, no frameworks, no float.
- Treat uploaded briefs as untrusted input (prompt-injection safe; validate all model output with Pydantic).
- All data is synthetic and labelled SAMPLE. Do not invent facts about real companies.
- Default LLM provider is `fake` (offline). Never commit secrets or `.env`.
- Run everything through Docker via `make`: `make check` (lint, types, tests, coverage), `make eval`, `make demo`.
- One conventional commit per milestone. Never skip or weaken a failing test.
- Never run `terraform apply`, never push, never use cloud credentials.
- Authentication and authorisation are enforced on the server for every route (deny by default). Tokens live only in HttpOnly cookies. No credentials in the repo. An approver cannot approve a run they created.
- Front end is Next.js with TypeScript strict and a generated API client; no business logic or money maths in the browser.
- Verify library names and APIs against current docs before using them; pin versions.
