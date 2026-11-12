"""Impact panel: hours, money and capacity saved. Every input is an assumption."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends

from dealdesk.api.deps import ContainerDep, require_permission
from dealdesk.api.schemas import (
    ImpactAssumptionsIn,
    ImpactMetricsOut,
    ImpactOut,
    StepHoursIn,
    StepImpactOut,
)
from dealdesk.auth.policy import Permission
from dealdesk.auth.port import Principal
from dealdesk.domain.impact import (
    ImpactAssumptions,
    ImpactMetrics,
    Step,
    calculate_impact,
    default_assumptions,
)

router = APIRouter(prefix="/v1/impact", tags=["impact"])
Reader = Annotated[Principal, Depends(require_permission(Permission.IMPACT_READ))]
NOTICE = (
    "Assumptions, not measurements. Savings are targets to be measured in a pilot; "
    "all data is SAMPLE data."
)
SECONDS_PER_HOUR = Decimal(3600)
HOURS_PLACES = Decimal("0.0001")
#: Which workflow steps make up each impact step (machine time is measured per workflow step).
WORKFLOW_STEPS = {
    "intake": Step.EXTRACTION,
    "estimate": Step.ESTIMATE_AND_COSTING,
    "cost": Step.ESTIMATE_AND_COSTING,
    "revise": Step.ESTIMATE_AND_COSTING,
    "resource_check": Step.RESOURCE_CHECK,
    "draft_proposal": Step.PROPOSAL_DRAFT,
    "finalize": Step.PIPELINE_AND_INVOICE,
}


def _hours(model: StepHoursIn) -> dict[Step, Decimal]:
    return {step: getattr(model, step.value) for step in Step}


def _hours_model(values: dict[Step, Decimal]) -> StepHoursIn:
    return StepHoursIn(**{step.value: values[step] for step in Step})


def _metrics_out(metrics: ImpactMetrics) -> ImpactMetricsOut:
    return ImpactMetricsOut(
        steps=[
            StepImpactOut(
                step=s.step.value,
                baseline_hours=str(s.baseline_hours),
                assisted_hours=str(s.assisted_hours),
                hours_saved=str(s.hours_saved),
            )
            for s in metrics.steps
        ],
        baseline_hours_per_bid=str(metrics.baseline_hours_per_bid),
        assisted_hours_per_bid=str(metrics.assisted_hours_per_bid),
        hours_saved_per_bid=str(metrics.hours_saved_per_bid),
        annual_hours_saved=str(metrics.annual_hours_saved),
        fte_equivalent=str(metrics.fte_equivalent),
        annual_value_full=str(metrics.annual_value_full),
        annual_value_cashable=str(metrics.annual_value_cashable),
        notice=NOTICE,
    )


@router.get("", response_model=ImpactOut, operation_id="getImpact")
def get_impact(_: Reader, container: ContainerDep) -> ImpactOut:
    """Default assumptions with machine time measured from completed workflow steps."""
    measured = container.runs.mean_step_seconds()
    machine = dict.fromkeys(Step, Decimal(0))
    for workflow_step, seconds in measured.items():
        if workflow_step in WORKFLOW_STEPS:
            impact_step = WORKFLOW_STEPS[workflow_step]
            machine[impact_step] += (Decimal(seconds) / SECONDS_PER_HOUR).quantize(HOURS_PLACES)
    assumptions = default_assumptions(machine)
    return ImpactOut(
        assumptions=ImpactAssumptionsIn(
            baseline_hours=_hours_model(dict(assumptions.baseline_hours)),
            machine_hours=_hours_model(machine),
            review_hours=_hours_model(dict(assumptions.review_hours)),
            bids_per_year=assumptions.bids_per_year,
            hourly_cost=assumptions.hourly_cost,
            fte_hours_per_year=assumptions.fte_hours_per_year,
            cashable_share=assumptions.cashable_share,
        ),
        measured_machine_hours={step.value: str(hours) for step, hours in machine.items()},
        measured_steps=sorted(measured),
        metrics=_metrics_out(calculate_impact(assumptions)),
    )


@router.post("/calculate", response_model=ImpactMetricsOut, operation_id="calculateImpact")
def calculate(body: ImpactAssumptionsIn, _: Reader) -> ImpactMetricsOut:
    """Recalculate with the user's assumptions. Read-only; nothing is stored."""
    assumptions = ImpactAssumptions(
        baseline_hours=_hours(body.baseline_hours),
        machine_hours=_hours(body.machine_hours),
        review_hours=_hours(body.review_hours),
        bids_per_year=body.bids_per_year,
        hourly_cost=body.hourly_cost,
        fte_hours_per_year=body.fte_hours_per_year,
        cashable_share=body.cashable_share,
    )
    return _metrics_out(calculate_impact(assumptions))
