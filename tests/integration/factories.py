"""Helpers for integration tests."""

from __future__ import annotations

import uuid
from datetime import date

from dealdesk.adapters.db.runs import SqlDocumentStore, SqlRunRepository
from dealdesk.adapters.db.session import SessionFactory
from dealdesk.adapters.db.users import SqlUserRepository
from dealdesk.domain.models import UserRole
from dealdesk.ports.repositories import RunRecord, UserRecord


def make_user(
    sessions: SessionFactory, role: UserRole = UserRole.ESTIMATOR, email: str | None = None
) -> UserRecord:
    return SqlUserRepository(sessions).create(
        email=email or f"{uuid.uuid4().hex[:8]}@test.example",
        display_name="Test User",
        role=role,
        password_hash="not-a-real-hash",
    )


def make_run(sessions: SessionFactory, creator: UserRecord, title: str = "Sample run") -> RunRecord:
    document_id = SqlDocumentStore(sessions).put(
        kind="brief", filename="brief.txt", content_type="text/plain", content=b"SAMPLE brief"
    )
    return SqlRunRepository(sessions).create(
        run_id=uuid.uuid4(),
        title=title,
        created_by=creator.id,
        brief_document_id=document_id,
        brief_filename="brief.txt",
        brief_text="SAMPLE brief",
        start_date=date(2026, 1, 5),
    )
