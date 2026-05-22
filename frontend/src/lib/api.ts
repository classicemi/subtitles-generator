import type { ArtifactType, TaskRecord, TranscriptPayload } from "./types";

const configuredBase = import.meta.env.VITE_API_BASE as string | undefined;
export const API_BASE = configuredBase?.replace(/\/$/, "") ?? "";

async function requestJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload && typeof payload.detail === "string" ? payload.detail : "Request failed.";
    throw new Error(detail);
  }
  return payload as T;
}

export async function listTasks(): Promise<TaskRecord[]> {
  const payload = await requestJson<{ tasks: TaskRecord[] }>("/api/tasks");
  return payload.tasks;
}

export async function getTask(taskId: string): Promise<TaskRecord> {
  return requestJson<TaskRecord>(`/api/tasks/${taskId}`);
}

export async function createTask(file: File): Promise<TaskRecord> {
  const formData = new FormData();
  formData.append("video", file);
  return requestJson<TaskRecord>("/api/tasks", {
    method: "POST",
    body: formData,
  });
}

export async function regenerateTask(taskId: string): Promise<TaskRecord> {
  return requestJson<TaskRecord>(`/api/tasks/${taskId}/regenerate`, {
    method: "POST",
  });
}

export async function getTranscript(taskId: string): Promise<TranscriptPayload> {
  return requestJson<TranscriptPayload>(`/api/tasks/${taskId}/download/json`);
}

export function mediaUrl(taskId: string): string {
  return `${API_BASE}/api/tasks/${taskId}/media`;
}

export function artifactUrl(taskId: string, type: ArtifactType): string {
  return `${API_BASE}/api/tasks/${taskId}/download/${type}`;
}
