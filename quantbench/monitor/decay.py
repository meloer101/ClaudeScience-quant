from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from quantbench.config import (
    MONITOR_MIN_OBSERVATIONS,
    MONITOR_SHARPE_ALERT_RATIO,
    MONITOR_SHARPE_WATCH_RATIO,
)
from quantbench.engine.metrics import annualized_sharpe, compute_drawdown, periods_per_year_from_timestamps

STATUS_OK = "ok"
STATUS_WATCH = "watch"
STATUS_ALERT = "alert"
STATUS_INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class DecayReport:
    status: str
    checked_at: str
    since_timestamp: str
    original_sharpe: float
    recent_sharpe: float | None
    sharpe_decay_ratio: float | None
    recent_observations: int
    recent_max_drawdown: float | None
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_decay_report(
    original_sharpe: float,
    recent_returns: pd.Series,
    since_timestamp: Any,
) -> DecayReport:
    """Compares a run's recorded backtest Sharpe to the Sharpe realized on
    data observed since the run's data cutoff. Uses the same decay-ratio
    thresholds as review/report.py's out-of-sample check (<0.5 -> alert,
    <0.8 -> watch) so "decayed since creation" and "decayed train->test"
    mean the same thing across the codebase.

    Deliberately refuses to compute a ratio on too few observations
    (MONITOR_MIN_OBSERVATIONS) - a Sharpe computed from a handful of days is
    not a meaningful comparison point and reporting one anyway would look
    precise while being statistically empty.
    """
    checked_at = datetime.now(timezone.utc).isoformat()
    clean = recent_returns.dropna()
    n = len(clean)

    if n < MONITOR_MIN_OBSERVATIONS:
        return DecayReport(
            status=STATUS_INSUFFICIENT_DATA,
            checked_at=checked_at,
            since_timestamp=str(since_timestamp),
            original_sharpe=original_sharpe,
            recent_sharpe=None,
            sharpe_decay_ratio=None,
            recent_observations=n,
            recent_max_drawdown=None,
            detail=(
                f"Only {n} observation(s) since {since_timestamp} - need at least "
                f"{MONITOR_MIN_OBSERVATIONS} before a recent Sharpe is meaningful."
            ),
        )

    ppy = periods_per_year_from_timestamps(clean.index)
    recent_sharpe = annualized_sharpe(clean, ppy)
    equity_curve = (1 + clean).cumprod()
    recent_drawdown = float(compute_drawdown(equity_curve).min())

    # A positive-Sharpe strategy whose recent Sharpe has flipped negative is
    # worse than a >50% decay (dividing the two would even give a negative
    # ratio, i.e. "beyond alert" on the ratio scale) - it must not be
    # downgraded to a mere STATUS_WATCH just because dividing two
    # opposite-signed numbers isn't meaningful. Only an already-unprofitable
    # original Sharpe (<=0) falls back to an unscored "flag for review" -
    # there the direction of change isn't a decay-from-good story to begin
    # with, so no ratio-based status applies.
    if original_sharpe > 0 and recent_sharpe < 0:
        ratio = None
        status = STATUS_ALERT
        detail = (
            f"Recent Sharpe {recent_sharpe:.2f} has turned negative from a positive original "
            f"Sharpe {original_sharpe:.2f} - this is worse than a >50% decay, not a borderline case."
        )
    elif original_sharpe <= 0:
        ratio = None
        status = STATUS_WATCH
        detail = (
            f"Original Sharpe {original_sharpe:.2f} was non-positive - decay ratio is not "
            "meaningful, flagging for review."
        )
    else:
        ratio = recent_sharpe / original_sharpe
        if ratio < MONITOR_SHARPE_ALERT_RATIO:
            status = STATUS_ALERT
            detail = f"Recent Sharpe {recent_sharpe:.2f} is {ratio:.0%} of original {original_sharpe:.2f} - significant decay."
        elif ratio < MONITOR_SHARPE_WATCH_RATIO:
            status = STATUS_WATCH
            detail = f"Recent Sharpe {recent_sharpe:.2f} is {ratio:.0%} of original {original_sharpe:.2f} - some decay."
        else:
            status = STATUS_OK
            detail = f"Recent Sharpe {recent_sharpe:.2f} is {ratio:.0%} of original {original_sharpe:.2f}."

    return DecayReport(
        status=status,
        checked_at=checked_at,
        since_timestamp=str(since_timestamp),
        original_sharpe=original_sharpe,
        recent_sharpe=round(float(recent_sharpe), 6),
        sharpe_decay_ratio=round(float(ratio), 6) if ratio is not None else None,
        recent_observations=n,
        recent_max_drawdown=round(recent_drawdown, 6),
        detail=detail,
    )
