"""Approval rules that hold regardless of how a decision arrives (API, script, workflow)."""

from __future__ import annotations

from uuid import UUID

from dealdesk.domain.errors import SeparationOfDutiesError


def ensure_separation_of_duties(actor_id: UUID, creator_id: UUID) -> None:
    """Nobody may approve or reject a run they created."""
    if actor_id == creator_id:
        raise SeparationOfDutiesError("you cannot approve or reject a run you created")
