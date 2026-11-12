"use client";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

export default function ErrorBoundary({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="space-y-4">
      <Alert tone="danger" title="Something went wrong">
        This part of the page could not be shown. Your work has not been lost.
      </Alert>
      <Button onClick={reset}>Try again</Button>
    </div>
  );
}
