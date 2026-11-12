"use client";

import { useState, type FormEvent } from "react";
import { QueryState } from "@/components/query-state";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { Table, Td, Th } from "@/components/ui/table";
import { formatDateTime } from "@/lib/format";
import { useAudit } from "@/lib/hooks";

const PAGE = 25;

export function AuditPanel() {
  const [filters, setFilters] = useState({ action: "", subject_id: "", offset: 0 });
  const [draft, setDraft] = useState({ action: "", subject_id: "" });
  const audit = useAudit(filters);
  const total = audit.data?.total ?? 0;

  function apply(event: FormEvent) {
    event.preventDefault();
    setFilters({ ...draft, offset: 0 });
  }

  return (
    <Card aria-labelledby="audit-heading">
      <CardTitle id="audit-heading">Audit log (append-only)</CardTitle>
      <form
        onSubmit={apply}
        className="mb-4 flex flex-wrap items-end gap-3"
        aria-label="Filter audit log"
      >
        <div>
          <Label htmlFor="audit-action">Action</Label>
          <Input
            id="audit-action"
            placeholder="e.g. run.approved"
            value={draft.action}
            onChange={(e) => setDraft({ ...draft, action: e.target.value })}
          />
        </div>
        <div>
          <Label htmlFor="audit-subject">Subject id</Label>
          <Input
            id="audit-subject"
            value={draft.subject_id}
            onChange={(e) => setDraft({ ...draft, subject_id: e.target.value })}
          />
        </div>
        <Button type="submit" variant="outline">
          Filter
        </Button>
      </form>
      <QueryState
        isPending={audit.isPending}
        error={audit.error}
        retry={() => void audit.refetch()}
      >
        <Table aria-label="Audit events">
          <thead>
            <tr>
              <Th>When</Th>
              <Th>Action</Th>
              <Th>Actor</Th>
              <Th>Subject</Th>
              <Th>Details</Th>
            </tr>
          </thead>
          <tbody>
            {audit.data?.items.map((event) => (
              <tr key={event.seq}>
                <Td className="whitespace-nowrap">{formatDateTime(event.occurred_at)}</Td>
                <Td className="font-mono text-xs">{event.action}</Td>
                <Td className="font-mono text-xs">{event.actor_id?.slice(0, 8) ?? "system"}</Td>
                <Td className="font-mono text-xs">
                  {event.subject_type}:{event.subject_id.slice(0, 8)}
                </Td>
                <Td className="text-xs">
                  {Object.entries(event.details)
                    .map(([key, value]) => `${key}=${value}`)
                    .join(" · ")}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
        <div className="mt-3 flex items-center justify-between text-sm">
          <span>
            {total === 0
              ? "No events"
              : `Showing ${filters.offset + 1}–${Math.min(filters.offset + PAGE, total)} of ${total}`}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={filters.offset === 0}
              onClick={() => setFilters({ ...filters, offset: Math.max(0, filters.offset - PAGE) })}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={filters.offset + PAGE >= total}
              onClick={() => setFilters({ ...filters, offset: filters.offset + PAGE })}
            >
              Next
            </Button>
          </div>
        </div>
      </QueryState>
    </Card>
  );
}
