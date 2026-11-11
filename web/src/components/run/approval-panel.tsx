"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { FlagList } from "@/components/status";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Dialog, DialogClose, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { FieldError, Label, Textarea } from "@/components/ui/input";
import { problemMessage } from "@/lib/api/client";
import type { RunDetail } from "@/lib/api/types";
import { formatGBP, ratioToPercent } from "@/lib/format";
import { useDecision } from "@/lib/hooks";

export const decisionSchema = (decision: "approve" | "reject") =>
  z.object({
    comment:
      decision === "reject"
        ? z
            .string()
            .trim()
            .min(1, "Say why you are rejecting, so the draft can be revised.")
            .max(2000)
        : z.string().trim().max(2000),
  });

function DecisionDialog({ run, decision }: { run: RunDetail; decision: "approve" | "reject" }) {
  const [open, setOpen] = useState(false);
  const mutation = useDecision(run.id);
  const form = useForm<{ comment: string }>({
    resolver: zodResolver(decisionSchema(decision)),
    defaultValues: { comment: "" },
  });
  const error = form.formState.errors.comment?.message;
  const approve = decision === "approve";

  const submit = form.handleSubmit(async ({ comment }) => {
    try {
      await mutation.mutateAsync({ decision, comment });
      toast.success(
        approve
          ? "Approved. Creating pipeline and invoice records."
          : "Rejected. The draft will be revised.",
      );
      setOpen(false);
      form.reset();
    } catch (problem) {
      toast.error(problemMessage(problem, "The decision was not recorded."));
    }
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant={approve ? "success" : "danger"}>{approve ? "Approve…" : "Reject…"}</Button>
      </DialogTrigger>
      <DialogContent
        title={approve ? "Approve this quote" : "Reject this draft"}
        description="This decision is recorded with your name, the time and your comment."
      >
        <dl className="bg-muted mb-4 grid grid-cols-2 gap-3 rounded-md p-3 text-sm">
          <dt>Price (ex VAT)</dt>
          <dd className="text-right font-semibold tabular-nums">{formatGBP(run.quote?.price)}</dd>
          <dt>Margin</dt>
          <dd className="text-right font-semibold tabular-nums">
            {ratioToPercent(run.quote?.margin)}
          </dd>
          <dt>Flags</dt>
          <dd className="flex justify-end">
            <FlagList flags={run.flags} />
          </dd>
        </dl>
        <form onSubmit={submit} noValidate className="space-y-3">
          <div>
            <Label htmlFor={`${decision}-comment`}>
              Comment{approve ? " (optional)" : " (required)"}
            </Label>
            <Textarea
              id={`${decision}-comment`}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? `${decision}-comment-error` : undefined}
              {...form.register("comment")}
            />
            <FieldError id={`${decision}-comment-error`} message={error} />
          </div>
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button
              type="submit"
              variant={approve ? "success" : "danger"}
              disabled={mutation.isPending}
            >
              {approve ? "Confirm approval" : "Confirm rejection"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function ApprovalPanel({ run }: { run: RunDetail }) {
  return (
    <Card aria-labelledby="approval-heading">
      <CardTitle id="approval-heading">Approval</CardTitle>
      {run.actions.can_decide ? (
        <div className="space-y-3">
          <p className="text-sm">
            Check the quote, flags and draft. Nothing is saved to the pipeline or invoice schedule
            until you approve.
          </p>
          <div className="flex gap-2">
            <DecisionDialog run={run} decision="approve" />
            <DecisionDialog run={run} decision="reject" />
          </div>
        </div>
      ) : (
        <Alert tone={run.status === "approved" ? "info" : "warning"}>
          {run.status === "approved"
            ? "This run has been approved."
            : run.actions.decide_blocked_reason}
        </Alert>
      )}
      {run.approvals.length > 0 ? (
        <ul className="mt-4 space-y-2 text-sm" aria-label="Decision history">
          {run.approvals.map((approval) => (
            <li key={approval.decided_at} className="border-border rounded-md border p-2">
              <strong>{approval.decision === "approved" ? "Approved" : "Rejected"}</strong> by{" "}
              {approval.decided_by_name} on {new Date(approval.decided_at).toLocaleString("en-GB")}
              {approval.comment ? (
                <p className="text-muted-foreground mt-1">“{approval.comment}”</p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}
