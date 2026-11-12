"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { QueryState } from "@/components/query-state";
import { AssumptionsBanner } from "@/components/status";
import { Card, CardTitle } from "@/components/ui/card";
import { FieldError, Input, Label } from "@/components/ui/input";
import { Table, Td, Th } from "@/components/ui/table";
import type { ImpactMetrics } from "@/lib/api/types";
import { formatGBP, formatHours, formatNumber } from "@/lib/format";
import { useCalculateImpact, useImpact } from "@/lib/hooks";
import { ImpactChart } from "./impact-chart";
import {
  impactSchema,
  STEP_KEYS,
  STEP_LABELS,
  toFormValues,
  toRequest,
  type ImpactFormValues,
} from "./schema";

const DEBOUNCE_MS = 400;

export function ImpactResults({ metrics }: { metrics: ImpactMetrics }) {
  const items = [
    ["Hours saved per bid", formatHours(metrics.hours_saved_per_bid)],
    ["Hours saved per year", formatHours(metrics.annual_hours_saved)],
    ["Capacity freed (FTE)", formatNumber(metrics.fte_equivalent)],
    ["Value of time saved per year", formatGBP(metrics.annual_value_full)],
    ["Cashable value per year", formatGBP(metrics.annual_value_cashable)],
  ] as const;
  return (
    <dl aria-live="polite" className="grid grid-cols-2 gap-4 md:grid-cols-5">
      {items.map(([label, value]) => (
        <div key={label} className="border-border rounded-md border p-3">
          <dt className="text-muted-foreground text-xs">{label} (assumption-based)</dt>
          <dd className="text-xl font-semibold tabular-nums">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function NumberField({
  name,
  label,
  form,
}: {
  name: string;
  label: string;
  form: ReturnType<typeof useForm<ImpactFormValues>>;
}) {
  const path = name as Parameters<typeof form.register>[0];
  const parts = name.split(".");
  const errors = form.formState.errors as Record<string, unknown>;
  const fieldError = parts.reduce<unknown>(
    (node, key) =>
      node && typeof node === "object" ? (node as Record<string, unknown>)[key] : undefined,
    errors,
  ) as { message?: string } | undefined;
  const id = name.replace(/\./g, "-");
  return (
    <div>
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        inputMode="decimal"
        aria-invalid={fieldError ? true : undefined}
        aria-describedby={fieldError ? `${id}-error` : undefined}
        {...form.register(path)}
      />
      <FieldError id={`${id}-error`} message={fieldError?.message} />
    </div>
  );
}

function ImpactEditor({
  initial,
  defaults,
}: {
  initial: ImpactFormValues;
  defaults: ImpactMetrics;
}) {
  const form = useForm<ImpactFormValues>({
    resolver: zodResolver(impactSchema),
    defaultValues: initial,
    mode: "onChange",
  });
  const calculate = useCalculateImpact();
  const [metrics, setMetrics] = useState(defaults);
  const values = useWatch({ control: form.control });
  const serialised = JSON.stringify(values);

  useEffect(() => {
    const timer = setTimeout(() => {
      const parsed = impactSchema.safeParse(JSON.parse(serialised));
      if (parsed.success) {
        calculate.mutate(toRequest(parsed.data), { onSuccess: setMetrics });
      }
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- recalculate only when the inputs change
  }, [serialised]);

  return (
    <div className="space-y-6">
      <ImpactResults metrics={metrics} />
      <Card>
        <ImpactChart metrics={metrics} />
      </Card>
      <Card>
        <CardTitle>Assumptions</CardTitle>
        <form noValidate onSubmit={(event) => event.preventDefault()} className="space-y-6">
          <Table aria-label="Hours per step">
            <thead>
              <tr>
                <Th>Step</Th>
                <Th>By hand (hours)</Th>
                <Th>Machine time (hours, measured)</Th>
                <Th>Human review (hours)</Th>
              </tr>
            </thead>
            <tbody>
              {STEP_KEYS.map((key) => (
                <tr key={key}>
                  <Td className="font-medium">{STEP_LABELS[key]}</Td>
                  <Td>
                    <NumberField
                      form={form}
                      name={`baseline_hours.${key}`}
                      label={`${STEP_LABELS[key]} by hand`}
                    />
                  </Td>
                  <Td>
                    <NumberField
                      form={form}
                      name={`machine_hours.${key}`}
                      label={`${STEP_LABELS[key]} machine time`}
                    />
                  </Td>
                  <Td>
                    <NumberField
                      form={form}
                      name={`review_hours.${key}`}
                      label={`${STEP_LABELS[key]} review time`}
                    />
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <div className="grid gap-4 md:grid-cols-4">
            <NumberField form={form} name="bids_per_year" label="Bids per year" />
            <NumberField form={form} name="hourly_cost" label="Hourly cost of staff time (£)" />
            <NumberField
              form={form}
              name="fte_hours_per_year"
              label="Working hours per FTE per year"
            />
            <NumberField
              form={form}
              name="cashable_share"
              label="Share of saved time that becomes cash (0 to 1)"
            />
          </div>
        </form>
      </Card>
    </div>
  );
}

export function ImpactView() {
  const impact = useImpact();
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Impact</h1>
      <AssumptionsBanner />
      <QueryState
        isPending={impact.isPending}
        error={impact.error}
        retry={() => void impact.refetch()}
      >
        {impact.data ? (
          <>
            <p className="text-muted-foreground text-sm">
              Machine time is measured from completed runs ({impact.data.measured_steps.length} step
              types so far); everything else is an assumption you can change. Results are
              recalculated by the server.
            </p>
            <ImpactEditor
              initial={toFormValues(impact.data.assumptions)}
              defaults={impact.data.metrics}
            />
          </>
        ) : null}
      </QueryState>
    </div>
  );
}
