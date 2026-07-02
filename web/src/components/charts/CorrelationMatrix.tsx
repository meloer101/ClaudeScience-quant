export interface CorrelationMatrixProps {
  runIds: string[];
  matrix: Record<string, Record<string, number | null>>;
  /** Optional shorter label per run_id (e.g. hypothesis) for the header. */
  labels?: Record<string, string>;
}

/**
 * Fixed to a [-1, 1] color domain (unlike HeatmapGrid, which scales to its
 * data's own max) because a correlation coefficient's magnitude is only
 * meaningful relative to that fixed range - auto-scaling would make a run
 * set with only weak correlations look misleadingly saturated.
 */
export function CorrelationMatrix({ runIds, matrix, labels = {} }: CorrelationMatrixProps) {
  if (runIds.length < 2) return null;

  function cellColor(value: number | null): string {
    if (value === null) return "var(--color-warm-50)";
    const intensity = Math.min(1, Math.abs(value));
    return value >= 0
      ? `color-mix(in srgb, var(--color-accent-600) ${Math.round(intensity * 80)}%, white)`
      : `color-mix(in srgb, var(--color-danger-400) ${Math.round(intensity * 80)}%, white)`;
  }

  function shortLabel(runId: string): string {
    const label = labels[runId] ?? runId;
    return label.length > 18 ? `${label.slice(0, 17)}…` : label;
  }

  return (
    <div className="overflow-x-auto">
      <table className="text-[10px] border-collapse">
        <thead>
          <tr>
            <th className="w-28" />
            {runIds.map((runId) => (
              <th key={runId} className="px-1 py-0.5 font-normal text-warm-500 whitespace-nowrap" title={labels[runId] ?? runId}>
                {shortLabel(runId)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {runIds.map((rowId) => (
            <tr key={rowId}>
              <td className="pr-2 py-0.5 text-warm-500 whitespace-nowrap truncate max-w-28" title={labels[rowId] ?? rowId}>
                {shortLabel(rowId)}
              </td>
              {runIds.map((colId) => {
                const value = matrix[rowId]?.[colId] ?? null;
                return (
                  <td
                    key={colId}
                    title={value === null ? "insufficient overlapping data" : value.toFixed(3)}
                    className="w-14 h-7 text-center align-middle border border-white"
                    style={{ backgroundColor: cellColor(value) }}
                  >
                    <span className="text-warm-900">{value === null ? "—" : value.toFixed(2)}</span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
