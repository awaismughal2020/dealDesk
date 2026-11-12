import { Badge, type BadgeProps } from "@/components/ui/badge";
import type { RunStatus } from "@/lib/api/types";
import { humanise } from "@/lib/format";

const STATUS_TONE: Record<RunStatus, BadgeProps["tone"]> = {
  queued: "neutral",
  running: "info",
  awaiting_approval: "warning",
  approved: "success",
  failed: "danger",
};

export function StatusBadge({ status }: { status: RunStatus }) {
  return <Badge tone={STATUS_TONE[status]}>{humanise(status)}</Badge>;
}

const FLAG_TEXT: Record<string, string> = {
  BELOW_MINIMUM_MARGIN: "Below minimum margin",
  BELOW_TARGET_MARGIN: "Below target margin",
  REVISION_LIMIT_REACHED: "Revision limit reached",
  RESOURCE_CLASH: "Resource clash",
  UNSTAFFED_ROLE: "Unstaffed role",
  UNCITED_CLAIM: "Uncited claim",
  MODEL_STATED_FIGURES: "Model stated figures",
  POSSIBLE_PROMPT_INJECTION: "Possible prompt injection",
  ESTIMATE_REJECTED: "Estimate rejected",
};

const SEVERE = new Set([
  "BELOW_MINIMUM_MARGIN",
  "POSSIBLE_PROMPT_INJECTION",
  "UNCITED_CLAIM",
  "REVISION_LIMIT_REACHED",
]);

export function FlagList({ flags }: { flags: string[] }) {
  if (flags.length === 0) return <span className="text-muted-foreground text-sm">None</span>;
  return (
    <ul className="flex flex-wrap gap-1" aria-label="Flags">
      {flags.map((flag) => (
        <li key={flag}>
          <Badge tone={SEVERE.has(flag) ? "danger" : "warning"}>
            {FLAG_TEXT[flag] ?? humanise(flag)}
          </Badge>
        </li>
      ))}
    </ul>
  );
}

export function AiDraftLabel() {
  return (
    <Badge tone="info" aria-label="AI-assisted draft">
      AI-assisted draft
    </Badge>
  );
}

export function AssumptionsBanner() {
  return (
    <div
      role="note"
      className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950"
    >
      <strong>Assumptions, not measurements.</strong> Every input below is an adjustable assumption
      and the results are targets to be measured in a pilot. All data is SAMPLE data.
    </div>
  );
}
