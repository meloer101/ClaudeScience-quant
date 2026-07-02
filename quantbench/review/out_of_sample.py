from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd


@dataclass(frozen=True)
class OOSResult:
    train_metrics: dict[str, float]
    test_metrics: dict[str, float]
    train_observations: int
    test_observations: int
    sharpe_decay_ratio: float | None


def split_out_of_sample(price_or_panel: pd.DataFrame, split_ratio: float = 0.7) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = price_or_panel.copy()
    timestamps = pd.to_datetime(data["timestamp"], utc=True).dropna().sort_values().unique()
    if len(timestamps) < 2:
        return data.iloc[0:0].copy(), data.iloc[0:0].copy()
    split_at = max(1, min(len(timestamps) - 1, int(len(timestamps) * split_ratio)))
    train_ts = set(timestamps[:split_at])
    train = data[pd.to_datetime(data["timestamp"], utc=True).isin(train_ts)].copy()
    test = data[~pd.to_datetime(data["timestamp"], utc=True).isin(train_ts)].copy()
    return train, test


def run_out_of_sample_check(
    data: pd.DataFrame,
    run_on_data: Callable[[pd.DataFrame], dict[str, float]],
    split_ratio: float = 0.7,
) -> OOSResult:
    train, test = split_out_of_sample(data, split_ratio=split_ratio)
    train_metrics = run_on_data(train) if len(train) else {}
    test_metrics = run_on_data(test) if len(test) else {}
    train_sharpe = float(train_metrics.get("sharpe", 0.0) or 0.0)
    test_sharpe = float(test_metrics.get("sharpe", 0.0) or 0.0)
    if train_sharpe <= 0 or test_sharpe * train_sharpe < 0:
        ratio = None
    else:
        ratio = test_sharpe / train_sharpe if train_sharpe else None
    return OOSResult(
        train_metrics=train_metrics,
        test_metrics=test_metrics,
        train_observations=len(train),
        test_observations=len(test),
        sharpe_decay_ratio=ratio,
    )
