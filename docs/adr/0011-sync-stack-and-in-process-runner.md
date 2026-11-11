# ADR 0011: A synchronous stack and an in-process workflow runner

Status: accepted

## Decision
FastAPI endpoints are synchronous (run in the thread pool) over SQLAlchemy 2 with psycopg 3 and
LangGraph's synchronous `PostgresSaver`. Workflow runs execute in a bounded `ThreadPoolExecutor`
inside the API process; on start-up the runner resumes queued or running runs from their checkpoints
(including a decision recorded just before a crash).

## Consequences
Simpler code, fully typed, easy to test (an inline executor makes tests deterministic). Throughput
is bounded by `WORKFLOW_MAX_WORKERS`; moving the runner to a worker process with a queue is the
scale-out path and needs no change to the workflow itself.
