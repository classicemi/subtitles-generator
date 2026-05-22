export type TaskStatus = "queued" | "running" | "succeeded" | "failed";

export type ArtifactType = "srt" | "vtt" | "json";

export interface TaskArtifact {
  type: ArtifactType;
  label: string;
  filename: string;
}

export interface TaskSource {
  filename: string;
  kind: "video" | "audio" | "media";
  url: string;
}

export interface TaskRecord {
  id: string;
  filename: string;
  source: TaskSource;
  status: TaskStatus;
  progress: number;
  language: string | null;
  language_probability: number | null;
  duration_seconds: number | null;
  backend: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  artifacts: TaskArtifact[];
}

export interface SubtitleSegment {
  start: number;
  end: number;
  text: string;
}

export interface TranscriptPayload {
  task_id: string;
  source_filename: string;
  generated_at: string;
  language: string;
  language_probability: number | null;
  backend: string;
  duration_seconds: number | null;
  segments: SubtitleSegment[];
}
