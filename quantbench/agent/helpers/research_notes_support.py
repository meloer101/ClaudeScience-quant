import difflib
import json
from pathlib import Path
from typing import Any

from quantbench.agent.constants import CRYPTO_PERPETUAL_FUNDING_COVERAGE_WARNING
from quantbench.agent.run_context import _RunContext
from quantbench.api import run_reader
from quantbench.engine.cross_sectional_backtest import run_cross_sectional_backtest
from quantbench.review import ReviewReport
from quantbench.review.lookback import estimate_lookback_bars
from quantbench.skills.codeexec import run_signal_code, run_signal_code_panel
from quantbench.engine.vectorized_backtest import run_vectorized_backtest


def _data_slices_from_cache(cache_meta: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not cache_meta:
        return []
    slices = cache_meta.get("data_slices")
    if isinstance(slices, list):
        return slices
    path = cache_meta.get("path")
    content_hash = cache_meta.get("content_hash")
    if not path or not content_hash:
        return []
    return [
        {
            "symbol": cache_meta.get("symbol"),
            "timeframe": cache_meta.get("timeframe"),
            "start": cache_meta.get("start"),
            "end": cache_meta.get("end"),
            "path": path,
            "content_hash": content_hash,
            "rows": cache_meta.get("rows"),
            "provider": cache_meta.get("provider"),
            "source": cache_meta.get("source"),
            "adjustment": cache_meta.get("adjustment"),
            "fallback_reason": cache_meta.get("fallback_reason"),
        }
    ]


def _append_crypto_perpetual_warning(ctx: _RunContext) -> list[str]:
    meta = ctx.funding_meta or {}
    alignment = meta.get("alignment") if isinstance(meta, dict) else {}
    failed = meta.get("failed") if isinstance(meta, dict) else {}
    ratio = float((alignment or {}).get("coverage_ratio", 0.0) or 0.0)
    missing_pairs = int((alignment or {}).get("missing_period_symbol_pairs", 0) or 0)
    if ratio >= 0.98 and missing_pairs == 0 and not failed:
        return []
    warning = (
        f"{CRYPTO_PERPETUAL_FUNDING_COVERAGE_WARNING} "
        f"Aligned funding coverage={ratio:.1%}; missing period-symbol pairs={missing_pairs}; "
        f"failed symbols={len(failed or {})}."
    )
    if warning not in ctx.warnings:
        ctx.warnings.append(warning)
        return [warning]
    return []


def _review_warning_messages(review_report: ReviewReport) -> list[str]:
    messages: list[str] = []
    if review_report.verdict in {"WEAK", "REJECTED"}:
        messages.append(f"Reviewer verdict: {review_report.verdict} - {review_report.verdict_reason}")
    for finding in review_report.findings:
        if finding.severity in {"critical", "warning"}:
            messages.append(f"Reviewer {finding.severity.upper()} [{finding.check}]: {finding.message}")
    return messages


def _metrics_ci_for_run(run_dir: Path) -> dict[str, dict[str, float]] | None:
    path = run_dir / "backtest_result.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    metrics_ci = payload.get("metrics_ci")
    return metrics_ci if isinstance(metrics_ci, dict) else None


def _factor_metadata(code: str, total_observations: int | None = None) -> dict[str, Any]:
    estimate = estimate_lookback_bars(code, total_observations)
    return {"lookback_bars": estimate.lookback_bars, "lookback_source": estimate.source}


def _backtest_payload_with_factor_metadata(backtest: Any, code: str, total_observations: int | None = None) -> dict[str, Any]:
    payload = backtest.to_json_dict()
    payload["factor_metadata"] = _factor_metadata(code, total_observations)
    return payload


def _ic_significance_for_run(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / "backtest_result.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    ic_significance = payload.get("ic_significance")
    return ic_significance if isinstance(ic_significance, dict) else None


def _fork_lineage_markdown(parent_run_id: str, parent_signal_code: str, child_signal_path: Path, child_metrics: dict[str, float]) -> str:
    parent_manifest = run_reader.read_manifest(parent_run_id) or {}
    parent_metrics = parent_manifest.get("metrics") or {}
    delta_lines = []
    for key in ("sharpe", "annual_return", "max_drawdown", "turnover_annual", "ic_mean"):
        before = parent_metrics.get(key)
        after = child_metrics.get(key)
        if before is None or after is None:
            continue
        delta_lines.append(f"- {key}: {before} → {after} (delta {after - before:+.4g})")

    child_signal = child_signal_path.read_text(encoding="utf-8") if child_signal_path.exists() else ""
    diff = "".join(
        difflib.unified_diff(
            parent_signal_code.splitlines(keepends=True),
            child_signal.splitlines(keepends=True),
            fromfile=f"{parent_run_id}/signal.py",
            tofile="child/signal.py",
        )
    )
    diff_block = f"\n```diff\n{diff[:4000]}\n```\n" if diff else "\n(信号代码无差异或不可用)\n"
    return f"""## 谱系
- 父 run: `{parent_run_id}`

### 指标变化
{chr(10).join(delta_lines) if delta_lines else "- 指标 delta 不可用"}

### 信号 diff
{diff_block}
"""


def _rerun_single_with_code(code: str, data_df, cost_bps: float) -> dict[str, float] | None:
    try:
        signal = run_signal_code(code, data_df)
        return run_vectorized_backtest(data_df, signal, cost_bps=cost_bps).metrics
    except Exception:
        return None


def _rerun_cross_with_code(
    code: str,
    panel,
    n_groups: int,
    cost_bps: float,
    membership_intervals: dict[str, list[list[str]]] | None = None,
) -> dict[str, float] | None:
    try:
        factor_values = run_signal_code_panel(code, panel)
        return run_cross_sectional_backtest(
            panel,
            None,
            n_groups=n_groups,
            cost_bps=cost_bps,
            membership_intervals=membership_intervals,
            factor_values=factor_values,
        ).metrics
    except Exception:
        return None
