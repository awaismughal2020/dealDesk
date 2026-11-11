"""HTTP request and response models. Amounts are decimal strings (GBP) computed by the server."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from dealdesk.domain.models import UserRole
from dealdesk.ports.repositories import RunStatus

Amount = Annotated[str, Field(description="Decimal string computed by the server (GBP or hours)")]
NON_NEGATIVE = Decimal(0)


class Model(BaseModel):
    """Strict base for API models."""

    model_config = ConfigDict(extra="forbid")


class Problem(Model):
    """RFC 9457 problem details."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    request_id: str | None = None
    errors: list[dict[str, str]] | None = None


# ---------------------------------------------------------------- auth and users


class CsrfOut(Model):
    """A CSRF token (also set as the `dd_csrf` cookie)."""

    csrf_token: str


class LoginIn(Model):
    """Sign-in form."""

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class UserOut(Model):
    """A user as shown to admins."""

    id: UUID
    email: str
    display_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


class MeOut(Model):
    """The signed-in user and what the server will allow them to do (UI hints only)."""

    id: UUID
    email: str
    display_name: str
    role: UserRole
    permissions: list[str]
    auth_mode: Literal["local", "oidc"]


class SessionOut(Model):
    """Returned after sign-in or refresh. Tokens are only ever in HttpOnly cookies."""

    user: MeOut
    access_expires_at: datetime


class UserCreateIn(Model):
    """Admin: create a local user."""

    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    display_name: str = Field(min_length=1, max_length=200)
    role: UserRole
    password: str = Field(min_length=1, max_length=256)


class UserPatchIn(Model):
    """Admin: change a user's role or deactivate them."""

    role: UserRole | None = None
    is_active: bool | None = None


class UserListOut(Model):
    """All users."""

    items: list[UserOut]


# ---------------------------------------------------------------- runs


class RequirementOut(Model):
    """One extracted requirement."""

    ref: str
    text: str
    category: str
    priority: str


class ExtractionOut(Model):
    """Requirements after screening (quarantined items are shown, never used)."""

    title: str
    summary: str
    requirements: list[RequirementOut]
    quarantined: list[RequirementOut]
    ambiguities: list[str]
    flags: list[str]


class ReferenceOut(Model):
    """A retrieved SAMPLE project or case study."""

    model_config = ConfigDict(extra="ignore")

    kind: Literal["project", "case_study"]
    id: str
    title: str
    summary: str
    similarity: Amount
    actual_hours_by_role: dict[str, Amount] | None = None


class RoleHoursOut(Model):
    """Model-proposed hours for one role."""

    role: str
    hours: Amount


class EstimateModelOut(Model):
    """What the model proposed (validated)."""

    roles: list[RoleHoursOut]
    rationale: str
    reference_project_ids: list[str]
    assumptions: list[str]


class EstimateOut(Model):
    """The accepted estimate."""

    hours_by_role: dict[str, Amount]
    total_hours: Amount
    model_output: EstimateModelOut


class QuoteLineOut(Model):
    """One role on the quote."""

    role: str
    hours: Amount
    adjusted_hours: Amount
    cost_rate: Amount
    sell_rate: Amount
    subtotal: Amount
    cost: Amount
    price: Amount


class QuoteOut(Model):
    """The code-computed quote."""

    lines: list[QuoteLineOut]
    subtotal: Amount
    contingency: Amount
    price: Amount
    cost: Amount
    margin: Amount
    flags: list[str]
    target_price: Amount | None
    price_gap_to_target: Amount | None


class PersonOut(Model):
    """Someone on the resource plan (SAMPLE roster)."""

    member_id: str
    name: str
    role: str


class AssignmentOut(Model):
    """Hours for one person in one week, and the share of their availability (1.0 = 100%)."""

    member_id: str
    week_index: int
    hours: Amount
    capacity: Amount
    utilisation: Amount


class ClashOut(Model):
    """A person booked above 100% in a week."""

    member_id: str
    week_index: int
    week_start: date
    hours: Amount
    capacity: Amount
    utilisation: Amount


class ResourcePlanOut(Model):
    """Hours per person per week."""

    week_starts: list[date]
    people: list[PersonOut]
    assignments: list[AssignmentOut]
    clashes: list[ClashOut]
    unstaffed_hours: dict[str, Amount]
    flags: list[str]


class ClaimOut(Model):
    """A cited relevant-experience claim."""

    text: str
    source_ids: list[str]


class SectionsOut(Model):
    """Model-drafted proposal prose."""

    executive_summary: str
    understanding: str
    scope_and_deliverables: list[str]
    approach: str
    team_and_timeline: str
    assumptions_and_exclusions: list[str]
    relevant_experience: list[ClaimOut]


class MilestoneOut(Model):
    """An invoice milestone."""

    sequence: int
    percentage: Amount
    due_date: date
    net: Amount
    vat: Amount
    gross: Amount


