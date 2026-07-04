import time

import pandas as pd
import pytest


def _sample_df(n=20):
    return pd.DataFrame({"close": [float(i) for i in range(n)]})


def _sample_panel() -> pd.DataFrame:
    rows = []
    for symbol, offset in (("AAA", 0.0), ("BBB", 10.0), ("CCC", 20.0)):
        for day in range(5):
            rows.append(
                {
                    "timestamp": f"2024-01-{day + 1:02d}",
                    "symbol": symbol,
                    "open": offset + day + 0.5,
                    "close": offset + day + 1.0,
                    "volume": 1000 + day,
                }
            )
    return pd.DataFrame(rows)


def _probe_rlimit_as(queue) -> None:
    import resource

    try:
        resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024))
        queue.put(True)
    except (ValueError, OSError):
        queue.put(False)


def _rlimit_as_is_enforceable() -> bool:
    """RLIMIT_AS is unenforceable on macOS/Darwin - setrlimit to any finite
    value fails with EINVAL there even though the constant is defined and
    getrlimit reports the current limit as unlimited. Probed in a throwaway
    subprocess (not this test process) so the probe itself can't leave the
    real limit lowered for the rest of the run."""
    import multiprocessing as mp

    ctx = mp.get_context("spawn")
    queue = ctx.Queue()
    process = ctx.Process(target=_probe_rlimit_as, args=(queue,))
    process.start()
    process.join(5.0)
    return queue.get() if not queue.empty() else False


def test_run_signal_code_matches_unsandboxed_execution_for_well_behaved_code():
    from quantbench.skills.codeexec import _execute_signal_code, run_signal_code

    code = "def compute(df):\n    return df['close'] * 2.0\n"
    df = _sample_df()

    sandboxed = run_signal_code(code, df)
    unsandboxed = _execute_signal_code(code, df)

    pd.testing.assert_series_equal(sandboxed, unsandboxed)


def test_run_signal_code_keeps_two_positional_argument_signature():
    from quantbench.skills.codeexec import run_signal_code

    code = "def compute(df):\n    return df['close']\n"
    result = run_signal_code(code, _sample_df())
    assert isinstance(result, pd.Series)


def test_run_signal_code_still_blocks_open_builtin():
    from quantbench.skills.codeexec import run_signal_code

    code = "def compute(df):\n    open('/tmp/should-not-exist', 'w')\n    return df['close']\n"
    with pytest.raises(NameError, match="open"):
        run_signal_code(code, _sample_df())


def test_run_signal_code_infinite_loop_hits_cpu_limit():
    from quantbench.skills.codeexec import run_signal_code
    from quantbench.skills.sandbox import SandboxConfig, SandboxError

    code = "def compute(df):\n    while True:\n        pass\n"
    tight_config = SandboxConfig(cpu_seconds=1, mem_mb=512, wall_timeout_s=5.0)

    started = time.monotonic()
    with pytest.raises(SandboxError):
        run_signal_code(code, _sample_df(), sandbox=tight_config)
    elapsed = time.monotonic() - started

    assert elapsed < tight_config.wall_timeout_s + 2.0


@pytest.mark.skipif(
    not _rlimit_as_is_enforceable(),
    reason="RLIMIT_AS is not enforceable on this platform (known macOS/Darwin limitation - "
    "setrlimit(RLIMIT_AS, ...) fails with EINVAL there even for a finite, lowered value). "
    "The sandbox degrades gracefully (CPU limit + wall-clock backstop still apply) but "
    "cannot bound memory on such platforms without a heavier isolation mechanism (e.g. "
    "cgroups on Linux, which PHASE13 explicitly defers rather than adding Docker for).",
)
def test_run_signal_code_memory_bomb_hits_address_space_limit():
    from quantbench.skills.codeexec import run_signal_code
    from quantbench.skills.sandbox import SandboxConfig, SandboxError

    code = "def compute(df):\n    np.zeros((400_000_000,), dtype='float64')\n    return df['close']\n"
    tight_config = SandboxConfig(cpu_seconds=5, mem_mb=200, wall_timeout_s=10.0)

    with pytest.raises(SandboxError):
        run_signal_code(code, _sample_df(), sandbox=tight_config)


