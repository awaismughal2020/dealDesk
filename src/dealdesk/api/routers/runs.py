"""Runs: start from a brief, list, inspect, approve or reject, download the proposal."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile

from dealdesk.adapters.briefs import read_brief
from dealdesk.api.container import Container
from dealdesk.api.deps import ContainerDep, request_id, require_permission
from dealdesk.api.errors import ApiError
from dealdesk.api.presenters import detail, summary
from dealdesk.api.schemas import (
    DecisionIn,
    Problem,
    RunDetailOut,
    RunListOut,
    RunSummaryOut,
    SampleListOut,
    SampleOut,
)
from dealdesk.application.runs import Actor, BriefUpload
from dealdesk.auth.policy import Permission
from dealdesk.auth.port import Principal
from dealdesk.domain.models import Decision
from dealdesk.ports.repositories import NotFoundError, RunQuery, RunRecord, RunStatus

router = APIRouter(prefix="/v1", tags=["runs"])
Reader = Annotated[Principal, Depends(require_permission(Permission.RUN_READ))]
Creator = Annotated[Principal, Depends(require_permission(Permission.RUN_CREATE))]
Decider = Annotated[Principal, Depends(require_permission(Permission.RUN_DECIDE))]

SAMPLE_ID = re.compile(r"^[a-z_]{1,40}$")
MAX_TITLE_CHARS = 200
SAMPLE_DESCRIPTIONS = {
    "clean_brief": "A clear brief with eight requirements. Expect a quote below the target margin.",
    "ambiguous_brief": "A vague AI brief. Ambiguities are listed and the revision loop runs.",
    "injection_brief": "The clean brief plus prompt-injection lines. Flagged; numbers unchanged.",
}
NOT_FOUND = ApiError(404, "Not found", "The requested run does not exist.")


def _names(container: Container) -> dict[UUID, str]:
    return {u.id: u.display_name for u in container.users.list_all()}


def _get(container: Container, run_id: UUID) -> RunRecord:
    run = container.runs.get(run_id)
    if run is None:
        raise NOT_FOUND
    return run


def _title(text: str, fallback: str) -> str:
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return (first or fallback)[:MAX_TITLE_CHARS]


def _sample_path(container: Container, sample_id: str) -> Path:
    path = container.samples_dir / f"{sample_id}.txt"
    if not SAMPLE_ID.match(sample_id) or not path.is_file():
        raise ApiError(404, "Not found", "No such sample brief.")
    return path


@router.get("/samples", response_model=SampleListOut, operation_id="listSamples")
def list_samples(_: Creator, container: ContainerDep) -> SampleListOut:
    """Bundled SAMPLE briefs that can start a run."""
    items = [
        SampleOut(
            id=path.stem,
            title=_title(path.read_text(encoding="utf-8"), path.stem),
            description=SAMPLE_DESCRIPTIONS.get(path.stem, "A SAMPLE brief."),
        )
        for path in sorted(container.samples_dir.glob("*.txt"))
    ]
    return SampleListOut(items=items)


@router.post(
    "/runs",
    response_model=RunSummaryOut,
    status_code=202,
    operation_id="createRun",
    responses={
        413: {"model": Problem, "description": "Too large"},
        415: {"model": Problem, "description": "Unsupported type"},
    },
)
def create_run(
    request: Request,
    user: Creator,
    container: ContainerDep,
    file: Annotated[UploadFile | None, File(description="Brief as PDF or UTF-8 text")] = None,
    sample_id: Annotated[str | None, Form(description="Or: id of a bundled SAMPLE brief")] = None,
) -> RunSummaryOut:
    """Upload a brief (or pick a sample) and start the workflow in the background."""
    limit = container.settings.upload_max_bytes
    if (file is None) == (sample_id is None):
        raise ApiError(422, "Invalid request", "Provide exactly one of `file` or `sample_id`.")
    if file is not None:
        content, name = file.file.read(limit + 1), file.filename
    else:
        path = _sample_path(container, str(sample_id))
        content, name = path.read_bytes(), path.name
    brief = read_brief(content, name, limit)
    upload = BriefUpload(
        brief.filename, brief.content_type, content, brief.text, _title(brief.text, brief.filename)
    )
    run = container.run_service.create(Actor(user.user_id, user.role), upload, request_id(request))
    return summary(run, _names(container))


@router.get("/runs", response_model=RunListOut, operation_id="listRuns")
def list_runs(
    _: Reader,
    container: ContainerDep,
    status: RunStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RunListOut:
    """Runs, newest first. Every role can read runs (team-wide visibility by design)."""
    runs, total = container.runs.list_runs(RunQuery(status=status, limit=limit, offset=offset))
    names = _names(container)
    return RunListOut(
        items=[summary(r, names) for r in runs], total=total, limit=limit, offset=offset
    )


@router.get("/runs/{run_id}", response_model=RunDetailOut, operation_id="getRun")
def get_run(run_id: UUID, user: Reader, container: ContainerDep) -> RunDetailOut:
    """State, steps, quote, flags, resource plan, proposal, decisions and downstream records."""
    run = _get(container, run_id)
    return detail(
        run,
        principal=user,
        names=_names(container),
        steps=container.runs.steps(run_id),
        approvals=container.approvals.for_run(run_id),
        pipeline=container.crm.get_pipeline_record(run_id),
        schedule=container.accounting.get_invoice_schedule(run_id),
    )


def _decide(
    run_id: UUID,
    *,
    decision: Decision,
    body: DecisionIn,
    request: Request,
    user: Principal,
    container: Container,
) -> RunDetailOut:
    _get(container, run_id)
    try:
        container.run_service.decide(
            Actor(user.user_id, user.role), run_id, decision, body.comment, request_id(request)
        )
    except NotFoundError as exc:
        raise NOT_FOUND from exc
    return get_run(run_id, user, container)


@router.post(
    "/runs/{run_id}/approve",
    response_model=RunDetailOut,
    operation_id="approveRun",
    responses={
        403: {"description": "Not an approver, or you created this run"},
        409: {"description": "Not awaiting approval"},
    },
)
def approve(
    run_id: UUID, body: DecisionIn, request: Request, user: Decider, container: ContainerDep
) -> RunDetailOut:
    """Approve exactly what is shown (price, margin, flags). Recorded with who, when and why."""
    return _decide(
        run_id,
        decision=Decision.APPROVED,
        body=body,
        request=request,
        user=user,
        container=container,
    )


@router.post(
    "/runs/{run_id}/reject",
    response_model=RunDetailOut,
    operation_id="rejectRun",
    responses={
        403: {"description": "Not an approver, or you created this run"},
        409: {"description": "Not awaiting approval"},
    },
)
def reject(
    run_id: UUID, body: DecisionIn, request: Request, user: Decider, container: ContainerDep
) -> RunDetailOut:
    """Reject with a comment; the run returns to drafting with the comment."""
    return _decide(
        run_id,
        decision=Decision.REJECTED,
        body=body,
        request=request,
        user=user,
        container=container,
    )


@router.get(
    "/runs/{run_id}/proposal.docx",
    operation_id="downloadProposal",
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {}
            }
        }
    },
)
def download_proposal(run_id: UUID, _: Reader, container: ContainerDep) -> Response:
    """The latest proposal document (DRAFT until approved)."""
    run = _get(container, run_id)
    document = (
        container.documents.get(run.proposal_document_id) if run.proposal_document_id else None
    )
    if document is None:
        raise ApiError(404, "Not found", "No proposal has been drafted for this run yet.")
    return Response(
        content=document.content,
        media_type=document.content_type,
        headers={"Content-Disposition": f'attachment; filename="{document.filename}"'},
    )
