import type { RunDetail } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const STEPS = [
  { key: "intake", label: "Extract requirements" },
  { key: "estimate", label: "Estimate hours" },
  { key: "cost", label: "Cost and margin" },
  { key: "resource_check", label: "Resource check" },
  { key: "draft_proposal", label: "Draft proposal" },
  { key: "await_approval", label: "Human approval" },
  { key: "finalize", label: "Pipeline and invoices" },
] as const;

type State = "done" | "current" | "failed" | "pending";

export function stepStates(run: RunDetail): Record<string, State> {
  const states: Record<string, State> = {};
  for (const step of STEPS) {
    const attempts = run.steps.filter((s) => s.step === step.key);
    const last = attempts.at(-1);
    states[step.key] =
      last?.status === "completed" ? "done" : last?.status === "failed" ? "failed" : "pending";
  }
  if (run.status === "awaiting_approval") states.await_approval = "current";
  if (run.status === "approved") states.await_approval = "done";
  if (run.status === "running" && run.current_step && states[run.current_step] !== "failed") {
    states[run.current_step] = "current";
  }
  return states;
}

const MARK: Record<State, string> = { done: "✓", current: "…", failed: "✕", pending: "○" };

export function StepProgress({ run }: { run: RunDetail }) {
  const states = stepStates(run);
  const current = STEPS.find((step) => states[step.key] === "current");
  return (
    <div>
      <p aria-live="polite" className="mb-3 text-sm font-medium">
        {run.status === "failed"
          ? "The run failed."
          : current
            ? `In progress: ${current.label}`
            : run.status === "approved"
              ? "Complete: approved and recorded."
              : "Queued"}
      </p>
      <ol className="grid gap-2 sm:grid-cols-4 lg:grid-cols-7">
        {STEPS.map((step) => {
          const state = states[step.key] ?? "pending";
          return (
            <li
              key={step.key}
              className={cn(
                "rounded-md border px-2 py-2 text-xs",
                state === "done" && "border-green-300 bg-green-50 text-green-950",
                state === "current" && "border-blue-400 bg-blue-50 text-blue-950",
                state === "failed" && "border-red-300 bg-red-50 text-red-950",
                state === "pending" && "border-border text-muted-foreground",
              )}
            >
              <span aria-hidden="true" className="mr-1">
                {MARK[state]}
              </span>
              {step.label}
              <span className="sr-only"> ({state})</span>
            </li>
          );
        })}
      </ol>
      {run.revision_count > 0 ? (
        <p className="text-muted-foreground mt-2 text-xs">
          The estimate was revised {run.revision_count} time{run.revision_count === 1 ? "" : "s"} to
          address the margin policy (hours or scope only, never rates).
        </p>
      ) : null}
    </div>
  );
}
