import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getMonitoringReport, triggerMonitoringCheck } from "../api/client";
import { MonitoringStatusBadge } from "./MonitoringStatusBadge";
import type { MonitoringStatus } from "../types";

interface MonitoringPanelProps {
  runId: string;
}

function fmtSharpe(value: number | null): string {
  if (value === null) return "-";
  return value.toFixed(3);
}

function fmtRatio(value: number | null): string {
  if (value === null) return "-";
  return `${(value * 100).toFixed(0)}%`;
}

export function MonitoringPanel({ runId }: MonitoringPanelProps) {
  const queryClient = useQueryClient();
  const [checking, setChecking] = useState(false);
  const [lastMessage, setLastMessage] = useState<string | null>(null);

  const { data } = useQuery({
    queryKey: ["monitoring-report", runId],
    queryFn: () => getMonitoringReport(runId),
  });

  const history = data?.history ?? [];
  const latest = history[history.length - 1];

  async function handleCheckNow() {
    setChecking(true);
    setLastMessage(null);
    try {
      const result = await triggerMonitoringCheck(runId);
      if ("skipped" in result) {
        setLastMessage(`未检查：${result.skipped}（verdict=${result.verdict ?? "无"}）`);
      } else if ("error" in result) {
        setLastMessage(`检查失败：${result.error}`);
      } else {
        setLastMessage(null);
      }
      await queryClient.invalidateQueries({ queryKey: ["monitoring-report", runId] });
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="mt-3 border border-warm-200 rounded-xl p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs font-medium text-warm-500 flex items-center gap-1.5">
          {latest && <MonitoringStatusBadge status={latest.status as MonitoringStatus} />}
          实时监控 · 策略衰减
          {latest && (
            <span className="text-warm-400 font-normal">
              最近检查 {new Date(latest.checked_at).toLocaleString()}
            </span>
          )}
        </div>
        <button
          onClick={handleCheckNow}
          disabled={checking}
          className="text-xs px-2 py-1 rounded-md bg-warm-900 text-white disabled:bg-warm-150 disabled:text-warm-500"
        >
          {checking ? "检查中…" : "立即检查"}
        </button>
      </div>

      {lastMessage && <div className="text-xs text-warm-500 mb-2">{lastMessage}</div>}

      {history.length === 0 && !lastMessage && (
        <div className="text-xs text-warm-400">尚未检查过。点击"立即检查"用最新数据重跑一次该 run 的因子代码。</div>
      )}

      {history.length > 0 && (
        <table className="text-xs border-collapse w-full">
          <thead>
            <tr className="text-warm-400">
              <td className="pr-3 py-0.5">检查时间</td>
              <td className="pr-3 py-0.5 text-right">原始 Sharpe</td>
              <td className="pr-3 py-0.5 text-right">近期 Sharpe</td>
              <td className="pr-3 py-0.5 text-right">衰减比</td>
              <td className="pr-3 py-0.5">状态</td>
            </tr>
          </thead>
          <tbody>
            {[...history].reverse().map((entry, index) => (
              <tr key={`${entry.checked_at}-${index}`} className="text-warm-700">
                <td className="pr-3 py-0.5">{new Date(entry.checked_at).toLocaleString()}</td>
                <td className="pr-3 py-0.5 text-right font-mono">{fmtSharpe(entry.original_sharpe)}</td>
                <td className="pr-3 py-0.5 text-right font-mono">{fmtSharpe(entry.recent_sharpe)}</td>
                <td className="pr-3 py-0.5 text-right font-mono">{fmtRatio(entry.sharpe_decay_ratio)}</td>
                <td className="py-0.5 flex items-center gap-1.5">
                  <MonitoringStatusBadge status={entry.status} />
                  <span className="text-warm-500">{entry.detail}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
