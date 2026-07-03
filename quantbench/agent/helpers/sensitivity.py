from collections.abc import Callable
from typing import Any

import pandas as pd

from quantbench.engine.costs import LiquidityCostConfig
from quantbench.engine.cross_sectional_backtest import run_cross_sectional_backtest
from quantbench.engine.execution import ExecutionConfig


def _cross_execution_sensitivity(
    panel: pd.DataFrame,
    compute: Callable[[pd.DataFrame], pd.Series],
    n_groups: int,
    cost_bps: float,
    membership_intervals: dict[str, list[list[str]]] | None,
    funding_rates: pd.DataFrame | None,
    liquidity_config: LiquidityCostConfig | None,
    borrow_rates: pd.DataFrame | None,
    neutralize_dims: list[str],
    sector: pd.Series | None,
) -> dict[str, Any] | None:
    if "open" not in panel.columns:
        return None
    close_metrics = run_cross_sectional_backtest(
        panel,
        compute,
        n_groups=n_groups,
        cost_bps=cost_bps,
        membership_intervals=membership_intervals,
        funding_rates=funding_rates,
        execution=ExecutionConfig(fill_price="close_t"),
        liquidity_cost_config=liquidity_config,
        borrow_rates=borrow_rates,
        neutralize=neutralize_dims,
        sector=sector,
    ).metrics
    open_next_metrics = run_cross_sectional_backtest(
        panel,
        compute,
        n_groups=n_groups,
        cost_bps=cost_bps,
        membership_intervals=membership_intervals,
        funding_rates=funding_rates,
        execution=ExecutionConfig(fill_price="open_t+1"),
        liquidity_cost_config=liquidity_config,
        borrow_rates=borrow_rates,
        neutralize=neutralize_dims,
        sector=sector,
    ).metrics
    return {
        "close_t_sharpe": close_metrics.get("sharpe"),
        "open_t+1_sharpe": open_next_metrics.get("sharpe"),
    }


def _metrics_without_borrow(
    panel: pd.DataFrame,
    compute: Callable[[pd.DataFrame], pd.Series],
    n_groups: int,
    cost_bps: float,
    membership_intervals: dict[str, list[list[str]]] | None,
    funding_rates: pd.DataFrame | None,
    execution: ExecutionConfig,
    liquidity_config: LiquidityCostConfig | None,
    neutralize_dims: list[str],
    sector: pd.Series | None,
) -> dict[str, float]:
    return run_cross_sectional_backtest(
        panel,
        compute,
        n_groups=n_groups,
        cost_bps=cost_bps,
        membership_intervals=membership_intervals,
        funding_rates=funding_rates,
        execution=execution,
        liquidity_cost_config=liquidity_config,
        neutralize=neutralize_dims,
        sector=sector,
    ).metrics


def _neutralization_comparison(
    panel: pd.DataFrame,
    compute: Callable[[pd.DataFrame], pd.Series],
    n_groups: int,
    cost_bps: float,
    membership_intervals: dict[str, list[list[str]]] | None,
    funding_rates: pd.DataFrame | None,
    execution: ExecutionConfig,
    liquidity_config: LiquidityCostConfig | None,
    borrow_rates: pd.DataFrame | None,
    neutralize_dims: list[str],
    sector: pd.Series | None,
) -> dict[str, Any]:
    if not neutralize_dims:
        return {}
    raw = run_cross_sectional_backtest(
        panel,
        compute,
        n_groups=n_groups,
        cost_bps=cost_bps,
        membership_intervals=membership_intervals,
        funding_rates=funding_rates,
        execution=execution,
        liquidity_cost_config=liquidity_config,
        borrow_rates=borrow_rates,
    )
    neutralized = run_cross_sectional_backtest(
        panel,
        compute,
        n_groups=n_groups,
        cost_bps=cost_bps,
        membership_intervals=membership_intervals,
        funding_rates=funding_rates,
        execution=execution,
        liquidity_cost_config=liquidity_config,
        borrow_rates=borrow_rates,
        neutralize=neutralize_dims,
        sector=sector,
    )
    return {
        "dimensions": ",".join(neutralize_dims),
        "raw_sharpe": raw.metrics.get("sharpe"),
        "neutralized_sharpe": neutralized.metrics.get("sharpe"),
        "raw_rank_ic_mean": raw.metrics.get("rank_ic_mean"),
        "neutralized_rank_ic_mean": neutralized.metrics.get("rank_ic_mean"),
    }
