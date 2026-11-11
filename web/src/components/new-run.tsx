"use client";

import { useRouter } from "next/navigation";
import { useId, useRef, useState, type DragEvent } from "react";
import { toast } from "sonner";
import { QueryState } from "@/components/query-state";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { problemMessage } from "@/lib/api/client";
import { useCreateRun, useMe, useSamples } from "@/lib/hooks";
import { checkBriefFile } from "@/lib/upload";
import { cn } from "@/lib/utils";

export function NewRun() {
  const router = useRouter();
  const me = useMe();
  const canCreate = me.data?.permissions.includes("run:create") ?? false;
  const samples = useSamples(canCreate);
  const createRun = useCreateRun();
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const hintId = useId();

  if (me.data && !canCreate) {
    return (
      <Alert tone="warning" title="Not available for your role">
        Only estimators and admins can start runs.
      </Alert>
    );
  }

  function choose(candidate: File | undefined) {
    if (!candidate) return;
    const problem = checkBriefFile(candidate);
    setFileError(problem);
    setFile(problem ? null : candidate);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    choose(event.dataTransfer.files[0]);
  }

  async function start(input: { file: File } | { sampleId: string }) {
    try {
      const run = await createRun.mutateAsync(input);
      toast.success("Run started");
      router.push(`/runs/${run.id}`);
    } catch (error) {
      toast.error(problemMessage(error, "Could not start the run."));
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">New run</h1>
      <Alert tone="info">
        With the default offline model nothing leaves this machine. Upload synthetic or public
        documents only.
      </Alert>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardTitle>Upload a brief</CardTitle>
          <div
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={cn(
              "border-border flex flex-col items-center justify-center gap-3 rounded-md border-2 border-dashed p-8 text-center",
              dragging && "border-brand bg-blue-50",
            )}
          >
            <p>Drag and drop a PDF or .txt file here, or</p>
            <Button type="button" variant="outline" onClick={() => inputRef.current?.click()}>
              Choose a file
            </Button>
            <label htmlFor="brief-file" className="sr-only">
              Brief file
            </label>
            <input
              id="brief-file"
              ref={inputRef}
              type="file"
              accept=".pdf,.txt,application/pdf,text/plain"
              className="sr-only"
              aria-describedby={hintId}
              onChange={(event) => choose(event.target.files?.[0])}
            />
            <p id={hintId} className="text-muted-foreground text-xs">
              PDF with selectable text or UTF-8 text, up to 10 MB.
            </p>
          </div>
          {fileError ? (
            <Alert tone="danger" className="mt-3">
              {fileError}
            </Alert>
          ) : null}
          {file ? (
            <div className="mt-4 flex items-center justify-between gap-2">
              <span className="truncate text-sm">{file.name}</span>
              <Button onClick={() => void start({ file })} disabled={createRun.isPending}>
                Start run
              </Button>
            </div>
          ) : null}
        </Card>
        <Card>
          <CardTitle>Or use a SAMPLE brief</CardTitle>
          <QueryState
            isPending={samples.isPending}
            error={samples.error}
            retry={() => void samples.refetch()}
          >
            <ul className="space-y-3">
              {samples.data?.items.map((sample) => (
                <li
                  key={sample.id}
                  className="border-border flex items-start justify-between gap-3 rounded-md border p-3"
                >
                  <div>
                    <p className="font-medium">{sample.title}</p>
                    <p className="text-muted-foreground text-sm">{sample.description}</p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={createRun.isPending}
                    onClick={() => void start({ sampleId: sample.id })}
                    aria-label={`Use sample: ${sample.title}`}
                  >
                    Use
                  </Button>
                </li>
              ))}
            </ul>
          </QueryState>
        </Card>
      </div>
    </div>
  );
}
