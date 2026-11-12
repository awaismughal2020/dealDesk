import { FlagList } from "@/components/status";
import { Card, CardTitle } from "@/components/ui/card";
import { Table, Td, Th } from "@/components/ui/table";
import type { Quote } from "@/lib/api/types";
import { formatGBP, formatHours, humanise, ratioToPercent } from "@/lib/format";

export function QuotePanel({ quote }: { quote: Quote }) {
  return (
    <Card aria-labelledby="quote-heading">
      <CardTitle id="quote-heading">Quote (computed by code)</CardTitle>
      <dl className="mb-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <dt className="text-muted-foreground text-xs">Price (ex VAT)</dt>
          <dd className="text-xl font-semibold tabular-nums">{formatGBP(quote.price)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground text-xs">Cost</dt>
          <dd className="text-xl font-semibold tabular-nums">{formatGBP(quote.cost)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground text-xs">Margin</dt>
          <dd className="text-xl font-semibold tabular-nums">{ratioToPercent(quote.margin)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground text-xs">Flags</dt>
          <dd>
            <FlagList flags={quote.flags} />
          </dd>
        </div>
      </dl>
      {quote.target_price ? (
        <p className="mb-4 rounded-md bg-amber-50 p-3 text-sm text-amber-950">
          To reach the target margin the price would need to be{" "}
          <strong className="tabular-nums">{formatGBP(quote.target_price)}</strong>, which is{" "}
          <strong className="tabular-nums">{formatGBP(quote.price_gap_to_target)}</strong> more.
        </p>
      ) : null}
      <Table aria-label="Quote lines">
        <thead>
          <tr>
            <Th>Role</Th>
            <Th className="text-right">Hours</Th>
            <Th className="text-right">Incl. contingency</Th>
            <Th className="text-right">Sell rate</Th>
            <Th className="text-right">Price</Th>
          </tr>
        </thead>
        <tbody>
          {quote.lines.map((line) => (
            <tr key={line.role}>
              <Td>{humanise(line.role)}</Td>
              <Td className="text-right tabular-nums">{formatHours(line.hours)}</Td>
              <Td className="text-right tabular-nums">{formatHours(line.adjusted_hours)}</Td>
              <Td className="text-right tabular-nums">{formatGBP(line.sell_rate)}</Td>
              <Td className="text-right tabular-nums">{formatGBP(line.price)}</Td>
            </tr>
          ))}
          <tr>
            <Td colSpan={4} className="text-right font-medium">
              Contingency included
            </Td>
            <Td className="text-right tabular-nums">{formatGBP(quote.contingency)}</Td>
          </tr>
        </tbody>
      </Table>
    </Card>
  );
}
