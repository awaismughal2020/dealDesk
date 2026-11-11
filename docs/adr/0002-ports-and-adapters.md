# ADR 0002: Hexagonal architecture (ports and adapters)

Status: accepted

## Decision
`domain` (pure) ← `application` (use cases, workflow) ← `adapters` and `api`. Ports are Protocols
in `dealdesk.ports`. import-linter contracts (run in `make check`) forbid the domain from importing
frameworks, I/O libraries or outer layers, and the application from importing adapters or SDKs.

## Consequences
The model provider, database, renderer, CRM and accounting systems are swappable and testable with
fakes (the evals run with an in-memory reference-data adapter). A composition root
(`api/container.py`) wires adapters into services.
