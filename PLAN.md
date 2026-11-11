# Deal Desk MVP: build plan

Source of truth: [docs/SPEC.md](docs/SPEC.md). Decisions that the spec leaves open are recorded in [docs/adr/](docs/adr/).

Rule for every milestone: `make check` green inside Docker, then one conventional commit. No skipped tests, no weakened checks.

## Milestones

| # | Goal | Main files | Done when |
|---|------|-----------|-----------|
| M0 | Scaffold | `pyproject.toml`, `uv.lock`, `Dockerfile`, `docker-compose.yml`, `Makefile`, `scripts/init.py`, `.env.example`, `.gitignore`, `.dockerignore`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `src/dealdesk/{config.py,api/app.py}`, `web/` skeleton + `web/Dockerfile`, `tests/unit/test_health.py`, `.importlinter` | `make up` healthy, `make check` green |
| M1 | Domain core | `src/dealdesk/domain/{money,models,costing,resourcing,invoicing,impact,errors,flags}.py`, `tests/unit/domain/*` | 100% branch coverage on `domain/`, hypothesis tests, no-float test |
| M2 | Persistence | `adapters/db/{models,session,repositories}.py`, `migrations/`, `ports/repositories.py`, `scripts/seed.py`, `data/seed/*.json`, `tests/integration/*` | integration tests on real Postgres, `make seed` idempotent |
| M3 | Model layer | `ports/{llm,embedder}.py`, `adapters/llm/{fake,vertex,anthropic,openai,factory}.py`, `adapters/embeddings/*`, `application/prompts/*.md`, `application/schemas.py`, `evals/*` | `make eval` passes offline; injection brief changes no computed number |
| M4 | Workflow | `application/{workflow,services,runner}.py`, `adapters/crm_mock`, `adapters/accounting_mock` | e2e test brief → approval → records; restart mid-run resumes |
| M5 | API + auth | `auth/*`, `api/routers/*`, `api/{deps,errors,middleware,security}.py` | permission matrix, token attacks, no unprotected route, OpenAPI snapshot |
| M6 | Proposal | `adapters/docx/proposal.py` | `.docx` opens and contains code-computed commercials table |
| M7 | Front end | `web/src/**`, `web/scripts/gen-client.sh`, generated `web/src/lib/api/schema.d.ts` | `make web-lint`, `make web-test` green |
| M8 | End to end | `web/e2e/*`, `docker-compose.e2e.yml` | `make e2e` green from clean stack (incl. axe) |
| M9 | Infra + docs | `infra/terraform/*`, `deploy/helm/dealdesk/*`, `docs/*`, `README.md` | `make tf-validate`, `make helm-lint` green |
| M10 | Hardening | review vs spec §12, final report | `make check`, `make eval`, `make e2e`, `make demo` green from clean clone |

## Assumptions (each non-trivial one has an ADR)

1. **Repo state.** The repo had only `.gitattributes` and one empty initial commit, so nothing conflicts. Kept `.gitattributes`.
2. **Host tooling.** Host only needs Docker + Make. A `dev` build stage carries uv, dev dependencies and tools; every Make target runs inside containers. Source is bind-mounted, dependencies live in the image (`/opt/venv`, `/app/node_modules`) so macOS/Linux native binaries never mix.
3. **Sync stack.** FastAPI endpoints are sync (run in the threadpool), SQLAlchemy sync with psycopg 3, LangGraph `PostgresSaver` (sync). Simpler, fully typed, plenty for an MVP (ADR 0011).
4. **Background execution.** Workflow runs execute in an in-process bounded thread pool. On API startup, runs left `running` are resumed from their LangGraph checkpoint. A separate worker is the scale-out path (documented, not built).
5. **Documents** (uploaded brief text, generated `.docx`) are stored in Postgres (`documents` table) behind `DocumentStorePort`, which lets containers keep read-only root filesystems.
6. **Embeddings** are fixed at 256 dimensions (`EMBEDDING_DIM`). The fake embedder uses feature hashing; real adapters request 256-dim output (both Google and OpenAI embedding APIs support a dimensions parameter).
7. **FakeLLM** is deterministic: it returns recorded fixtures keyed by prompt id + input hash when present (`evals/fixtures/`), else a deterministic rule-based response. It never sees or follows instructions in briefs because it only pattern-matches requirement-shaped lines.
8. **Runs are team-visible.** The permission matrix says every role can read runs, so object-level checks on reads verify existence and permission; object-level checks on writes enforce state machine + separation of duties + ownership where relevant (users can only act on their own session, admins can't demote themselves).
9. **Cookies & paths.** Next.js proxies `/v1/*` to the API through a runtime route handler, so the browser path equals the API path. Access cookie `Path=/` (needed for page-level route protection), refresh cookie `Path=/v1/auth` (narrowest).
10. **Rate limiting** is an in-memory sliding window per process (documented single-replica limitation; Redis is the scale-out path).
11. **Keycloak `oidc` profile** is the first optional item to cut if time is short (spec §16). OIDC token validation is built and tested with a mocked JWKS regardless.
12. **Versions** were checked against PyPI, npm, Docker Hub and MCR on 2026-11-11 and pinned (lockfiles + image tags).
