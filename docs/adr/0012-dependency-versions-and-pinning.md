# ADR 0012: Dependency versions and pinning

Status: accepted (2026-11-11)

## Context
The spec asks for verified, pinned versions. Several packages had releases less than 48 hours old
when the project started, and some of the newest majors are not yet compatible with each other.

## Decision
- Python: `uv.lock` is the source of truth. `[tool.uv] exclude-newer` is set a few days before the
  start date so a fresh lock never picks up a package published hours ago (supply-chain hygiene and
  reproducibility). Version ranges in `pyproject.toml` are major-series bounds; exact versions live
  in the lock.
- Node: exact versions in `package.json`, `package-lock.json` committed, `npm ci` everywhere.
- Node runtime is **26 LTS** ("Lithium", 26.13.0), verified against nodejs.org's release index.
- **TypeScript 5.9.3**, not 7.x or 6.x: `typescript-eslint` supports `<6.1` and `openapi-typescript`
  peers on `^5`. TS 7 (the native port) is not supported by the lint toolchain yet.
- **ESLint 9.39**, not 10: `eslint-plugin-react` (pulled in by `eslint-config-next`) supports `^9.7`.
- Images pinned by tag: `python:3.12.16-slim-trixie`, `ghcr.io/astral-sh/uv:0.13.7`,
  `node:26.13.0-trixie-slim`, `pgvector/pgvector:0.8.7-pg16-trixie`,
  `mcr.microsoft.com/playwright:v1.65.0-noble`, `hashicorp/terraform:1.17.2`, `alpine/helm:3.22.1`.

## Consequences
Upgrades are deliberate: bump the bound or `exclude-newer`, relock, run `make check`. Digest pinning
of images is the next step for production builds (Renovate/Dependabot can maintain them).
