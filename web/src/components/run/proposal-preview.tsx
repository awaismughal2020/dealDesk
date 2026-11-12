import { AiDraftLabel } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Table, Td, Th } from "@/components/ui/table";
import type { Proposal, RunDetail } from "@/lib/api/types";
import { formatDate, formatGBP, ratioToPercent } from "@/lib/format";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-4">
      <h3 className="font-semibold">{title}</h3>
      <div className="mt-1 text-sm whitespace-pre-line">{children}</div>
    </section>
  );
}

export function ProposalPreview({ run, proposal }: { run: RunDetail; proposal: Proposal }) {
  const { sections, schedule } = proposal;
  const uncited = new Set(proposal.uncited_claim_indexes);
  return (
    <Card aria-labelledby="proposal-heading">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <CardTitle id="proposal-heading" className="mb-0">
          Proposal {run.is_final ? "(final)" : "(draft)"}
        </CardTitle>
        <div className="flex items-center gap-2">
          {run.is_final ? null : <AiDraftLabel />}
          {run.has_proposal_document ? (
            <Button asChild variant="outline" size="sm">
              <a href={`/v1/runs/${run.id}/proposal.docx`} download>
                Download .docx
              </a>
            </Button>
          ) : null}
        </div>
      </div>
      {!run.is_final ? (
        <p className="mt-2 rounded bg-red-50 px-2 py-1 text-sm font-semibold text-red-900">
          DRAFT, requires approval
        </p>
      ) : null}
      <Section title="Executive summary">{sections.executive_summary}</Section>
      <Section title="Understanding of requirements">{sections.understanding}</Section>
      <Section title="Scope and deliverables">
        <ul className="list-disc pl-5">
          {sections.scope_and_deliverables.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </Section>
      <Section title="Approach">{sections.approach}</Section>
      <Section title="Team and timeline">{sections.team_and_timeline}</Section>
      <Section title="Payment milestones (computed by code)">
        <Table aria-label="Payment milestones">
          <thead>
            <tr>
              <Th>#</Th>
              <Th>Share</Th>
              <Th>Due</Th>
              <Th className="text-right">Net</Th>
              <Th className="text-right">VAT ({ratioToPercent(schedule.vat_rate)})</Th>
              <Th className="text-right">Gross</Th>
            </tr>
          </thead>
          <tbody>
            {schedule.milestones.map((m) => (
              <tr key={m.sequence}>
                <Td>{m.sequence}</Td>
                <Td>{m.percentage}%</Td>
                <Td>{formatDate(m.due_date)}</Td>
                <Td className="text-right tabular-nums">{formatGBP(m.net)}</Td>
                <Td className="text-right tabular-nums">{formatGBP(m.vat)}</Td>
                <Td className="text-right tabular-nums">{formatGBP(m.gross)}</Td>
              </tr>
            ))}
            <tr className="font-semibold">
              <Td colSpan={3}>Total</Td>
              <Td className="text-right tabular-nums">{formatGBP(schedule.net_total)}</Td>
              <Td className="text-right tabular-nums">{formatGBP(schedule.vat_total)}</Td>
              <Td className="text-right tabular-nums">{formatGBP(schedule.gross_total)}</Td>
            </tr>
          </tbody>
        </Table>
      </Section>
      <Section title="Assumptions and exclusions">
        <ul className="list-disc pl-5">
          {sections.assumptions_and_exclusions.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </Section>
      <Section title="Relevant experience (cited)">
        <ul className="list-disc pl-5">
          {sections.relevant_experience.map((claim, index) => (
            <li key={claim.text} className={uncited.has(index) ? "text-danger" : undefined}>
              {claim.text}{" "}
              <span className="font-mono text-xs">
                [{claim.source_ids.join(", ") || "UNCITED"}]
              </span>
            </li>
          ))}
        </ul>
      </Section>
    </Card>
  );
}
