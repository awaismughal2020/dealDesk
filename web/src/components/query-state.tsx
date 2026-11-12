"use client";

import type { ReactNode } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { PageSkeleton } from "@/components/ui/skeleton";
import { problemMessage } from "@/lib/api/client";

/** Loading skeleton, error with retry, or the content. */
export function QueryState({
  isPending,
  error,
  retry,
  children,
}: {
  isPending: boolean;
  error: unknown;
  retry: () => void;
  children: ReactNode;
}) {
  if (isPending) return <PageSkeleton />;
  if (error) {
    return (
      <div className="space-y-3">
        <Alert tone="danger" title="Could not load">
          {problemMessage(error)}
        </Alert>
        <Button variant="outline" onClick={retry}>
          Retry
        </Button>
      </div>
    );
  }
  return <>{children}</>;
}
