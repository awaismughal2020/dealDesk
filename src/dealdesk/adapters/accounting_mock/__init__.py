"""Mock accounting system: stores invoice milestones locally. No external system is called."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from dealdesk.adapters.db.models import InvoiceMilestoneRow
from dealdesk.adapters.db.session import SessionFactory
from dealdesk.domain.models import InvoiceMilestone, InvoiceSchedule


class MockAccounting:
    """Implements `AccountingPort`. Idempotent per (run, milestone sequence)."""

    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    def upsert_invoice_schedule(self, run_id: UUID, schedule: InvoiceSchedule) -> None:
        """Insert milestones that do not exist yet."""
        rows = [
            {
                "run_id": run_id,
                "sequence": m.sequence,
                "percentage": m.percentage,
                "due_date": m.due_date,
                "net": m.net,
                "vat": m.vat,
                "gross": m.gross,
                "vat_rate": schedule.vat_rate,
            }
            for m in schedule.milestones
        ]
        statement = (
            insert(InvoiceMilestoneRow)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_invoice_milestones_seq")
        )
        with self._sessions.begin() as session:
            session.execute(statement)

    def get_invoice_schedule(self, run_id: UUID) -> InvoiceSchedule | None:
        """Return the schedule for a run, if any."""
        with self._sessions() as session:
            rows = list(
                session.scalars(
                    select(InvoiceMilestoneRow)
                    .where(InvoiceMilestoneRow.run_id == run_id)
                    .order_by(InvoiceMilestoneRow.sequence)
                )
            )
        if not rows:
            return None
        milestones = tuple(
            InvoiceMilestone(r.sequence, r.percentage, r.due_date, r.net, r.vat, r.gross)
            for r in rows
        )
        return InvoiceSchedule(
            milestones=milestones,
            net_total=sum((m.net for m in milestones), Decimal(0)),
            vat_total=sum((m.vat for m in milestones), Decimal(0)),
            gross_total=sum((m.gross for m in milestones), Decimal(0)),
            vat_rate=rows[0].vat_rate,
        )
