"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ImpactMetrics } from "@/lib/api/types";
import { STEP_LABELS, type StepKey } from "./schema";

/** Bar heights need numbers; these are chart coordinates only, not money arithmetic. */
export function ImpactChart({ metrics }: { metrics: ImpactMetrics }) {
  const data = metrics.steps.map((step) => ({
    name: STEP_LABELS[step.step as StepKey],
    "By hand (h)": Number(step.baseline_hours),
    "Assisted (h)": Number(step.assisted_hours),
  }));
  return (
    <figure>
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Legend />
            <Bar dataKey="By hand (h)" fill="#71717a" />
            <Bar dataKey="Assisted (h)" fill="#1d4ed8" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="text-muted-foreground text-sm">
        Hours per bid by step, by hand versus assisted (assumptions).
      </figcaption>
    </figure>
  );
}
