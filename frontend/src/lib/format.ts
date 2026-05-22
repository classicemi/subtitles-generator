import type { TaskRecord } from "./types";

export function formatDate(value?: string | null): string {
  if (!value) {
    return "Pending";
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatDuration(value?: number | null): string {
  if (typeof value !== "number") {
    return "Unknown";
  }
  const totalSeconds = Math.max(0, Math.round(value));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function formatSubtitleTime(value: number): string {
  const totalMilliseconds = Math.max(0, Math.round(value * 1000));
  const minutes = Math.floor(totalMilliseconds / 60000);
  const seconds = Math.floor((totalMilliseconds % 60000) / 1000);
  const milliseconds = totalMilliseconds % 1000;
  return `${minutes}:${String(seconds).padStart(2, "0")}.${String(milliseconds).padStart(3, "0")}`;
}

export function languageLabel(task: TaskRecord): string {
  if (!task.language) {
    return "Detecting";
  }
  if (typeof task.language_probability === "number") {
    return `${task.language} ${Math.round(task.language_probability * 100)}%`;
  }
  return task.language;
}

export function statusLabel(status: TaskRecord["status"]): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}
