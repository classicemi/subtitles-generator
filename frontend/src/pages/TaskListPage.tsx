import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Activity, CheckCircle2, Clock3, DownloadCloud, FileVideo, RefreshCw, Search, Trash2, UploadCloud } from "lucide-react";
import StatusBadge from "../components/StatusBadge";
import { createTask, deleteTask, listTasks } from "../lib/api";
import { formatDate, formatDuration, languageLabel } from "../lib/format";
import type { TaskRecord } from "../lib/types";

export default function TaskListPage() {
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function load(showSpinner = false) {
    if (showSpinner) {
      setRefreshing(true);
    }
    try {
      const nextTasks = await listTasks();
      setTasks(nextTasks);
      setMessage(null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load tasks.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!tasks.some((task) => task.status === "queued" || task.status === "running")) {
      return undefined;
    }
    const timer = window.setInterval(() => load(), 2500);
    return () => window.clearInterval(timer);
  }, [tasks]);

  const filteredTasks = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return tasks;
    }
    return tasks.filter((task) => task.filename.toLowerCase().includes(normalized));
  }, [query, tasks]);

  const completedCount = tasks.filter((task) => task.status === "succeeded").length;
  const activeCount = tasks.filter((task) => task.status === "queued" || task.status === "running").length;

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile) {
      setMessage("Choose a media file first.");
      return;
    }
    setUploading(true);
    setMessage("Creating task...");
    try {
      const task = await createTask(selectedFile);
      setSelectedFile(null);
      setMessage(null);
      navigate(`/tasks/${task.id}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to create task.");
    } finally {
      setUploading(false);
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setSelectedFile(event.target.files?.[0] ?? null);
  }

  async function handleDelete(taskId: string, filename: string, event: React.MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    if (!window.confirm(`Delete "${filename}" and all its artifacts? This cannot be undone.`)) {
      return;
    }
    try {
      await deleteTask(taskId);
      setTasks((prev) => prev.filter((t) => t.id !== taskId));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to delete task.");
    }
  }

  return (
    <div className="stack">
      <section className="console-header">
        <div className="page-title">
          <p className="eyebrow">AI subtitle workspace</p>
          <h1>Task Console</h1>
          <p>Analyze local media, detect spoken language, and manage generated subtitle artifacts.</p>
        </div>
        <div className="header-actions">
          <button className="icon-text-button" type="button" onClick={() => load(true)} disabled={refreshing}>
            <RefreshCw size={16} />
            <span>Refresh</span>
          </button>
        </div>
      </section>

      <section className="operations-grid">
        <form className="upload-card" onSubmit={handleUpload}>
          <div>
            <p className="eyebrow">Create task</p>
            <h2>Upload source media</h2>
          </div>
          <label className="file-picker">
            <UploadCloud size={18} />
            <span>{selectedFile ? selectedFile.name : "Select video or audio file"}</span>
            <input
              type="file"
              accept=".mp4,.mov,.m4v,.mkv,.webm,.avi,.mp3,.wav,.m4a,.aac,.flac,.ogg,video/*,audio/*"
              onChange={handleFileChange}
            />
          </label>
          <button className="primary-action" type="submit" disabled={uploading}>
            <DownloadCloud size={17} />
            <span>{uploading ? "Creating" : "Create task"}</span>
          </button>
          {message && <p className="form-message">{message}</p>}
        </form>

        <section className="stats-grid" aria-label="Task summary">
          <Metric icon={<Activity size={18} />} label="Total tasks" value={String(tasks.length)} />
          <Metric icon={<CheckCircle2 size={18} />} label="Completed" value={String(completedCount)} />
          <Metric icon={<Clock3 size={18} />} label="Active" value={String(activeCount)} />
        </section>
      </section>

      <section className="content-card">
        <div className="card-head">
          <div>
            <p className="eyebrow">Task list</p>
            <h2>Media jobs</h2>
          </div>
          <div className="toolbar">
            <label className="search-box">
              <Search size={16} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search tasks" />
            </label>
          </div>
        </div>

        {loading ? (
          <div className="empty-state">Loading tasks...</div>
        ) : filteredTasks.length === 0 ? (
          <div className="empty-state">No tasks found.</div>
        ) : (
          <div className="task-table">
            <div className="task-table-head">
              <span>Source file</span>
              <span>Language</span>
              <span>Duration</span>
              <span>Progress</span>
              <span>Status</span>
            </div>
            {filteredTasks.map((task) => (
              <Link className="task-row" to={`/tasks/${task.id}`} key={task.id}>
                <div className="task-file">
                  <div className="file-icon">
                    <FileVideo size={19} />
                  </div>
                  <div>
                    <strong>{task.filename}</strong>
                    <span>{formatDate(task.created_at)}</span>
                  </div>
                </div>
                <div className="task-cell">{languageLabel(task)}</div>
                <div className="task-cell">{formatDuration(task.duration_seconds)}</div>
                <div className="task-cell">{task.progress}%</div>
                <div className="task-cell">
                  <StatusBadge status={task.status} />
                </div>
                <button
                  className="delete-task-btn"
                  type="button"
                  title="Delete task"
                  aria-label={`Delete ${task.filename}`}
                  onClick={(e) => handleDelete(task.id, task.filename, e)}
                >
                  <Trash2 size={16} />
                </button>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function Metric({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="metric-card">
      <div className="metric-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
