from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class FundingPeriodSeries:
    cost: pd.Series
    coverage: dict[str, Any]


def funding_cost_by_period(weights: pd.DataFrame, funding_rates: pd.DataFrame | None) -> FundingPeriodSeries:
    """Return signed funding carry by rebalance period.

    Funding rows are assigned to the holding interval [weight_timestamp, next_weight_timestamp).
    Positive weight * positive funding is a cost; negative weight * positive funding is a rebate.
    """
    if weights.empty:
        return FundingPeriodSeries(pd.Series(dtype="float64", index=weights.index), _empty_coverage(weights))
    if funding_rates is None or funding_rates.empty:
        return FundingPeriodSeries(pd.Series(0.0, index=weights.index), _empty_coverage(weights))

    required = {"timestamp", "symbol", "funding_rate"}
    missing = required - set(funding_rates.columns)
    if missing:
        raise ValueError("funding_rates must contain timestamp, symbol, and funding_rate columns")

    normalized = funding_rates.loc[:, ["timestamp", "symbol", "funding_rate"]].copy()
    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], utc=True)
    normalized["symbol"] = normalized["symbol"].astype(str)
    normalized["funding_rate"] = pd.to_numeric(normalized["funding_rate"], errors="coerce")
    normalized = normalized.dropna(subset=["timestamp", "symbol", "funding_rate"]).sort_values("timestamp")

    index = pd.DatetimeIndex(pd.to_datetime(weights.index, utc=True))
    columns = [str(column) for column in weights.columns]
    safe_weights = weights.copy()
    safe_weights.index = index
    safe_weights.columns = columns

    if len(index) >= 2:
        period_delta = pd.Series(index[1:] - index[:-1]).median()
    else:
        period_delta = pd.Timedelta(days=1)

    values: dict[pd.Timestamp, float] = {}
    observed_pairs: set[tuple[pd.Timestamp, str]] = set()
    aligned_rows = 0

    for position, start in enumerate(index):
        end = index[position + 1] if position + 1 < len(index) else start + period_delta
        window = normalized[(normalized["timestamp"] >= start) & (normalized["timestamp"] < end)]
        if window.empty:
            values[start] = 0.0
            continue
        period_rates = window.pivot_table(columns="symbol", values="funding_rate", aggfunc="sum").reindex(columns=columns, fill_value=0)
        row = period_rates.iloc[0]
        values[start] = float((safe_weights.loc[start] * row).sum())
        aligned_rows += len(window)
        for symbol in set(window["symbol"].astype(str)) & set(columns):
            observed_pairs.add((start, symbol))

    expected_pairs = len(index) * len(columns)
    missing_pairs = max(expected_pairs - len(observed_pairs), 0)
    coverage = {
        "raw_rows": int(len(normalized)),
        "aligned_rows": int(aligned_rows),
        "expected_period_symbol_pairs": int(expected_pairs),
        "observed_period_symbol_pairs": int(len(observed_pairs)),
        "missing_period_symbol_pairs": int(missing_pairs),
        "coverage_ratio": round(len(observed_pairs) / expected_pairs, 6) if expected_pairs else 1.0,
    }
    return FundingPeriodSeries(pd.Series(values).reindex(index).fillna(0.0), coverage)


def _empty_coverage(weights: pd.DataFrame) -> dict[str, Any]:
    expected_pairs = len(weights.index) * len(weights.columns)
    return {
        "raw_rows": 0,
        "aligned_rows": 0,
        "expected_period_symbol_pairs": int(expected_pairs),
        "observed_period_symbol_pairs": 0,
        "missing_period_symbol_pairs": int(expected_pairs),
        "coverage_ratio": 0.0 if expected_pairs else 1.0,
    }
