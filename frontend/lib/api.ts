import type { Run } from "@/lib/types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export function createRun(objective: string): Promise<Run> {
  return request<Run>("/api/runs", {
    method: "POST",
    body: JSON.stringify({ objective }),
  });
}

export function getRun(runId: string): Promise<Run> {
  return request<Run>(`/api/runs/${runId}`);
}

export function sendFollowUp(runId: string, message: string): Promise<Run> {
  return request<Run>(`/api/runs/${runId}/messages`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export function artifactUrl(artifactId: string): string {
  return `${API_URL}/api/artifacts/${artifactId}`;
}
