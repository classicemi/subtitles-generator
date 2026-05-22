import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Download, Eye, FileJson, FileText, RefreshCw, RotateCcw } from "lucide-react";
import StatusBadge from "../components/StatusBadge";
import SubtitleDataModal from "../components/SubtitleDataModal";
import { artifactUrl, getTask, getTranscript, mediaUrl, regenerateTask } from "../lib/api";
import { formatDate, formatDuration, languageLabel } from "../lib/format";
import type { TaskArtifact, TaskRecord, TranscriptPayload } from "../lib/types";

export default function TaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [task, setTask] = useState<TaskRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<TranscriptPayload | null>(null);
  const [transcriptLoading, setTranscriptLoading] = useState(false);
  const [transcriptError, setTranscriptError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  async function load() {
    if (!taskId) {
      return;
    }
    try {
      const nextTask = await getTask(taskId);
      setTask(nextTask);
      setError(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to load task.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [taskId]);

  useEffect(() => {
    if (!task || (task.status !== "queued" && task.status !== "running")) {
      return undefined;
    }
    const timer = window.setInterval(() => load(), 2500);
    return () => window.clearInterval(timer);
  }, [task]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) {
      return;
    }
    for (const track of video.textTracks) {
      track.mode = track.kind === "subtitles" ? "showing" : "disabled";
    }
  }, [task]);

  async function openTranscript() {
    if (!taskId) {
      return;
    }
    setModalOpen(true);
    setTranscript(null);
    setTranscriptError(null);
    setTranscriptLoading(true);
    try {
      setTranscript(await getTranscript(taskId));
    } catch (requestError) {
      setTranscriptError(requestError instanceof Error ? requestError.message : "Unable to load subtitle data.");
    } finally {
      setTranscriptLoading(false);
    }
  }

  async function handleRegenerate() {
    if (!taskId) {
      return;
    }
    setRegenerating(true);
    setActionMessage("Regenerating subtitles...");
    try {
      const nextTask = await regenerateTask(taskId);
      setTask(nextTask);
      setActionMessage("Regeneration started.");
      window.setTimeout(() => load(), 800);
    } catch (requestError) {
      setActionMessage(requestError instanceof Error ? requestError.message : "Unable to regenerate subtitles.");
    } finally {
      setRegenerating(false);
    }
  }

  if (loading) {
    return <div className="content-card empty-state">Loading task...</div>;
  }

  if (error || !task) {
    return (
      <section className="content-card empty-state">
        <p>{error || "Task not found."}</p>
        <button className="secondary-action" type="button" onClick={() => navigate("/tasks")}>
          <ArrowLeft size={16} />
          <span>Back to tasks</span>
        </button>
      </section>
    );
  }

  const vttArtifact = findArtifact(task, "vtt");
  const jsonArtifact = findArtifact(task, "json");

  return (
    <div className="detail-layout">
      <section className="detail-main">
        <div className="detail-title">
          <Link className="back-link" to="/tasks">
            <ArrowLeft size={16} />
            <span>Tasks</span>
          </Link>
          <div className="detail-heading-row">
            <div>
              <p className="eyebrow">Source media</p>
              <h1>{task.filename}</h1>
            </div>
            <button className="icon-text-button" type="button" onClick={load}>
              <RefreshCw size={16} />
              <span>Refresh</span>
            </button>
          </div>
          <div className="title-meta">
            <StatusBadge status={task.status} />
            <span>Language: {languageLabel(task)}</span>
            <span>Duration: {formatDuration(task.duration_seconds)}</span>
          </div>
        </div>

        <div className="player-card">
          {task.source.kind === "video" ? (
            <video ref={videoRef} controls preload="metadata" src={mediaUrl(task.id)}>
              {vttArtifact && (
                <track
                  default
                  kind="subtitles"
                  src={artifactUrl(task.id, "vtt")}
                  srcLang={task.language || "und"}
                  label={task.language || "Subtitles"}
                />
              )}
            </video>
          ) : (
            <audio controls preload="metadata" src={mediaUrl(task.id)} />
          )}
        </div>

        {task.error && <div className="error-box">{task.error}</div>}
      </section>

      <aside className="detail-side">
        <section className="content-card">
          <div className="card-head compact">
            <div>
              <p className="eyebrow">Task detail</p>
              <h2>Artifacts</h2>
            </div>
            <button className="icon-button" type="button" onClick={load} aria-label="Refresh task">
              <RefreshCw size={17} />
            </button>
          </div>

          <dl className="detail-grid">
            <InfoCell label="Created" value={formatDate(task.created_at)} />
            <InfoCell label="Completed" value={formatDate(task.completed_at)} />
            <InfoCell label="Backend" value={task.backend || "Pending"} />
            <InfoCell label="Progress" value={`${task.progress}%`} />
          </dl>

          <div className="action-list">
            <button
              className="secondary-action wide"
              type="button"
              onClick={handleRegenerate}
              disabled={regenerating || task.status === "queued" || task.status === "running"}
            >
              <RotateCcw size={17} />
              <span>{regenerating ? "Starting regeneration" : "Regenerate subtitles"}</span>
            </button>
            {actionMessage && <p className="action-message">{actionMessage}</p>}
            {jsonArtifact && (
              <button className="primary-action wide" type="button" onClick={openTranscript}>
                <Eye size={17} />
                <span>View subtitle data</span>
              </button>
            )}
            {task.artifacts.map((artifact) => (
              <a className="download-row" href={artifactUrl(task.id, artifact.type)} key={artifact.type}>
                {artifact.type === "json" ? <FileJson size={17} /> : <FileText size={17} />}
                <span>{artifact.label}</span>
                <Download size={16} />
              </a>
            ))}
            {task.artifacts.length === 0 && <div className="empty-state compact">Artifacts will appear here.</div>}
          </div>
        </section>
      </aside>

      {modalOpen && (
        <SubtitleDataModal
          transcript={transcript}
          loading={transcriptLoading}
          error={transcriptError}
          onClose={() => setModalOpen(false)}
        />
      )}
    </div>
  );
}

function InfoCell({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function findArtifact(task: TaskRecord, type: TaskArtifact["type"]): TaskArtifact | undefined {
  return task.artifacts.find((artifact) => artifact.type === type);
}
