import { useMemo, useState } from "react";
import type { StagingArtifact, StagingConfig } from "../types";

interface StagingReviewPanelProps {
  artifact: StagingArtifact;
  isAwaiting: boolean;
  onConfirm: (overrides: Record<string, unknown>) => Promise<void>;
}

function formatNumber(value: unknown): string {
  return typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: 4 }) : String(value ?? "");
}

export function StagingReviewPanel({ artifact, isAwaiting, onConfirm }: StagingReviewPanelProps) {
  const initialCode = artifact.factor_spec?.code ?? "";
  const initialConfig = artifact.config ?? {};
  const [code, setCode] = useState(initialCode);
  const [configDraft, setConfigDraft] = useState<StagingConfig>(initialConfig);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const report = artifact.validation_report;
  const issues = report?.lookahead_issues ?? [];
  const reasons = artifact.gate_decision?.reasons ?? [];
  const metrics = useMemo(
    () => [
      ["Risk", artifact.gate_decision?.risk_score],
      ["Cost", artifact.gate_decision?.cost_score],
      ["NaN", report?.nan_ratio],
      ["Coverage", report?.coverage_ratio],
      ["Shift", report?.has_shift ? "yes" : "no"],
      ["Aligned", report?.output_aligned ? "yes" : "no"],
    ],
    [artifact.gate_decision?.cost_score, artifact.gate_decision?.risk_score, report],
  );

  const setConfig = (patch: Partial<StagingConfig>) =>
    setConfigDraft((prev) => ({ ...prev, ...patch }));

  const submit = async () => {
    const overrides: Record<string, unknown> = { config: configDraft };
    if (code !== initialCode) overrides.code = code;
    setIsSubmitting(true);
    try {
      await onConfirm(overrides);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="border border-warm-200 bg-white rounded-xl p-4 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-warm-900">实验提交前审查台</div>
          <div className="text-xs text-warm-500 mt-1">{artifact.factor_spec?.natural_language_definition}</div>
        </div>
        <div className="text-xs uppercase tracking-wide text-warm-500">{artifact.gate_decision?.decision ?? "staging"}</div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
        {metrics.map(([label, value]) => (
          <div key={label} className="border border-warm-150 rounded-lg px-2.5 py-2">
            <div className="text-[11px] text-warm-400">{label}</div>
            <div className="text-sm font-mono text-warm-800">{formatNumber(value)}</div>
          </div>
        ))}
      </div>

      {reasons.length > 0 && <div className="text-xs text-warm-600">Reasons: {reasons.join(", ")}</div>}
      {issues.length > 0 && (
        <div className="border border-danger-200 bg-danger-50 rounded-lg p-3 text-xs text-danger-900 space-y-1">
          {issues.map((issue, index) => (
            <div key={`${issue.pattern}-${index}`}>{issue.detail ?? issue.pattern}</div>
          ))}
        </div>
      )}

      <div>
        <div className="text-xs text-warm-500 mb-1">Formula</div>
        <div className="font-mono text-xs bg-warm-50 border border-warm-150 rounded-lg p-2 text-warm-800">
          {artifact.factor_spec?.formula}
        </div>
      </div>

      <textarea
        value={code}
        onChange={(event) => setCode(event.target.value)}
        className="w-full min-h-48 font-mono text-xs border border-warm-200 rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-warm-300"
        spellCheck={false}
      />

      <div className="flex flex-wrap items-center gap-2">
        <label className="text-xs text-warm-500">
          Fill price
          <select
            value={configDraft.execution?.fill_price ?? "open_t+1"}
            onChange={(e) =>
              setConfig({ execution: { ...configDraft.execution, fill_price: e.target.value as StagingConfig["execution"] extends { fill_price?: infer T } ? T : "open_t+1" | "close_t" | "close_t+1" } })
            }
            className="ml-1 border border-warm-200 rounded-lg px-2 py-1.5 text-sm"
            aria-label="Fill price"
          >
            <option value="open_t+1">open_t+1</option>
            <option value="close_t+1">close_t+1</option>
            <option value="close_t">close_t</option>
          </select>
        </label>
        <label className="text-xs text-warm-500">
          Groups
          <input
            value={configDraft.n_groups ?? ""}
            onChange={(e) => setConfig({ n_groups: e.target.value ? Number(e.target.value) : undefined })}
            placeholder="n_groups"
            inputMode="numeric"
            className="ml-1 w-20 border border-warm-200 rounded-lg px-2 py-1.5 text-sm"
            aria-label="Groups"
          />
        </label>
        <input
          value={configDraft.cost_bps ?? ""}
          onChange={(e) => setConfig({ cost_bps: e.target.value ? Number(e.target.value) : undefined })}
          placeholder="cost_bps"
          inputMode="decimal"
          className="w-28 border border-warm-200 rounded-lg px-2.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-warm-300"
        />
        <label className="text-xs text-warm-500 flex items-center gap-1">
          <input
            type="checkbox"
            checked={configDraft.neutralize?.includes("beta") ?? false}
            onChange={(e) => {
              const current = configDraft.neutralize ?? [];
              setConfig({ neutralize: e.target.checked ? [...current, "beta"] : current.filter((d) => d !== "beta") });
            }}
            aria-label="Neutralize beta"
          />
          β
        </label>
        <button
          type="button"
          disabled={!isAwaiting || isSubmitting}
          onClick={() => void submit()}
          className="px-3 py-2 rounded-lg bg-warm-900 text-white text-sm disabled:opacity-40"
        >
          Confirm
        </button>
      </div>
    </div>
  );
}
