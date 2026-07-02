from __future__ import annotations

import numpy as np
import pandas as pd


def yearly_return_contribution(returns: pd.Series) -> dict[int, float]:
    clean = returns.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    if clean.empty:
        return {}
    dated = clean.copy()
    dated.index = pd.to_datetime(dated.index, utc=True)
    yearly_log = np.log1p(dated.clip(lower=-0.999999)).groupby(dated.index.year).sum()
    total_abs = float(yearly_log.abs().sum())
    if total_abs == 0:
        return {int(year): 0.0 for year in yearly_log.index}
    return {int(year): float(value / total_abs) for year, value in yearly_log.items()}
