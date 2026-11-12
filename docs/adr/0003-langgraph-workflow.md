# ADR 0003: LangGraph for the workflow, with the Postgres checkpointer

Status: accepted

## Decision
The bid workflow is a LangGraph `StateGraph` with conditional edges (revision loop, approve or
reject) and an `interrupt()` at `await_approval`. State is checkpointed with
`langgraph-checkpoint-postgres` so runs survive restarts and can pause indefinitely. Graph state is
kept small (ids, counters, the decision); step outputs are stored on the run row so the API never
depends on checkpoint internals.

## Consequences
Restart-and-resume is tested by crashing a node and recovering with a new process. Nodes must be
idempotent (outputs are overwritten, downstream writes are upserts, `finalize` re-checks the
approval). The API runs the graph in a thread pool; a separate worker is the scale-out path.
