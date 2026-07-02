import { useState } from "react";
import type { ArtifactInfo } from "../types";
import { ArtifactCard } from "./ArtifactCard";

interface ArtifactGalleryProps {
  runId: string;
  artifacts: ArtifactInfo[];
  selectedFilename: string | null;
  onSelect: (filename: string) => void;
  /** Present only when the run has a backtest_result.json to chart (see App.tsx). */
  onOpenCharts?: () => void;
  isChartsSelected?: boolean;
}

const COLLAPSED_COUNT = 5;

function ChartsCard({ isSelected, onClick }: { isSelected: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`w-36 shrink-0 rounded-xl border overflow-hidden text-left bg-white transition-colors ${
        isSelected ? "border-warm-900" : "border-warm-150 hover:border-warm-300"
      }`}
    >
      <div className="h-24 bg-accent-50 flex items-center justify-center overflow-hidden text-2xl">📊</div>
      <div className="px-2.5 py-2 text-xs text-warm-700 truncate">Interactive Charts</div>
    </button>
  );
}

export function ArtifactGallery({ runId, artifacts, selectedFilename, onSelect, onOpenCharts, isChartsSelected }: ArtifactGalleryProps) {
  const [expanded, setExpanded] = useState(false);
  if (artifacts.length === 0 && !onOpenCharts) return null;

  const visible = expanded ? artifacts : artifacts.slice(0, COLLAPSED_COUNT);
  const remaining = artifacts.length - visible.length;

  return (
    <div className="mt-4">
      <div className="text-xs text-warm-400 mb-2">Generated · {artifacts.length}</div>
      <div className="flex gap-2.5 overflow-x-auto pb-1">
        {onOpenCharts && <ChartsCard isSelected={Boolean(isChartsSelected)} onClick={onOpenCharts} />}
        {visible.map((artifact) => (
          <ArtifactCard
            key={artifact.filename}
            runId={runId}
            artifact={artifact}
            isSelected={artifact.filename === selectedFilename}
            onClick={() => onSelect(artifact.filename)}
          />
        ))}
        {!expanded && remaining > 0 && (
          <button
            onClick={() => setExpanded(true)}
            className="w-36 h-[104px] shrink-0 rounded-xl border border-warm-150 text-sm text-warm-500 hover:bg-warm-50 transition-colors"
          >
            +{remaining} more
          </button>
        )}
      </div>
    </div>
  );
}
