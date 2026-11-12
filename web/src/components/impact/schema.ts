import { z } from "zod";
import type { ImpactAssumptions, ImpactAssumptionsOut } from "@/lib/api/types";

export const STEP_KEYS = [
  "extraction",
  "estimate_and_costing",
  "resource_check",
  "proposal_draft",
  "pipeline_and_invoice",
] as const;
export type StepKey = (typeof STEP_KEYS)[number];

export const STEP_LABELS: Record<StepKey, string> = {
  extraction: "Requirement extraction",
  estimate_and_costing: "Estimate and costing",
  resource_check: "Resource check",
  proposal_draft: "Proposal first draft",
  pipeline_and_invoice: "Pipeline and invoice setup",
};

const decimal = z
  .string()
  .trim()
  .regex(/^\d{1,4}(\.\d{1,4})?$/, "Enter a number like 4 or 0.5.");
const share = z
  .string()
  .trim()
  .regex(/^(0(\.\d{1,4})?|1(\.0{1,4})?)$/, "Enter a share between 0 and 1, like 0.6.");
const steps = z.object(
  Object.fromEntries(STEP_KEYS.map((key) => [key, decimal])) as Record<StepKey, typeof decimal>,
);

export const impactSchema = z.object({
  baseline_hours: steps,
  machine_hours: steps,
  review_hours: steps,
  bids_per_year: z
    .string()
    .trim()
    .regex(/^\d{1,5}$/, "Enter a whole number."),
  hourly_cost: decimal,
  fte_hours_per_year: z
    .string()
    .trim()
    .regex(/^[1-9]\d{0,3}(\.\d{1,2})?$/, "Enter a positive number of hours."),
  cashable_share: share,
});
export type ImpactFormValues = z.infer<typeof impactSchema>;

function toStrings(hours: Record<StepKey, string | number>): Record<StepKey, string> {
  return Object.fromEntries(STEP_KEYS.map((key) => [key, String(hours[key])])) as Record<
    StepKey,
    string
  >;
}

export function toFormValues(assumptions: ImpactAssumptionsOut): ImpactFormValues {
  return {
    baseline_hours: toStrings(assumptions.baseline_hours),
    machine_hours: toStrings(assumptions.machine_hours),
    review_hours: toStrings(assumptions.review_hours),
    bids_per_year: String(assumptions.bids_per_year),
    hourly_cost: String(assumptions.hourly_cost),
    fte_hours_per_year: String(assumptions.fte_hours_per_year),
    cashable_share: String(assumptions.cashable_share),
  };
}

/** Decimal strings go to the server as strings; the server does every calculation. */
export function toRequest(values: ImpactFormValues): ImpactAssumptions {
  return { ...values, bids_per_year: Number.parseInt(values.bids_per_year, 10) };
}
