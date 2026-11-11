import { Badge } from "@/components/ui/badge";
import { Card, CardTitle } from "@/components/ui/card";
import { Table, Td, Th } from "@/components/ui/table";
import type { Estimate, Extraction, RunDetail } from "@/lib/api/types";
import { formatHours, humanise } from "@/lib/format";

export function RequirementsPanel({ extraction }: { extraction: Extraction }) {
  return (
    <Card aria-labelledby="requirements-heading">
      <CardTitle id="requirements-heading">
        Requirements ({extraction.requirements.length})
      </CardTitle>
      <ul className="space-y-2 text-sm">
        {extraction.requirements.map((r) => (
          <li key={r.ref} className="flex gap-2">
            <span className="text-muted-foreground font-mono text-xs">{r.ref}</span>
            <span className="flex-1">{r.text}</span>
            <Badge>{humanise(r.category)}</Badge>
            <Badge tone={r.priority === "must" ? "info" : "neutral"}>{r.priority}</Badge>
          </li>
        ))}
      </ul>
      {extraction.quarantined.length > 0 ? (
        <div className="mt-4 rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-950">
          <p className="font-semibold">Quarantined as possible prompt injection (not used):</p>
          <ul className="mt-1 list-disc pl-5">
            {extraction.quarantined.map((r) => (
              <li key={r.ref}>{r.text}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {extraction.ambiguities.length > 0 ? (
        <div className="mt-4 text-sm">
          <p className="font-semibold">Questions for the client</p>
          <ul className="list-disc pl-5">
            {extraction.ambiguities.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </Card>
  );
}

export function EstimatePanel({ estimate, run }: { estimate: Estimate; run: RunDetail }) {
  const projects = run.references.filter((r) => r.kind === "project");
  return (
    <Card aria-labelledby="estimate-heading">
      <CardTitle id="estimate-heading">Estimate by role (model-proposed, code-validated)</CardTitle>
      <Table aria-label="Hours by role">
        <thead>
          <tr>
            <Th>Role</Th>
            <Th className="text-right">Hours</Th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(estimate.hours_by_role).map(([role, hours]) => (
            <tr key={role}>
              <Td>{humanise(role)}</Td>
              <Td className="text-right tabular-nums">{formatHours(hours)}</Td>
            </tr>
          ))}
          <tr className="font-semibold">
            <Td>Total</Td>
            <Td className="text-right tabular-nums">{formatHours(estimate.total_hours)}</Td>
          </tr>
        </tbody>
      </Table>
      <p className="mt-3 text-sm">{estimate.model_output.rationale}</p>
      {projects.length > 0 ? (
        <p className="text-muted-foreground mt-2 text-xs">
          Grounded in SAMPLE past projects:{" "}
          {projects.map((p) => `${p.id} ${p.title} (similarity ${p.similarity})`).join("; ")}
        </p>
      ) : null}
    </Card>
  );
}