class ScheduleOut(Model):
    """Invoice milestones; each column sums exactly to its total."""

    milestones: list[MilestoneOut]
    net_total: Amount
    vat_total: Amount
    gross_total: Amount
    vat_rate: Amount


class ProposalOut(Model):
    """The current draft (or final) proposal."""

    sections: SectionsOut
    flags: list[str]
    uncited_claim_indexes: list[int]
    schedule: ScheduleOut


class StepOut(Model):
    """One execution of a workflow step."""

    step: str
    attempt: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None


class ApprovalOut(Model):
    """A recorded human decision."""

    decision: Literal["approved", "rejected"]
    decided_by: UUID
    decided_by_name: str
    comment: str
    decided_at: datetime


class PipelineRecordOut(Model):
    """The mock CRM opportunity created on approval."""

    title: str
    value: Amount
    margin: Amount
    stage: str
    approved_at: datetime


class RunActionsOut(Model):
    """What this user may do now. Usability hints; the server enforces every rule."""

    can_decide: bool
    decide_blocked_reason: str | None


class RunSummaryOut(Model):
    """A run in a list."""

    id: UUID
    title: str
    status: RunStatus
    created_by: UUID
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    current_step: str | None
    price: Amount | None
    margin: Amount | None
    flags: list[str]
    revision_count: int
    is_final: bool


class RunListOut(Model):
    """A page of runs."""

    items: list[RunSummaryOut]
    total: int
    limit: int
    offset: int


class RunDetailOut(RunSummaryOut):
    """Everything about one run."""

    brief_filename: str
    start_date: date
    error: str | None
    review_comment: str | None
    extraction: ExtractionOut | None
    references: list[ReferenceOut]
    estimate: EstimateOut | None
    quote: QuoteOut | None
    resource_plan: ResourcePlanOut | None
    proposal: ProposalOut | None
    has_proposal_document: bool
    steps: list[StepOut]
    approvals: list[ApprovalOut]
    pipeline_record: PipelineRecordOut | None
    invoice_schedule: ScheduleOut | None
    actions: RunActionsOut


class DecisionIn(Model):
    """Approve or reject. A rejection must include a comment."""

    comment: str = Field(default="", max_length=2000)


class SampleOut(Model):
    """A bundled SAMPLE brief."""

    id: str
    title: str
    description: str


class SampleListOut(Model):
    """Bundled SAMPLE briefs."""

    items: list[SampleOut]


# ---------------------------------------------------------------- impact


StepName = Literal[
    "extraction", "estimate_and_costing", "resource_check", "proposal_draft", "pipeline_and_invoice"
]


class StepHoursIn(Model):
    """Hours per step (assumptions)."""

    extraction: Decimal = Field(ge=NON_NEGATIVE, le=1000)
    estimate_and_costing: Decimal = Field(ge=NON_NEGATIVE, le=1000)
    resource_check: Decimal = Field(ge=NON_NEGATIVE, le=1000)
    proposal_draft: Decimal = Field(ge=NON_NEGATIVE, le=1000)
    pipeline_and_invoice: Decimal = Field(ge=NON_NEGATIVE, le=1000)


class ImpactAssumptionsIn(Model):
    """Every input to the impact calculator. All are assumptions, not measurements."""

    baseline_hours: StepHoursIn
    machine_hours: StepHoursIn
    review_hours: StepHoursIn
    bids_per_year: int = Field(ge=0, le=100_000)
    hourly_cost: Decimal = Field(ge=NON_NEGATIVE, le=10_000)
    fte_hours_per_year: Decimal = Field(gt=NON_NEGATIVE, le=10_000)
    cashable_share: Decimal = Field(ge=NON_NEGATIVE, le=1)


class StepImpactOut(Model):
    """By hand versus assisted for one step."""

    step: StepName
    baseline_hours: Amount
    assisted_hours: Amount
    hours_saved: Amount


class ImpactMetricsOut(Model):
    """Calculator output."""

    steps: list[StepImpactOut]
    baseline_hours_per_bid: Amount
    assisted_hours_per_bid: Amount
    hours_saved_per_bid: Amount
    annual_hours_saved: Amount
    fte_equivalent: Amount
    annual_value_full: Amount
    annual_value_cashable: Amount
    notice: str


class ImpactOut(Model):
    """Default assumptions, measured machine time, and the resulting metrics."""

    assumptions: ImpactAssumptionsIn
    measured_machine_hours: dict[str, Amount]
    measured_steps: list[str]
    metrics: ImpactMetricsOut


# ---------------------------------------------------------------- audit


class AuditEventOut(Model):
    """One audit event."""

    seq: int
    action: str
    actor_id: UUID | None
    subject_type: str
    subject_id: str
    occurred_at: datetime
    request_id: str | None
    details: dict[str, str]


class AuditPageOut(Model):
    """A page of audit events, newest first."""

    items: list[AuditEventOut]
    total: int
    limit: int
    offset: int


class HealthStatus(Model):
    """Probe response."""

    status: str
