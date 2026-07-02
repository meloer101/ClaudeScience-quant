from __future__ import annotations

import numpy as np
import pandas as pd


def compute_beta(strategy_returns: pd.Series, benchmark_returns: pd.Series) -> tuple[float, float, int]:
    joined = (
        pd.concat(
            [
                strategy_returns.rename("strategy"),
                benchmark_returns.rename("benchmark"),
            ],
            axis=1,
            sort=False,
        )
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    if len(joined) < 2 or float(joined["benchmark"].var(ddof=0)) == 0:
        return 0.0, 0.0, len(joined)
    x = joined["benchmark"].astype(float).to_numpy()
    y = joined["strategy"].astype(float).to_numpy()
    x_mean = float(x.mean())
    y_mean = float(y.mean())
    beta = float(((x - x_mean) * (y - y_mean)).sum() / ((x - x_mean) ** 2).sum())
    fitted = y_mean + beta * (x - x_mean)
    ss_res = float(((y - fitted) ** 2).sum())
    ss_tot = float(((y - y_mean) ** 2).sum())
    r_squared = 0.0 if ss_tot == 0 else max(0.0, min(1.0, 1 - ss_res / ss_tot))
    return beta, r_squared, len(joined)
