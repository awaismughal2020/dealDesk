"""Reference data: rate card, team roster, and pgvector retrieval over past work."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import select

from dealdesk.adapters.db.models import CaseStudyRow, PastProjectRow, RateCardRow, TeamMemberRow
from dealdesk.adapters.db.session import SessionFactory
from dealdesk.domain.models import CaseStudy, PastProject, RateCard, RateCardEntry, TeamMember
from dealdesk.ports.repositories import Scored

SIMILARITY_PLACES = Decimal("0.0001")


def _similarity(distance: object) -> str:
    """Cosine similarity = 1 - cosine distance, as a 4-dp string (no floats leave this module)."""
    return str((Decimal(1) - Decimal(str(distance))).quantize(SIMILARITY_PLACES))


class SqlReferenceData:
    """Read-only reference data."""

    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    def rate_card(self) -> RateCard:
        """Return the current rate card."""
        with self._sessions() as session:
            rows = session.scalars(select(RateCardRow).order_by(RateCardRow.role))
            return RateCard.of(*(RateCardEntry(r.role, r.cost_rate, r.sell_rate) for r in rows))

    def team(self) -> list[TeamMember]:
        """Return the team roster."""
        with self._sessions() as session:
            rows = session.scalars(select(TeamMemberRow).order_by(TeamMemberRow.id))
            return [TeamMember(r.id, r.name, r.role, r.weekly_hours) for r in rows]

    def similar_projects(self, embedding: Sequence[float], k: int) -> list[Scored[PastProject]]:
        """Return the `k` most similar past projects by cosine distance."""
        distance = PastProjectRow.embedding.cosine_distance(list(embedding))
        with self._sessions() as session:
            rows = session.execute(
                select(PastProjectRow, distance.label("d"))
                .order_by(distance, PastProjectRow.id)
                .limit(k)
            ).all()
            return [
                Scored(
                    PastProject(
                        project_id=row.id,
                        title=row.title,
                        sector=row.sector,
                        summary=row.summary,
                        actual_hours_by_role={
                            role: Decimal(str(hours)) for role, hours in row.actual_hours.items()
                        },
                    ),
                    _similarity(d),
                )
                for row, d in rows
            ]

    def similar_case_studies(self, embedding: Sequence[float], k: int) -> list[Scored[CaseStudy]]:
        """Return the `k` most similar case studies by cosine distance."""
        distance = CaseStudyRow.embedding.cosine_distance(list(embedding))
        with self._sessions() as session:
            rows = session.execute(
                select(CaseStudyRow, distance.label("d"))
                .order_by(distance, CaseStudyRow.id)
                .limit(k)
            ).all()
            return [
                Scored(CaseStudy(row.id, row.project_id, row.title, row.summary), _similarity(d))
                for row, d in rows
            ]
