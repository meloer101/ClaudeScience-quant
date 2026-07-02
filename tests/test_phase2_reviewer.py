import json
from pathlib import Path

import numpy as np
import pandas as pd

from _fakes import FakeLLMClient


def _sample_ohlcv(rows: int = 160) -> pd.DataFrame:
    timestamp = pd.date_range("2022-01-01", periods=rows, freq="1D", tz="UTC")
    close = 100 + np.linspace(0, 30, rows) + np.sin(np.linspace(0, 20, rows)) * 3
    return pd.DataFrame(
        {
            "timestamp": timestamp,
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1000.0,
        }
    )


def test_lookahead_detects_negative_shift_and_verdict_rejects():
    from quantbench.review import determine_verdict
    from quantbench.review.lookahead import detect_lookahead
    from quantbench.review.report import ReviewFinding

    issues = detect_lookahead("def compute(df):\n    return df['close'].shift(-1)\n")

    assert any(issue.pattern == "negative_period" for issue in issues)
    verdict, _ = determine_verdict(
        [ReviewFinding("lookahead", "critical", issue.detail, {"pattern": issue.pattern}) for issue in issues]
    )
    assert verdict == "REJECTED"


def test_lookahead_does_not_flag_normal_rolling_momentum():
    from quantbench.review.lookahead import detect_lookahead

    code = "def compute(df):\n    return df['close'].pct_change(20).rolling(5).mean().fillna(0.0)\n"

    assert detect_lookahead(code) == []


def test_verdict_boundaries():
    from quantbench.review import determine_verdict
    from quantbench.review.report import ReviewFinding

    warning = ReviewFinding("x", "warning", "warn", {})
    critical = ReviewFinding("x", "critical", "crit", {})

    assert determine_verdict([critical])[0] == "REJECTED"
    assert determine_verdict([warning, warning, warning])[0] == "WEAK"
    assert determine_verdict([warning])[0] == "PROMISING"
    assert determine_verdict([ReviewFinding("x", "pass", "ok", {})])[0] == "STRONG"


def test_parameter_perturbation_uses_ast_not_comments_or_strings():
    from quantbench.review.parameter_stability import perturb_code

    code = "def compute(df):\n    label = '20'\n    # 20 in a comment\n    return df['close'].pct_change(20)\n"
    perturbed = perturb_code(code, 1.2)

    assert "'20'" in perturbed
    assert "pct_change(24)" in perturbed


def test_run_review_rejects_future_function():
    from quantbench.engine.vectorized_backtest import run_vectorized_backtest
    from quantbench.review import run_review
    from quantbench.skills.codeexec import run_signal_code

    df = _sample_ohlcv()
    code = "def compute(df):\n    return df['close'].shift(-1).fillna(df['close'])\n"
    signal = run_signal_code(code, df)
    result = run_vectorized_backtest(df, signal, cost_bps=0)

    report = run_review(
        code=code,
        returns=result.returns,
        cost_bps=0,
        rerun_at_cost=lambda bps: run_vectorized_backtest(df, signal, cost_bps=bps).metrics,
        rerun_with_code=lambda candidate: run_vectorized_backtest(df, run_signal_code(candidate, df), cost_bps=0).metrics,
        out_of_sample_data=df,
        run_on_data=lambda data: run_vectorized_backtest(data, run_signal_code(code, data), cost_bps=0).metrics,
        benchmark_returns=None,
        turnover_annual=result.metrics["turnover_annual"],
    )

    assert report.verdict == "REJECTED"
    assert any(finding.check == "lookahead" and finding.severity == "critical" for finding in report.findings)


def test_coordinator_writes_review_report_and_note(tmp_path: Path, monkeypatch):
    from quantbench.agent.coordinator import Coordinator
    from quantbench.artifact.store import ArtifactStore

    df = _sample_ohlcv()

    def fake_fetch_ohlcv(symbol, timeframe, start, end):
        return tmp_path / "data.parquet", df, {"source": "unit-test", "cache_hit": False}

    data_path = tmp_path / "data.parquet"
    df.to_parquet(data_path, index=False)
    monkeypatch.setattr("quantbench.agent.coordinator.fetch_ohlcv", fake_fetch_ohlcv)

    signal_code = "def compute(df):\n    return df['close'].pct_change(20).fillna(0.0)\n"
    script = [
        ("tools", [("fetch_ohlcv", {"symbol": "AAPL", "timeframe": "1d", "start": "2022-01-01", "end": "2022-06-30"})]),
        ("tools", [("run_signal_backtest", {"code": signal_code, "cost_bps": 5})]),
        ("text", "Verdict stated."),
    ]
    coordinator = Coordinator(run_store=ArtifactStore(tmp_path / "runs"), llm=FakeLLMClient(script))
    result = coordinator.run("测试20日动量因子")

    review_path = result.run_dir / "review_report.json"
    assert review_path.exists()
    review = json.loads(review_path.read_text(encoding="utf-8"))
    assert review["verdict"] in {"STRONG", "PROMISING", "WEAK", "REJECTED"}
    note = (result.run_dir / "research_note.md").read_text(encoding="utf-8")
    assert "## Reviewer 审查报告" in note
    manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["review"]["verdict"] == review["verdict"]
