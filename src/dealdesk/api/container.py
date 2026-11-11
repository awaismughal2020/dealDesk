"""Composition root: builds adapters from settings and wires them into services."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text

from dealdesk.adapters.accounting_mock import MockAccounting
from dealdesk.adapters.crm_mock import MockCRM
from dealdesk.adapters.db.audit import SqlAuditLog
from dealdesk.adapters.db.checkpointer import open_checkpointer
from dealdesk.adapters.db.reference import SqlReferenceData
from dealdesk.adapters.db.runs import SqlApprovalRepository, SqlDocumentStore, SqlRunRepository
from dealdesk.adapters.db.session import make_engine, make_session_factory
from dealdesk.adapters.db.users import SqlRefreshTokenRepository, SqlUserRepository
from dealdesk.adapters.docx.proposal import DocxProposalRenderer
from dealdesk.adapters.embeddings.factory import build_embedder
from dealdesk.adapters.llm.factory import build_llm
from dealdesk.application.pipeline import DealPipeline
from dealdesk.application.runner import Executor, WorkflowRunner
from dealdesk.application.runs import RunService
from dealdesk.application.workflow import ModelPricing, WorkflowDeps, build_graph
from dealdesk.auth.local import LocalSessionService, LocalTokenAuthenticator, LockoutPolicy
from dealdesk.auth.oidc import JwksCache, OidcAuthenticator, fetch_jwks
from dealdesk.auth.passwords import Argon2Params, PasswordHasher
from dealdesk.auth.port import AuthPort
from dealdesk.auth.ratelimit import SlidingWindowLimiter
from dealdesk.auth.tokens import KeyRing, TokenService
from dealdesk.config import AuthMode, Settings


def utc_now() -> datetime:
    """The system clock (UTC)."""
    return datetime.now(UTC)


@dataclass
class Container:
    """Everything the HTTP layer needs. Built once per process."""

    settings: Settings
    engine: Engine
    users: SqlUserRepository
    runs: SqlRunRepository
    approvals: SqlApprovalRepository
    audit: SqlAuditLog
    documents: SqlDocumentStore
    crm: MockCRM
    accounting: MockAccounting
    hasher: PasswordHasher
    tokens: TokenService
    authenticator: AuthPort
    sessions: LocalSessionService
    run_service: RunService
    runner: WorkflowRunner
    samples_dir: Path
    _closers: list[Any] = field(default_factory=list)

    def ready(self) -> bool:
        """True if the database answers."""
        with self.engine.connect() as connection:
            return connection.execute(text("SELECT 1")).scalar() == 1

    def close(self) -> None:
        """Release pools and threads."""
        for closer in reversed(self._closers):
            closer()
        self.engine.dispose()


def build_container(
    settings: Settings,
    *,
    executor: Executor | None = None,
    keys: KeyRing | None = None,
) -> Container:
    """Wire adapters and services. `executor` and `keys` can be overridden by tests."""
    url = settings.database_url.get_secret_value()
    engine = make_engine(url, pool_size=settings.db_pool_size)
    sessions = make_session_factory(engine)
    closers: list[Any] = []

    users, runs = SqlUserRepository(sessions), SqlRunRepository(sessions)
    approvals, audit = SqlApprovalRepository(sessions), SqlAuditLog(sessions)
    documents, reference = SqlDocumentStore(sessions), SqlReferenceData(sessions)
    crm, accounting = MockCRM(sessions), MockAccounting(sessions)

    pipeline = DealPipeline(
        llm=build_llm(settings),
        embedder=build_embedder(settings),
        reference=reference,
        policy=settings.costing_policy,
        top_k=settings.retrieval_top_k,
        max_revisions=settings.max_revisions,
    )
    saver, pool = open_checkpointer(url, max_size=settings.workflow_max_workers + 1)
    closers.append(pool.close)
    graph = build_graph(
        WorkflowDeps(
            pipeline=pipeline,
            runs=runs,
            users=users,
            reference=reference,
            audit=audit,
            approvals=approvals,
            documents=documents,
            renderer=DocxProposalRenderer(),
            crm=crm,
            accounting=accounting,
            invoice_policy=settings.invoice_policy,
            weeks=settings.project_weeks,
            pricing=ModelPricing(settings.llm_input_gbp_per_mtok, settings.llm_output_gbp_per_mtok),
            clock=utc_now,
            timer=time.monotonic,
        ),
        saver,
    )
    if executor is None:
        pool_executor = ThreadPoolExecutor(
            max_workers=settings.workflow_max_workers, thread_name_prefix="workflow"
        )
        closers.append(lambda: pool_executor.shutdown(wait=False, cancel_futures=False))
        executor = pool_executor
    runner = WorkflowRunner(
        graph=graph, runs=runs, approvals=approvals, audit=audit, executor=executor, clock=utc_now
    )
    hasher = PasswordHasher(
        Argon2Params(
            settings.argon2_time_cost, settings.argon2_memory_cost_kib, settings.argon2_parallelism
        )
    )
    tokens = TokenService(
        keys or KeyRing.load(Path(settings.jwt_keys_dir)),
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        ttl_seconds=settings.access_token_ttl_seconds,
    )
    authenticator: AuthPort
    if settings.auth_mode is AuthMode.OIDC:
        authenticator = OidcAuthenticator(
            jwks=JwksCache(lambda: fetch_jwks(settings.oidc_jwks_url)),
            issuer=settings.oidc_issuer,
            audience=settings.oidc_audience,
            role_claim=settings.oidc_role_claim,
            leeway_seconds=settings.oidc_clock_skew_seconds,
            users=users,
        )
    else:
        authenticator = LocalTokenAuthenticator(tokens, users)
    return Container(
        settings=settings,
        engine=engine,
        users=users,
        runs=runs,
        approvals=approvals,
        audit=audit,
        documents=documents,
        crm=crm,
        accounting=accounting,
        hasher=hasher,
        tokens=tokens,
        authenticator=authenticator,
        sessions=LocalSessionService(
            users=users,
            refresh_tokens=SqlRefreshTokenRepository(sessions),
            hasher=hasher,
            tokens=tokens,
            audit=audit,
            lockout=LockoutPolicy(settings.lockout_threshold, settings.lockout_seconds),
            ip_limiter=SlidingWindowLimiter(settings.login_rate_limit_per_ip_per_minute),
            account_limiter=SlidingWindowLimiter(settings.login_rate_limit_per_account_per_minute),
            refresh_ttl_seconds=settings.refresh_token_ttl_seconds,
            sleep=time.sleep,
        ),
        run_service=RunService(
            runs=runs,
            approvals=approvals,
            documents=documents,
            audit=audit,
            runner=runner,
            clock=utc_now,
            start_lead_days=settings.start_date_lead_days,
        ),
        runner=runner,
        samples_dir=Path(settings.data_dir) / "samples",
        _closers=closers,
    )
