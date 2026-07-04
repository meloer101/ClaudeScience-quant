import builtins

import numpy as np
import pandas as pd

from quantbench.config import SANDBOX_PANEL_CPU_SECONDS, SANDBOX_PANEL_WALL_TIMEOUT_S
from quantbench.skills.sandbox import SandboxConfig, SandboxUsage, run_in_sandbox

# Basic signal-code sandboxing: block the builtins that would let generated signal code
# reach outside pandas/numpy (filesystem, imports, nested eval). Combined with the
# process-level isolation in quantbench.skills.sandbox (CPU/memory/wall-clock rlimits),
# this is both an import whitelist/builtin denylist AND a resource-bounded subprocess -
# a runaway or malicious compute() can no longer stall or OOM the coordinator process.
_BLOCKED_BUILTINS = {"eval", "exec", "open", "__import__", "compile", "input", "exit", "quit", "breakpoint"}
_SAFE_BUILTINS = {name: getattr(builtins, name) for name in dir(builtins) if name not in _BLOCKED_BUILTINS}


def run_signal_code(
    code: str,
    data_df: pd.DataFrame,
    *,
    sandbox: SandboxConfig | None = None,
    usage_sink: list[SandboxUsage] | None = None,
) -> pd.Series:
    """Execute model-generated signal code in a resource-bounded child process
    and return the resulting series.

    `code` must define `compute(df: pd.DataFrame) -> pd.Series`. Only `pd` and
    `np` are available in scope; imports are disabled. `sandbox` overrides the
    default CPU/memory/wall-clock limits (quantbench.config.SANDBOX_*); pass it
    when a caller legitimately needs more headroom than the conservative
    defaults. Raises SandboxError (a RuntimeError) on a resource-limit breach,
    or ValueError for ordinary code/shape errors - both are plain exceptions,
    so existing callers that catch Exception around this call see no change.
    """
    return run_in_sandbox(_execute_signal_code, code, data_df, config=sandbox, usage_sink=usage_sink)


def run_signal_code_panel(
    code: str,
    panel: pd.DataFrame,
    *,
    sandbox: SandboxConfig | None = None,
    usage_sink: list[SandboxUsage] | None = None,
) -> pd.DataFrame:
    """Execute `compute(df)` once inside a sandboxed child for an entire
    cross-sectional panel, grouping by symbol in the child process.

    The returned DataFrame contains exactly timestamp, symbol, factor. The
    deterministic backtest engine joins this with prices/returns afterwards,
    keeping the sandbox boundary around generated model code only.
    """
    config = sandbox or SandboxConfig(
        cpu_seconds=SANDBOX_PANEL_CPU_SECONDS,
        wall_timeout_s=SANDBOX_PANEL_WALL_TIMEOUT_S,
    )
    return run_in_sandbox(_execute_signal_code_panel, code, panel, config=config, usage_sink=usage_sink)


def _execute_signal_code(code: str, data_df: pd.DataFrame) -> pd.Series:
    """The unsandboxed executor. Runs inside the sandboxed child process (see
    run_in_sandbox); do not call directly from coordinator/tool code - that
    would bypass the resource limits run_signal_code enforces."""
    compute = load_signal_function(code)
    result = compute(data_df)
    if not isinstance(result, pd.Series):
        raise ValueError(f"compute() must return a pandas Series, got {type(result).__name__}")
    if len(result) != len(data_df):
        raise ValueError(f"compute() returned {len(result)} rows, expected {len(data_df)}")
    return result


def _execute_signal_code_panel(code: str, panel: pd.DataFrame) -> pd.DataFrame:
    compute = load_signal_function(code)
    required = {"timestamp", "symbol"}
    missing = required - set(panel.columns)
    if missing:
        raise ValueError(f"panel is missing required column(s): {', '.join(sorted(missing))}")

    data = panel.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True)
    data = data.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    frames = []
    for symbol, symbol_df in data.groupby("symbol", sort=False):
        symbol_df = symbol_df.sort_values("timestamp").reset_index(drop=True)
        factor = compute(symbol_df)
        if not isinstance(factor, pd.Series):
            raise ValueError(f"compute() must return a pandas Series, got {type(factor).__name__}")
        if len(factor) != len(symbol_df):
            raise ValueError(f"compute() returned {len(factor)} rows for {symbol}, expected {len(symbol_df)}")
        frames.append(
            pd.DataFrame(
                {
                    "timestamp": symbol_df["timestamp"],
                    "symbol": symbol,
                    "factor": pd.Series(factor, index=symbol_df.index, dtype="float64"),
                }
            )
        )
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["timestamp", "symbol", "factor"])


def load_signal_function(code: str):
    namespace: dict = {"__builtins__": _SAFE_BUILTINS, "pd": pd, "np": np}
    try:
        exec(code, namespace)  # noqa: S102 - intentional, restricted namespace above
    except Exception as exc:
        raise ValueError(f"signal code failed to execute: {type(exc).__name__}: {exc}") from exc

    compute = namespace.get("compute")
    if not callable(compute):
        raise ValueError("signal code must define a function `compute(df) -> pd.Series`")
    return compute
