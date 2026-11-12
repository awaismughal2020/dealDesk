import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import type { RunDetail } from "@/lib/api/types";

export function renderWithClient(ui: ReactElement): RenderResult {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

export function runFixture(overrides: Partial<RunDetail> = {}): RunDetail {
  return {
    id: "7d1e0c62-0000-4000-8000-000000000001",
    title: "Tenant self-service portal",
    status: "awaiting_approval",
    created_by: "u1",
    created_by_name: "Demo Estimator (SAMPLE)",
    created_at: "2026-11-11T10:00:00Z",
    updated_at: "2026-11-11T10:00:05Z",
    current_step: "await_approval",
    price: "137830.00",
    margin: "0.3376",
    flags: ["BELOW_TARGET_MARGIN", "RESOURCE_CLASH"],
    revision_count: 0,
    is_final: false,
    brief_filename: "clean_brief.txt",
    start_date: "2026-11-30",
    error: null,
    review_comment: null,
    extraction: null,
    references: [],
    estimate: null,
    quote: {
      lines: [
        {
          role: "engineer",
          hours: "400",
          adjusted_hours: "440.00",
          cost_rate: "60.00",
          sell_rate: "90.00",
          subtotal: "36000.00",
          cost: "26400.00",
          price: "39600.00",
        },
      ],
      subtotal: "125300.00",
      contingency: "12530.00",
      price: "137830.00",
      cost: "91300.00",
      margin: "0.3376",
      flags: ["BELOW_TARGET_MARGIN"],
      target_price: "140461.54",
      price_gap_to_target: "2631.54",
    },
    resource_plan: null,
    proposal: null,
    has_proposal_document: true,
    steps: [
      {
        step: "intake",
        attempt: 1,
        status: "completed",
        started_at: "2026-11-11T10:00:00Z",
        finished_at: null,
        duration_ms: 12,
      },
    ],
    approvals: [],
    pipeline_record: null,
    invoice_schedule: null,
    actions: { can_decide: true, decide_blocked_reason: null },
    ...overrides,
  };
}
