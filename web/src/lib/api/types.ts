import type { components } from "./schema";

type Schemas = components["schemas"];

export type Me = Schemas["MeOut"];
export type Role = Me["role"];
export type RunSummary = Schemas["RunSummaryOut"];
export type RunDetail = Schemas["RunDetailOut"];
export type RunStatus = RunSummary["status"];
export type Quote = Schemas["QuoteOut"];
export type ResourcePlan = Schemas["ResourcePlanOut"];
export type Extraction = Schemas["ExtractionOut"];
export type Estimate = Schemas["EstimateOut"];
export type Proposal = Schemas["ProposalOut"];
export type Step = Schemas["StepOut"];
export type Sample = Schemas["SampleOut"];
export type ImpactAssumptions = Schemas["ImpactAssumptionsIn-Input"];
export type ImpactAssumptionsOut = Schemas["ImpactAssumptionsIn-Output"];
export type ImpactMetrics = Schemas["ImpactMetricsOut"];
export type Impact = Schemas["ImpactOut"];
export type User = Schemas["UserOut"];
export type AuditEvent = Schemas["AuditEventOut"];
export type Problem = Schemas["Problem"];

export const ACTIVE_STATUSES: readonly RunStatus[] = ["queued", "running"];
