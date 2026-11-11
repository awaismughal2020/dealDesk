"""Executes workflow runs in the background and resumes them after a restart."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from functools import partial
from typing import Any, Protocol
from uuid import UUID

from langgraph.types import Command

from dealdesk.application.workflow import RunState, Step
from dealdesk.domain.models import AuditEvent
from dealdesk.observability import get_logger
from dealdesk.ports.repositories import (
    ACTIVE_STATUSES,
    ApprovalRepository,
    AuditLog,
    RunRepository,
    RunStatus,
)

log = get_logger("workflow")
MAX_ERROR_CHARS = 300


class Executor(Protocol):
    """Anything that can run a callable later (a thread pool in production, inline in tests)."""

    def submit(self, fn: Callable[[], None], /) -> object:
        """Schedule `fn`."""


class Graph(Protocol):
    """The subset of a compiled LangGraph the runner uses."""

    def invoke(self, input: Any, config: Any) -> Any:  # noqa: A002, ANN401 - LangGraph signature
        """Run until the next interrupt or the end."""

    def get_state(self, config: Any) -> Any:  # noqa: ANN401 - LangGraph signature
        """Return the latest checkpointed state."""


def thread_config(run_id: UUID) -> dict[str, dict[str, str]]:
    """LangGraph config: one checkpoint thread per run."""
    return {"configurable": {"thread_id": str(run_id)}}


class WorkflowRunner:
    """Starts, resumes and recovers runs. Failures mark the run failed; they never crash the API."""

    def __init__(
        self,
        *,
        graph: Graph,
        runs: RunRepository,
        approvals: ApprovalRepository,
        audit: AuditLog,
        executor: Executor,
        clock: Callable[[], datetime],
    ) -> None:
        self._graph = graph
        self._runs = runs
        self._approvals = approvals
        self._audit = audit
        self._executor = executor
        self._clock = clock

    def start(self, run_id: UUID, request_id: str | None) -> None:
        """Begin a new run in the background."""
        initial: RunState = {"run_id": str(run_id), "request_id": request_id, "revisions": 0}
        self._executor.submit(lambda: self._drive(run_id, initial))

    def resume(self, run_id: UUID, decision: Mapping[str, str]) -> None:
        """Continue a run paused for approval with a recorded human decision."""
        self._executor.submit(lambda: self._drive(run_id, Command(resume=dict(decision))))

    def recover(self) -> list[UUID]:
        """Resume every run that was queued or running when the process stopped."""
        recovered = []
        for run_id in self._runs.ids_with_status(ACTIVE_STATUSES):
            snapshot = self._graph.get_state(thread_config(run_id))
            if not snapshot.values:
                fresh: RunState = {"run_id": str(run_id), "revisions": 0}
                self._executor.submit(partial(self._drive, run_id, fresh))
            elif tuple(snapshot.next) == (Step.AWAIT_APPROVAL,):
                self._resume_recorded_decision(run_id)
            else:
                self._executor.submit(partial(self._drive, run_id, None))
            recovered.append(run_id)
        return recovered

    def _resume_recorded_decision(self, run_id: UUID) -> None:
        decisions = self._approvals.for_run(run_id)
        if decisions:
            latest = decisions[-1]
            self.resume(run_id, {"decision": latest.decision.value, "comment": latest.comment})
        else:
            self._runs.update(run_id, {"status": RunStatus.AWAITING_APPROVAL})

    def _drive(self, run_id: UUID, graph_input: object) -> None:
        try:
            self._graph.invoke(graph_input, thread_config(run_id))
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"[:MAX_ERROR_CHARS]
            log.exception("run.failed", run_id=str(run_id), error_type=type(exc).__name__)
            self._runs.update(run_id, {"status": RunStatus.FAILED, "error": message})
            self._audit.append(
                AuditEvent(
                    "run.failed",
                    None,
                    "run",
                    str(run_id),
                    self._clock(),
                    details={"error_type": type(exc).__name__},
                )
            )
