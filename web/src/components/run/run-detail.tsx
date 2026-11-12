"use client";

import Link from "next/link";
import { QueryState } from "@/components/query-state";
import { ApprovalPanel } from "@/components/run/approval-panel";
import { ProposalPreview } from "@/components/run/proposal-preview";
import { QuotePanel } from "@/components/run/quote-panel";
import { ResourceHeatmap } from "@/components/run/resource-heatmap";
import { EstimatePanel, RequirementsPanel } from "@/components/run/scope-panels";
import { StepProgress } from "@/components/run/step-progress";
import { FlagList, StatusBadge } from "@/components/status";
import { Alert } from "@/components/ui/alert";
import { Card, CardTitle } from "@/components/ui/card";
import type { RunDetail } from "@/lib/api/types";
import { formatDate, formatGBP, ratioToPercent } from "@/lib/format";
import { useRun } from "@/lib/hooks";

function Downstream({ run }: { run: RunDetail }) {
  if (!run.pipeline_record || !run.invoice_schedule) return null;
  return (
    <Card aria-labelledby="downstream-heading">
      <CardTitle id="downstream-heading">Created on approval (mock CRM and accounting)</CardTitle>
      <p className="text-sm">
        Pipeline record “{run.pipeline_record.title}”: {formatGBP(run.pipeline_record.value)} at{" "}
        {ratioToPercent(run.pipeline_record.margin)} margin, stage {run.pipeline_record.stage}.
      </p>
      <p className="mt-1 text-sm">
        Invoice schedule: {run.invoice_schedule.milestones.length} milestones,{" "}
        {formatGBP(run.invoice_schedule.gross_total)} gross including VAT.
      </p>
    </Card>
  );
}

export function RunDetailView({ runId }: { runId: string }) {
  const query = useRun(runId);
  const run = query.data;
  return (
    <QueryState isPending={query.isPending} error={query.error} retry={() => void query.refetch()}>
      {run ? (
        <div className="space-y-6">
          <div>
            <Link href="/" className="text-brand text-sm underline">
              ← All runs
            </Link>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <h1 className="text-2xl font-bold">{run.title}</h1>
              <StatusBadge status={run.status} />
            </div>
            <p className="text-muted-foreground text-sm">
              {run.brief_filename} · created by {run.created_by_name} · planned start{" "}
              {formatDate(run.start_date)}
            </p>
            <div className="mt-2">
              <FlagList flags={run.flags} />
            </div>
          </div>
          <Card>
            <StepProgress run={run} />
          </Card>
          {run.status === "failed" ? (
            <Alert tone="danger" title="This run failed">
              {run.error ?? "Unknown error."}
            </Alert>
          ) : null}
          <div className="grid gap-6 xl:grid-cols-3">
            <div className="space-y-6 xl:col-span-2">
              {run.quote ? <QuotePanel quote={run.quote} /> : null}
              {run.resource_plan ? <ResourceHeatmap plan={run.resource_plan} /> : null}
              {run.proposal ? <ProposalPreview run={run} proposal={run.proposal} /> : null}
            </div>
            <div className="space-y-6">
              {run.quote ? <ApprovalPanel run={run} /> : null}
              <Downstream run={run} />
              {run.extraction ? <RequirementsPanel extraction={run.extraction} /> : null}
              {run.estimate ? <EstimatePanel estimate={run.estimate} run={run} /> : null}
            </div>
          </div>
        </div>
      ) : null}
    </QueryState>
  );
}
