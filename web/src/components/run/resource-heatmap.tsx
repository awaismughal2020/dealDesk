import { Card, CardTitle } from "@/components/ui/card";
import type { ResourcePlan } from "@/lib/api/types";
import { formatDate, formatHours, humanise, ratioToPercent, utilisationBand } from "@/lib/format";
import { cn } from "@/lib/utils";

const BAND_CLASS = {
  low: "bg-green-50 text-green-950",
  medium: "bg-green-200 text-green-950",
  high: "bg-amber-200 text-amber-950",
  over: "bg-red-600 text-white font-semibold",
} as const;

export function ResourceHeatmap({ plan }: { plan: ResourcePlan }) {
  const cell = new Map(plan.assignments.map((a) => [`${a.member_id}:${a.week_index}`, a]));
  return (
    <Card aria-labelledby="resource-heading">
      <CardTitle id="resource-heading">Resource plan (SAMPLE team)</CardTitle>
      {plan.clashes.length > 0 ? (
        <p className="text-danger mb-3 text-sm">
          {plan.clashes.length} person-week{plan.clashes.length === 1 ? " is" : "s are"} booked
          above 100% of availability (shown in red with “over”).
        </p>
      ) : (
        <p className="text-success mb-3 text-sm">Nobody is booked above their availability.</p>
      )}
      {Object.keys(plan.unstaffed_hours).length > 0 ? (
        <p className="text-danger mb-3 text-sm">
          Unstaffed:{" "}
          {Object.entries(plan.unstaffed_hours)
            .map(([role, hours]) => `${humanise(role)} ${formatHours(hours)}`)
            .join(", ")}
        </p>
      ) : null}
      {/* Focusable so keyboard users can scroll wide plans. */}
      <div className="overflow-x-auto" role="region" aria-label="Resource plan table" tabIndex={0}>
        <table className="border-collapse text-xs" aria-label="Hours per person per week">
          <thead>
            <tr>
              <th scope="col" className="sticky left-0 bg-white px-2 py-1 text-left">
                Person
              </th>
              {plan.week_starts.map((week, index) => (
                <th key={week} scope="col" className="px-1 py-1 font-medium whitespace-nowrap">
                  W{index + 1}
                  <span className="sr-only"> starting {formatDate(week)}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {plan.people.map((person) => (
              <tr key={person.member_id}>
                <th
                  scope="row"
                  className="sticky left-0 bg-white px-2 py-1 text-left font-normal whitespace-nowrap"
                >
                  {person.name}
                  <span className="text-muted-foreground block">{humanise(person.role)}</span>
                </th>
                {plan.week_starts.map((week, index) => {
                  const assignment = cell.get(`${person.member_id}:${index}`);
                  if (!assignment)
                    return (
                      <td key={week} className="px-1 py-1 text-center text-zinc-400">
                        –
                      </td>
                    );
                  const band = utilisationBand(assignment.utilisation);
                  return (
                    <td
                      key={week}
                      className={cn(
                        "min-w-14 px-1 py-1 text-center tabular-nums",
                        BAND_CLASS[band],
                      )}
                      title={`${formatHours(assignment.hours)} of ${formatHours(assignment.capacity)}`}
                    >
                      {ratioToPercent(assignment.utilisation)}
                      {band === "over" ? <span className="block">over</span> : null}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
