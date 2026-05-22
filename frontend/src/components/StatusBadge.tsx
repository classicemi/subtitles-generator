import type { TaskStatus } from "../lib/types";
import { statusLabel } from "../lib/format";

interface StatusBadgeProps {
  status: TaskStatus;
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  return <span className={`status-badge ${status}`}>{statusLabel(status)}</span>;
}
