import { X } from "lucide-react";
import type { TranscriptPayload } from "../lib/types";
import { formatSubtitleTime } from "../lib/format";

interface SubtitleDataModalProps {
  transcript: TranscriptPayload | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}

export default function SubtitleDataModal({ transcript, loading, error, onClose }: SubtitleDataModalProps) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="modal-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="subtitle-modal-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="modal-head">
          <div>
            <h2 id="subtitle-modal-title">Subtitle data</h2>
            <p>{transcript ? subtitleMetaText(transcript) : "Transcript JSON"}</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close subtitle data">
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          {loading && <div className="empty-state">Loading subtitle data...</div>}
          {error && <div className="error-box">{error}</div>}
          {transcript && <TranscriptTable transcript={transcript} />}
        </div>
      </section>
    </div>
  );
}

function TranscriptTable({ transcript }: { transcript: TranscriptPayload }) {
  const confidence =
    typeof transcript.language_probability === "number"
      ? `${Math.round(transcript.language_probability * 100)}%`
      : "Unknown";

  return (
    <>
      <dl className="subtitle-summary">
        <SummaryCell label="Language" value={transcript.language || "Unknown"} />
        <SummaryCell label="Confidence" value={confidence} />
        <SummaryCell label="Backend" value={transcript.backend || "Unknown"} />
        <SummaryCell label="Segments" value={String(transcript.segments.length)} />
      </dl>

      {transcript.segments.length > 0 ? (
        <div className="subtitle-table-wrap">
          <table className="subtitle-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Start</th>
                <th>End</th>
                <th>Text</th>
              </tr>
            </thead>
            <tbody>
              {transcript.segments.map((segment, index) => (
                <tr key={`${segment.start}-${segment.end}-${index}`}>
                  <td>{index + 1}</td>
                  <td>{formatSubtitleTime(segment.start)}</td>
                  <td>{formatSubtitleTime(segment.end)}</td>
                  <td>{segment.text}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="empty-state">No subtitle segments were found.</div>
      )}
    </>
  );
}

function SummaryCell({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function subtitleMetaText(transcript: TranscriptPayload): string {
  return [transcript.source_filename, `Language: ${transcript.language}`, `Backend: ${transcript.backend}`].join(" | ");
}
