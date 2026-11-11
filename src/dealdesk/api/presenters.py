"""Map stored records to API models. No arithmetic: amounts are already strings from code."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from dealdesk.api.schemas import (
    ApprovalOut,
    EstimateOut,
    ExtractionOut,
    PipelineRecordOut,
    ProposalOut,
    QuoteOut,
    ReferenceOut,
    ResourcePlanOut,
    RunActionsOut,
    RunDetailOut,
    RunSummaryOut,
    ScheduleOut,
    StepOut,
)
from dealdesk.application.serialization import schedule_to_json
from dealdesk.auth.port import Principal
from dealdesk.domain.models import Approval, InvoiceSchedule, PipelineRecord, UserRole
from dealdesk.ports.repositories import RunRecord, RunStatus, StepRecord

UNKNOWN_USER = "Unknown user"


def summary(run: RunRecord, names: Mapping[UUID, str]) -> RunSummaryOut:
    """A run as a list item."""
    quote = run.quote or {}
    return RunSummaryOut(
        id=run.id,
        title=run.title,
        status=run.status,
        created_by=run.created_by,
        created_by_name=names.get(run.created_by, UNKNOWN_USER),
        created_at=run.created_at,
        updated_at=run.updated_at,
        current_step=run.current_step,
        price=quote.get("price"),
        margin=quote.get("margin"),
        flags=run.flags,
        revision_count=run.revision_count,
        is_final=run.is_final,
    )


def actions(run: RunRecord, principal: Principal) -> RunActionsOut:
    """Whether this user may decide now, and if not, why (the server enforces regardless)."""
    reason = None
    if principal.role is not UserRole.APPROVER:
        reason = "Only approvers can approve or reject runs."
    elif principal.user_id == run.created_by:
        reason = "You created this run, so someone else must approve it (separation of duties)."
    elif run.status is not RunStatus.AWAITING_APPROVAL:
        reason = "This run is not awaiting approval."
    return RunActionsOut(can_decide=reason is None, decide_blocked_reason=reason)


def detail(
    run: RunRecord,
    *,
    principal: Principal,
    names: Mapping[UUID, str],
    steps: list[StepRecord],
    approvals: list[Approval],
    pipeline: PipelineRecord | None,
    schedule: InvoiceSchedule | None,
) -> RunDetailOut:
    """Everything about a run."""
    base = summary(run, names)
    return RunDetailOut(
        **base.model_dump(),
        brief_filename=run.brief_filename,
        start_date=run.start_date,
        error=run.error,
        review_comment=run.review_comment,
        extraction=ExtractionOut.model_validate(run.requirements) if run.requirements else None,
        references=[ReferenceOut.model_validate(r) for r in run.references or []],
        estimate=EstimateOut.model_validate(run.estimate) if run.estimate else None,
        quote=QuoteOut.model_validate(run.quote) if run.quote else None,
        resource_plan=ResourcePlanOut.model_validate(run.resource_plan)
        if run.resource_plan
        else None,
        proposal=ProposalOut.model_validate(run.proposal) if run.proposal else None,
        has_proposal_document=run.proposal_document_id is not None,
        steps=[
            StepOut(
                step=s.step,
                attempt=s.attempt,
                status=s.status,
                started_at=s.started_at,
                finished_at=s.finished_at,
                duration_ms=s.duration_ms,
            )
            for s in steps
        ],
        approvals=[
            ApprovalOut(
                decision=a.decision.value,
                decided_by=a.decided_by,
                decided_by_name=names.get(a.decided_by, UNKNOWN_USER),
                comment=a.comment,
                decided_at=a.decided_at,
            )
            for a in approvals
        ],
        pipeline_record=(
            PipelineRecordOut(
                title=pipeline.title,
                value=str(pipeline.value),
                margin=str(pipeline.margin),
                stage=pipeline.stage,
                approved_at=pipeline.approved_at,
            )
            if pipeline
            else None
        ),
        invoice_schedule=ScheduleOut.model_validate(schedule_to_json(schedule))
        if schedule
        else None,
        actions=actions(run, principal),
    )
