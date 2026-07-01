import pandas as pd


def _panel() -> pd.DataFrame:
    timestamps = pd.date_range("2024-01-01", periods=5, freq="1D", tz="UTC")
    rows = []
    specs = {
        "WIN": [100, 100, 110, 121, 133.1],
        "MID": [100, 100, 101, 102.01, 103.03],
        "LOS": [100, 100, 90, 81, 72.9],
    }
    for symbol, closes in specs.items():
        for timestamp, close in zip(timestamps, closes, strict=True):
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": timestamp,
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "volume": 1000,
                }
            )
    return pd.DataFrame(rows)


def test_cross_sectional_backtest_uses_factor_for_next_period_returns():
    from quantbench.engine.cross_sectional_backtest import run_cross_sectional_backtest

    def compute(df):
        scores = {"WIN": 3.0, "MID": 2.0, "LOS": 1.0}
        return pd.Series(scores[df["symbol"].iloc[0]], index=df.index)

    result = run_cross_sectional_backtest(_panel(), compute, n_groups=3, cost_bps=0)

    assert result.returns.iloc[0] == 0
    assert round(result.returns.iloc[1], 6) == 0.2
    assert result.metrics["rank_ic_mean"] > 0
    assert result.metrics["monotonicity_score"] == 1.0
    assert result.metrics["symbols"] == 3


def test_data_quality_reports_missing_gaps_drops_and_jumps():
    from quantbench.data.universe import UniverseDefinition
    from quantbench.skills.data_quality import validate_universe_data

    universe = UniverseDefinition(
        name="test",
        as_of_date="2024-01-10",
        symbols=["AAA", "BBB", "CCC"],
        point_in_time=False,
        survivorship_bias_note="biased",
        source="unit",
    )
    panel = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "BBB", "BBB"],
            "timestamp": pd.to_datetime(["2024-01-01", "2024-01-03", "2024-01-01", "2024-01-02"], utc=True),
            "open": [10, 30, 10, 10],
            "high": [10, 30, 10, 10],
            "low": [10, 30, 10, 10],
            "close": [10, 30, 10, 10],
            "volume": [1, 1, 1, 1],
        }
    )

    report = validate_universe_data(panel, universe, end="2024-01-20")

    assert report.symbols_missing_entirely == ["CCC"]
    assert report.symbols_with_gaps["AAA"] == 1
    assert "AAA" in report.symbols_delisted_or_dropped
    assert report.suspicious_price_jumps["AAA"] == ["2024-01-03"]