def test_run_signal_code_wall_clock_backstop_fires_before_a_looser_cpu_limit():
    from quantbench.skills.codeexec import run_signal_code
    from quantbench.skills.sandbox import SandboxConfig, SandboxError

    # cpu_seconds is intentionally looser than wall_timeout_s here, so this
    # only passes if the parent's own wall-clock join(timeout) is doing real
    # work rather than just waiting on RLIMIT_CPU to fire.
    code = "def compute(df):\n    while True:\n        pass\n"
    tight_config = SandboxConfig(cpu_seconds=30, mem_mb=512, wall_timeout_s=1.5)

    started = time.monotonic()
    with pytest.raises(SandboxError, match="timeout"):
        run_signal_code(code, _sample_df(), sandbox=tight_config)
    elapsed = time.monotonic() - started

    assert elapsed < tight_config.wall_timeout_s + 3.0


def test_run_signal_code_panel_matches_unsandboxed_groupby_execution():
    from quantbench.skills.codeexec import _execute_signal_code_panel, run_signal_code_panel

    code = "def compute(df):\n    return df['close'].pct_change().fillna(0)\n"
    panel = _sample_panel()

    sandboxed = run_signal_code_panel(code, panel)
    unsandboxed = _execute_signal_code_panel(code, panel)

    pd.testing.assert_frame_equal(sandboxed, unsandboxed)
    assert list(sandboxed.columns) == ["timestamp", "symbol", "factor"]
    assert len(sandboxed) == len(panel)


def test_run_signal_code_panel_does_not_deadlock_on_large_result():
    """Regression: a factor panel larger than the OS pipe buffer (~64KB pickled)
    used to deadlock. The child couldn't terminate until the parent drained its
    result, but the parent was blocked in join() waiting for the child to exit -
    so the run hung until the wall-clock backstop fired (~120s). Small test
    panels fit under the buffer and hid this; every realistic multi-symbol /
    multi-year cross-sectional backtest hit it. 40 symbols x ~2 years is well
    over the buffer and must complete near-instantly, not near the timeout.

    Uses a generous wall_timeout so a genuinely deadlocked implementation still
    surfaces (it would raise SandboxError), but a healthy one returns in well
    under a second."""
    from quantbench.skills.codeexec import run_signal_code_panel
    from quantbench.skills.sandbox import SandboxConfig

    dates = pd.bdate_range("2021-01-01", periods=520)
    frames = []
    for i in range(40):
        frames.append(
            pd.DataFrame(
                {
                    "timestamp": dates,
                    "symbol": f"S{i:02d}",
                    "open": 100.0,
                    "high": 100.0,
                    "low": 100.0,
                    "close": [100.0 + j * 0.1 for j in range(len(dates))],
                    "volume": 1_000_000.0,
                }
            )
        )
    panel = pd.concat(frames, ignore_index=True)
    assert len(panel) > 20_000  # comfortably over the ~64KB pipe buffer once pickled

    code = "def compute(df):\n    return df['close'].pct_change().fillna(0.0)\n"
    started = time.perf_counter()
    result = run_signal_code_panel(code, panel, sandbox=SandboxConfig(cpu_seconds=60, wall_timeout_s=30.0))
    elapsed = time.perf_counter() - started

    assert len(result) == len(panel)
    assert elapsed < 15.0  # a deadlocked impl would only escape at the 30s wall backstop


def test_cross_sectional_backtest_accepts_precomputed_factor_values():
    from quantbench.engine.cross_sectional_backtest import run_cross_sectional_backtest
    from quantbench.skills.codeexec import _execute_signal_code_panel, load_signal_function

    code = "def compute(df):\n    return df['close'].pct_change().fillna(0)\n"
    panel = _sample_panel()
    compute = load_signal_function(code)
    factor_values = _execute_signal_code_panel(code, panel)

    direct = run_cross_sectional_backtest(panel, compute, n_groups=3, cost_bps=0)
    precomputed = run_cross_sectional_backtest(panel, None, n_groups=3, cost_bps=0, factor_values=factor_values)

    assert precomputed.metrics == direct.metrics
    pd.testing.assert_frame_equal(precomputed.factor_panel, direct.factor_panel)


def test_run_in_sandbox_records_usage_metadata():
    from quantbench.skills.sandbox import SandboxConfig, run_in_sandbox
    from quantbench.skills.codeexec import _execute_signal_code

    usage = []
    result = run_in_sandbox(
        _execute_signal_code,
        "def compute(df):\n    return df['close']\n",
        _sample_df(3),
        config=SandboxConfig(cpu_seconds=2, mem_mb=256, wall_timeout_s=5.0),
        usage_sink=usage,
    )

    pd.testing.assert_series_equal(result, _sample_df(3)["close"])
    assert len(usage) == 1
    assert usage[0].wall_seconds >= 0
    assert usage[0].exitcode == 0
    assert usage[0].limits["cpu_seconds"] == 2
    assert usage[0].max_rss_bytes >= 0
