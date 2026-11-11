"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { QueryState } from "@/components/query-state";
import { FlagList, StatusBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { Table, Td, Th } from "@/components/ui/table";
import type { RunStatus } from "@/lib/api/types";
import { formatDateTime, formatGBP, ratioToPercent } from "@/lib/format";
import { useMe, useRuns } from "@/lib/hooks";

const STATUS_OPTIONS: { value: RunStatus | "all"; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "awaiting_approval", label: "Awaiting approval" },
  { value: "running", label: "Running" },
  { value: "queued", label: "Queued" },
  { value: "approved", label: "Approved" },
  { value: "failed", label: "Failed" },
];

export function Dashboard() {
  const [status, setStatus] = useState<RunStatus | "all">("all");
  const [search, setSearch] = useState("");
  const me = useMe();
  const runs = useRuns(status);
  const canCreate = me.data?.permissions.includes("run:create") ?? false;
  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return (runs.data?.items ?? []).filter(
      (run) => !term || run.title.toLowerCase().includes(term),
    );
  }, [runs.data, search]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Runs</h1>
          <p className="text-muted-foreground text-sm">
            Every brief and where it is. Values and margins are computed by code.
          </p>
        </div>
        {canCreate ? (
          <Button asChild>
            <Link href="/runs/new">New run</Link>
          </Button>
        ) : null}
      </div>
      <Card>
        <div className="mb-4 flex flex-wrap gap-4">
          <div className="w-56">
            <Label htmlFor="status-filter">Status</Label>
            <Select
              id="status-filter"
              value={status}
              onChange={(e) => setStatus(e.target.value as RunStatus | "all")}
            >
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </div>
          <div className="w-72">
            <Label htmlFor="search">Search titles</Label>
            <Input
              id="search"
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>
        <QueryState isPending={runs.isPending} error={runs.error} retry={() => void runs.refetch()}>
          {visible.length === 0 ? (
            <p className="text-muted-foreground py-8 text-center">
              No runs yet.{canCreate ? " Start one with “New run”." : ""}
            </p>
          ) : (
            <Table aria-label="Runs">
              <thead>
                <tr>
                  <Th>Title</Th>
                  <Th>Status</Th>
                  <Th className="text-right">Value (ex VAT)</Th>
                  <Th className="text-right">Margin</Th>
                  <Th>Flags</Th>
                  <Th>Created</Th>
                </tr>
              </thead>
              <tbody>
                {visible.map((run) => (
                  <tr key={run.id}>
                    <Td>
                      <Link
                        href={`/runs/${run.id}`}
                        className="text-brand font-medium underline-offset-2 hover:underline"
                      >
                        {run.title}
                      </Link>
                      <div className="text-muted-foreground text-xs">by {run.created_by_name}</div>
                    </Td>
                    <Td>
                      <StatusBadge status={run.status} />
                    </Td>
                    <Td className="text-right tabular-nums">{formatGBP(run.price)}</Td>
                    <Td className="text-right tabular-nums">{ratioToPercent(run.margin)}</Td>
                    <Td>
                      <FlagList flags={run.flags} />
                    </Td>
                    <Td className="whitespace-nowrap">{formatDateTime(run.created_at)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </QueryState>
      </Card>
    </div>
  );
}
