# Deal Desk on Google Cloud (Terraform)

Validate-only in this repository: `make tf-validate` runs `terraform fmt -check` and
`terraform validate` with `-backend=false`. Nothing here runs `plan` against a real project or
`apply`, and no project ids or credentials are committed.

## What it creates

| Resource | Purpose |
| --- | --- |
| Artifact Registry (Docker, immutable tags) | API and web images |
| Cloud Run `…-api` (internal ingress only) | FastAPI; reachable only from the web service through Direct VPC egress |
| Cloud Run `…-web` (public) | Next.js front end; the only public entry point |
| Cloud SQL for PostgreSQL 16 (private IP, TLS only, PITR) | Application data, LangGraph checkpoints, pgvector |
| Secret Manager (`database-url`, `jwt-signing-key`, `llm-api-key`) | Created empty; values are added out of band, never via Terraform state |
| Service accounts `…-api` and `…-web` | Least privilege: API gets Cloud SQL client, per-secret accessor and (only for Vertex) `aiplatform.user`; web may only invoke the API |
| VPC, subnet, private service access | Web-to-API traffic and Cloud SQL private IP |

## Before a first apply (outside this repo)

1. Create a state bucket and run `terraform init -backend-config="bucket=<bucket>"`.
2. **Enable pgvector on the database**: connect as the owner and run `CREATE EXTENSION IF NOT EXISTS vector;`
   (the Alembic migration also does this, but the database user needs permission to create it).
3. Push images, then set `api_image` and `web_image` by digest.
4. Add secret versions: the database URL, an Ed25519 signing key (PEM) and, if not using Vertex, the LLM API key.
5. Run migrations as a one-off Cloud Run job using the API image:
   `alembic upgrade head && python -m scripts.setup_checkpointer`. Do **not** run the seed script; it refuses
   to run outside `APP_ENV=local` by design.
6. Use `auth_mode = "oidc"` with your identity provider for shared environments.

## Notes

- The API rate limiter is in memory per instance; `api_max_instances` keeps the effective limit predictable.
  Use Cloud Armor or a shared store for strict global limits.
- `web_public` grants `allUsers` the invoker role on the web service only. Put Identity-Aware Proxy or
  Cloud Armor in front if the demo must not be internet-reachable.
