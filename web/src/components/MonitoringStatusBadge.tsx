import type { MonitoringStatus } from "../types";

const DOT_BY_STATUS: Record<MonitoringStatus, string> = {
  ok: "bg-success-600",
  watch: "bg-warn-400",
  alert: "bg-danger-600",
  insufficient_data: "bg-warm-300",
};

const LABEL_BY_STATUS: Record<MonitoringStatus, string> = {
  ok: "监控: 正常",
  watch: "监控: 观察",
  alert: "监控: 警报",
  insufficient_data: "监控: 数据不足",
};

interface MonitoringStatusBadgeProps {
  status: MonitoringStatus | null | undefined;
  className?: string;
}

// Small dot indicator for a run's most recent live-decay check (see
// quantbench/monitor/). `null`/undefined means the run has never been
// checked - rendered as a hollow dot rather than hidden entirely, so its
// absence is visibly distinct from "known and healthy".
export function MonitoringStatusBadge({ status, className = "" }: MonitoringStatusBadgeProps) {
  if (!status) {
    return (
      <span
        className={`inline-block w-1.5 h-1.5 rounded-full border border-warm-300 ${className}`}
        title="未检查过存活情况"
        aria-label="monitoring: unchecked"
      />
    );
  }
  return (
    <span
      className={`inline-block w-1.5 h-1.5 rounded-full ${DOT_BY_STATUS[status]} ${className}`}
      title={LABEL_BY_STATUS[status]}
      aria-label={`monitoring: ${status}`}
    />
  );
}
