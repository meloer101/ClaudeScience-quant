from __future__ import annotations

import numpy as np
import pandas as pd


def symbol_concentration_from_factor_panel(
    factor_panel: pd.DataFrame,
    n_groups: int,
    top_n: int = 5,
) -> tuple[float, dict[str, float]]:
    required = {"timestamp", "symbol", "group", "forward_return"}
    if factor_panel.empty or not required.issubset(factor_panel.columns):
        return 0.0, {}
    data = factor_panel.dropna(subset=["group", "forward_return"]).copy()
    if data.empty:
        return 0.0, {}
    data["group"] = data["group"].astype(int)
    legs = data[data["group"].isin([1, n_groups])].copy()
    if legs.empty:
        return 0.0, {}
    leg_sizes = legs.groupby(["timestamp", "group"], observed=True)["symbol"].transform("count").replace(0, np.nan)
    legs["side"] = np.where(legs["group"] == n_groups, 1.0, -1.0)
    legs["contribution"] = legs["side"] * legs["forward_return"].astype(float) / leg_sizes
    by_symbol = legs.groupby("symbol")["contribution"].sum().sort_values(key=lambda s: s.abs(), ascending=False)
    total_abs = float(by_symbol.abs().sum())
    if total_abs == 0:
        return 0.0, {}
    top_share = float(by_symbol.abs().head(top_n).sum() / total_abs)
    return top_share, {str(symbol): float(value) for symbol, value in by_symbol.head(top_n).items()}
