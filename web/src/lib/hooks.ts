"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, authFetch } from "@/lib/api/client";
import {
  ACTIVE_STATUSES,
  type ImpactAssumptions,
  type RunStatus,
  type RunSummary,
} from "@/lib/api/types";

export const POLL_MS = 2_000;

async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown }>): Promise<T> {
  const { data, error } = await promise;
  if (error !== undefined || data === undefined) throw error ?? new Error("Empty response");
  return data;
}

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => unwrap(api.GET("/v1/auth/me")) });
}

export function useRuns(status: RunStatus | "all") {
  return useQuery({
    queryKey: ["runs", status],
    queryFn: () =>
      unwrap(
        api.GET("/v1/runs", {
          params: { query: { limit: 100, ...(status === "all" ? {} : { status }) } },
        }),
      ),
    refetchInterval: (query) =>
      query.state.data?.items.some((run) => ACTIVE_STATUSES.includes(run.status)) ? POLL_MS : false,
  });
}

export function useRun(runId: string) {
  return useQuery({
    queryKey: ["run", runId],
    queryFn: () => unwrap(api.GET("/v1/runs/{run_id}", { params: { path: { run_id: runId } } })),
    refetchInterval: (query) =>
      query.state.data && !ACTIVE_STATUSES.includes(query.state.data.status) ? false : POLL_MS,
  });
}

export function useSamples(enabled: boolean) {
  return useQuery({
    queryKey: ["samples"],
    queryFn: () => unwrap(api.GET("/v1/samples")),
    enabled,
  });
}

export function useCreateRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (input: { file: File } | { sampleId: string }): Promise<RunSummary> => {
      const form = new FormData();
      if ("file" in input) form.append("file", input.file);
      else form.append("sample_id", input.sampleId);
      const response = await authFetch("/v1/runs", { method: "POST", body: form });
      const body: unknown = await response.json();
      if (!response.ok) throw body;
      return body as RunSummary;
    },
    onSuccess: () => client.invalidateQueries({ queryKey: ["runs"] }),
  });
}

export function useDecision(runId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ decision, comment }: { decision: "approve" | "reject"; comment: string }) =>
      unwrap(
        decision === "approve"
          ? api.POST("/v1/runs/{run_id}/approve", {
              params: { path: { run_id: runId } },
              body: { comment },
            })
          : api.POST("/v1/runs/{run_id}/reject", {
              params: { path: { run_id: runId } },
              body: { comment },
            }),
      ),
    onSuccess: (run) => {
      client.setQueryData(["run", runId], run);
      void client.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}

export function useImpact() {
  return useQuery({ queryKey: ["impact"], queryFn: () => unwrap(api.GET("/v1/impact")) });
}

export function useCalculateImpact() {
  return useMutation({
    mutationFn: (body: ImpactAssumptions) => unwrap(api.POST("/v1/impact/calculate", { body })),
  });
}

export function useUsers(enabled: boolean) {
  return useQuery({
    queryKey: ["users"],
    queryFn: () => unwrap(api.GET("/v1/admin/users")),
    enabled,
  });
}

export function useCreateUser() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      email: string;
      display_name: string;
      role: "viewer" | "estimator" | "approver" | "admin";
      password: string;
    }) => unwrap(api.POST("/v1/admin/users", { body })),
    onSuccess: () => client.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useUpdateUser() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      userId,
      ...body
    }: {
      userId: string;
      role?: "viewer" | "estimator" | "approver" | "admin";
      is_active?: boolean;
    }) =>
      unwrap(
        api.PATCH("/v1/admin/users/{user_id}", { params: { path: { user_id: userId } }, body }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useAudit(filters: { action?: string; subject_id?: string; offset: number }) {
  return useQuery({
    queryKey: ["audit", filters],
    queryFn: () =>
      unwrap(
        api.GET("/v1/audit", {
          params: {
            query: {
              limit: 25,
              offset: filters.offset,
              ...(filters.action ? { action: filters.action } : {}),
              ...(filters.subject_id ? { subject_id: filters.subject_id } : {}),
            },
          },
        }),
      ),
  });
}

export function useLogout() {
  return useMutation({ mutationFn: () => api.POST("/v1/auth/logout") });
}
