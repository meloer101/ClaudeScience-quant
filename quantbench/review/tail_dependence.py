from __future__ import annotations

import pandas as pd


MAX_BEST_DAYS = 20


def best_days_contribution_share(returns: pd.Series, drop_frac: float = 0.05) -> float:
    """Share of total positive daily return contributed by the single best
    slice of days (5% of observations, capped at `MAX_BEST_DAYS`).

    Uses additive contribution share, not "recompound the series with the
    best days removed" - the latter looks intuitive but is a horizon
    artifact for multi-year daily series: compounding ~1500 daily returns
    with even a mildly negative post-trim mean decays to near -100%
    regardless of how good or bad the strategy actually is (verified against
    a pure random walk with a small positive drift and realistic daily vol -
    it also "fails" that test). Measuring what fraction of total positive
    return the top days account for is horizon-independent and mirrors the
    same additive-share pattern already used in symbol_concentration.py.

    The count is capped at `MAX_BEST_DAYS` rather than left as a pure 5%
    fraction: on long multi-year daily series, 5% is 60-75 days, which
    dilutes a handful of genuinely outsized outlier days among many
    ordinary ones and washes out exactly the concentration signal this
    check exists to catch (verified: a synthetic series with 5 dominant
    spike days out of 500 scored *lower* on uncapped 5% than a real,
    broad-based strategy's normal daily variation - capping restores the
    intended discrimination between "a few days explain everything" and
    "returns are broadly distributed").
    """
    clean = returns.dropna()
    if clean.empty:
        return 0.0
    total_positive = float(clean.clip(lower=0).sum())
    if total_positive <= 0:
        return 0.0
    drop_count = min(max(1, int(len(clean) * drop_frac)), MAX_BEST_DAYS)
    best_days_sum = float(clean.sort_values(ascending=False).iloc[:drop_count].clip(lower=0).sum())
    return best_days_sum / total_positive
