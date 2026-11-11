# ADR 0007: Cloud Run as the live target, Helm as the Kubernetes route

Status: accepted

## Decision
Terraform for GCP: Artifact Registry, Cloud Run for web (public) and API (internal ingress, reached
through Direct VPC egress), Cloud SQL for PostgreSQL 16 with private IP and pgvector, Secret Manager
(values added out of band), least-privilege service accounts. A Helm chart provides the Kubernetes
route with a pre-install migration job, hardened pod security and optional HPA and NetworkPolicy.
Both are validated only (`make tf-validate`, `make helm-lint`); nothing is applied.

## Consequences
Cloud Run gives scale-to-zero for a demo. The in-memory rate limiter means API instance counts are
capped; a shared store is needed for strict global limits.
