import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ImpactResults } from "@/components/impact/impact-view";
import { impactSchema, toRequest } from "@/components/impact/schema";
import { ApprovalPanel } from "@/components/run/approval-panel";
import { QuotePanel } from "@/components/run/quote-panel";
import { ResourceHeatmap } from "@/components/run/resource-heatmap";
import { StepProgress } from "@/components/run/step-progress";
import { AssumptionsBanner, FlagList, StatusBadge } from "@/components/status";
import { renderWithClient, runFixture } from "@/test/render";

test("status badge and flags are readable", () => {
  render(<StatusBadge status="awaiting_approval" />);
  expect(screen.getByText("Awaiting approval")).toBeInTheDocument();
  render(<FlagList flags={["POSSIBLE_PROMPT_INJECTION", "RESOURCE_CLASH"]} />);
  const list = screen.getByRole("list", { name: "Flags" });
  expect(within(list).getByText("Possible prompt injection")).toBeInTheDocument();
  expect(within(list).getByText("Resource clash")).toBeInTheDocument();
});

test("quote panel shows the server's figures and the price needed for target margin", () => {
  render(<QuotePanel quote={runFixture().quote!} />);
  expect(screen.getByText("£137,830.00")).toBeInTheDocument();
  expect(screen.getByText("33.76%")).toBeInTheDocument();
  expect(screen.getByText("£140,461.54")).toBeInTheDocument();
  expect(screen.getByText("£2,631.54")).toBeInTheDocument();
});

test("approval dialog shows what is approved and requires a comment to reject", async () => {
  const user = userEvent.setup();
  renderWithClient(<ApprovalPanel run={runFixture()} />);
  await user.click(screen.getByRole("button", { name: "Reject…" }));
  const dialog = screen.getByRole("dialog", { name: "Reject this draft" });
  expect(within(dialog).getByText("£137,830.00")).toBeInTheDocument();
  expect(within(dialog).getByText("33.76%")).toBeInTheDocument();
  await user.click(within(dialog).getByRole("button", { name: "Confirm rejection" }));
  expect(await within(dialog).findByText(/Say why you are rejecting/)).toBeInTheDocument();
  expect(within(dialog).getByLabelText(/Comment/)).toHaveAttribute("aria-invalid", "true");
});

test("approval controls are replaced by the reason when the user cannot decide", () => {
  const reason = "You created this run, so someone else must approve it (separation of duties).";
  renderWithClient(
    <ApprovalPanel
      run={runFixture({ actions: { can_decide: false, decide_blocked_reason: reason } })}
    />,
  );
  expect(screen.queryByRole("button", { name: "Approve…" })).not.toBeInTheDocument();
  expect(screen.getByText(reason)).toBeInTheDocument();
});

test("resource heatmap marks over-allocation with text, not colour alone", () => {
  render(
    <ResourceHeatmap
      plan={{
        week_starts: ["2026-11-30", "2026-12-07"],
        people: [{ member_id: "TM-09", name: "Sample UX Designer A", role: "ux_designer" }],
        assignments: [
          {
            member_id: "TM-09",
            week_index: 0,
            hours: "14.67",
            capacity: "12.0",
            utilisation: "1.2225",
          },
          {
            member_id: "TM-09",
            week_index: 1,
            hours: "6.00",
            capacity: "12.0",
            utilisation: "0.5000",
          },
        ],
        clashes: [
          {
            member_id: "TM-09",
            week_index: 0,
            week_start: "2026-11-30",
            hours: "14.67",
            capacity: "12.0",
            utilisation: "1.2225",
          },
        ],
        unstaffed_hours: {},
        flags: ["RESOURCE_CLASH"],
      }}
    />,
  );
  expect(screen.getByText(/1 person-week is booked above/)).toBeInTheDocument();
  expect(screen.getByText("122.25%")).toBeInTheDocument();
  expect(screen.getByText("over")).toBeInTheDocument();
  expect(screen.getByText("50%")).toBeInTheDocument();
});

test("step progress announces the current step", () => {
  render(<StepProgress run={runFixture({ status: "running", current_step: "estimate" })} />);
  expect(screen.getByText("In progress: Estimate hours")).toHaveAttribute("aria-live", "polite");
  expect(screen.getByText("(done)", { exact: false })).toBeInTheDocument();
});

test("impact results and the assumptions banner", () => {
  render(<AssumptionsBanner />);
  expect(screen.getByRole("note")).toHaveTextContent("Assumptions, not measurements.");
  render(
    <ImpactResults
      metrics={{
        steps: [],
        baseline_hours_per_bid: "40.00",
        assisted_hours_per_bid: "6.75",
        hours_saved_per_bid: "33.25",
        annual_hours_saved: "1995.00",
        fte_equivalent: "1.21",
        annual_value_full: "149625.00",
        annual_value_cashable: "89775.00",
        notice: "Assumptions, not measurements.",
      }}
    />,
  );
  expect(screen.getByText("33.25 h")).toBeInTheDocument();
  expect(screen.getByText("1.21")).toBeInTheDocument();
  expect(screen.getByText("£89,775.00")).toBeInTheDocument();
});

test("impact form schema validates inputs and keeps decimals as strings", () => {
  const steps = {
    extraction: "4",
    estimate_and_costing: "8",
    resource_check: "4",
    proposal_draft: "20",
    pipeline_and_invoice: "4",
  };
  const values = {
    baseline_hours: steps,
    machine_hours: steps,
    review_hours: steps,
    bids_per_year: "60",
    hourly_cost: "75",
    fte_hours_per_year: "1650",
    cashable_share: "0.6",
  };
  const parsed = impactSchema.parse(values);
  expect(toRequest(parsed)).toMatchObject({
    bids_per_year: 60,
    hourly_cost: "75",
    cashable_share: "0.6",
  });
  expect(impactSchema.safeParse({ ...values, cashable_share: "1.5" }).success).toBe(false);
  expect(impactSchema.safeParse({ ...values, bids_per_year: "-1" }).success).toBe(false);
});
