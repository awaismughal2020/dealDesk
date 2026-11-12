"""Mock CRM: stores pipeline records in a local table. No external system is called."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from dealdesk.adapters.db.models import PipelineRecordRow
from dealdesk.adapters.db.session import SessionFactory
from dealdesk.domain.models import PipelineRecord

REFERENCE_PREFIX = "OPP-SAMPLE-"
REFERENCE_CHARS = 8


class MockCRM:
    """Implements `CRMPort`. Idempotent: one opportunity per run, keyed by run id."""

    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    def upsert_pipeline_record(self, record: PipelineRecord) -> str:
        """Create the opportunity unless it exists; return its reference either way."""
        reference = REFERENCE_PREFIX + record.run_id.hex[:REFERENCE_CHARS].upper()
        statement = (
            insert(PipelineRecordRow)
            .values(
                run_id=record.run_id,
                reference=reference,
                title=record.title,
                value=record.value,
                margin=record.margin,
                stage=record.stage,
                approved_by=record.approved_by,
                approved_at=record.approved_at,
            )
            .on_conflict_do_nothing(index_elements=["run_id"])
        )
        with self._sessions.begin() as session:
            session.execute(statement)
        return reference

    def get_pipeline_record(self, run_id: UUID) -> PipelineRecord | None:
        """Return the opportunity for a run, if any."""
        with self._sessions() as session:
            row = session.scalar(
                select(PipelineRecordRow).where(PipelineRecordRow.run_id == run_id)
            )
            if row is None:
                return None
            return PipelineRecord(
                run_id=row.run_id,
                title=row.title,
                value=row.value,
                margin=row.margin,
                stage=row.stage,
                approved_by=row.approved_by,
                approved_at=row.approved_at,
            )
