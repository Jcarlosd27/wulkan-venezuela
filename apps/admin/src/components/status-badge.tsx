import { getStatusLabel } from "../lib/status-labels";

interface StatusBadgeProps {
  status: string;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  return <span className={`statusBadge status-${status.replaceAll("_", "-")}`}>{getStatusLabel(status)}</span>;
}

