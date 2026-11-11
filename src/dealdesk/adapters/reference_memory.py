"""In-memory reference data built from the SAMPLE seed files. Used by evals and unit tests.

Behaves like the Postgres adapter (same seed data, same cosine ranking and tie-break) without a
database, so `make eval` runs fully offline.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

from dealdesk.domain.models import CaseStudy, PastProject, RateCard, RateCardEntry, TeamMember
from dealdesk.ports.embedder import EmbedderPort
from dealdesk.ports.repositories import Scored

SIMILARITY_PLACES = Decimal("0.0001")


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def _ranked[T](
    items: list[tuple[str, T, list[float]]], query: Sequence[float], k: int
) -> list[Scored[T]]:
    scored = sorted(
        ((-_cosine(vector, query), key, item) for key, item, vector in items),
        key=lambda t: (t[0], t[1]),
    )
    return [
        Scored(item, str(Decimal(str(-negative)).quantize(SIMILARITY_PLACES)))
        for negative, _key, item in scored[:k]
    ]


class InMemoryReferenceData:
    """Implements `ReferenceData` from `data/seed/*.json`."""

    def __init__(self, seed_dir: Path, embedder: EmbedderPort) -> None:
        def load(name: str) -> dict[str, Any]:
            data: dict[str, Any] = json.loads((seed_dir / name).read_text(encoding="utf-8"))
            return data

        self._rate_card = RateCard.of(
            *(
                RateCardEntry(r["role"], Decimal(r["cost_rate"]), Decimal(r["sell_rate"]))
                for r in load("rate_card.json")["roles"]
            )
        )
        self._team = [
            TeamMember(m["id"], m["name"], m["role"], Decimal(m["weekly_hours"]))
            for m in load("team.json")["members"]
        ]
        projects = load("past_projects.json")["projects"]
        project_vectors = embedder.embed([f"{p['title']}. {p['summary']}" for p in projects])
        case_vectors = embedder.embed(
            [f"{p['case_study']['title']}. {p['case_study']['summary']}" for p in projects]
        )
        self._projects = [
            (
                p["id"],
                PastProject(
                    p["id"],
                    p["title"],
                    p["sector"],
                    p["summary"],
                    {role: Decimal(h) for role, h in p["actual_hours"].items()},
                ),
                vector,
            )
            for p, vector in zip(projects, project_vectors, strict=True)
        ]
        self._case_studies = [
            (
                p["case_study"]["id"],
                CaseStudy(
                    p["case_study"]["id"],
                    p["id"],
                    p["case_study"]["title"],
                    p["case_study"]["summary"],
                ),
                vector,
            )
            for p, vector in zip(projects, case_vectors, strict=True)
        ]

    def rate_card(self) -> RateCard:
        """Return the SAMPLE rate card."""
        return self._rate_card

    def team(self) -> list[TeamMember]:
        """Return the SAMPLE team."""
        return list(self._team)

    def similar_projects(self, embedding: Sequence[float], k: int) -> list[Scored[PastProject]]:
        """Return the `k` most similar projects."""
        return _ranked(self._projects, embedding, k)

    def similar_case_studies(self, embedding: Sequence[float], k: int) -> list[Scored[CaseStudy]]:
        """Return the `k` most similar case studies."""
        return _ranked(self._case_studies, embedding, k)
