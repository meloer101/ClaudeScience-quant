from typing import Any

import pandas as pd

from quantbench.data.universe import UniverseDefinition
from quantbench.engine.costs import BorrowCostConfig, LiquidityCostConfig, borrow_rates_from_dollar_volume
from quantbench.engine.execution import ExecutionConfig


def _execution_config(execution: dict[str, str] | ExecutionConfig | None) -> ExecutionConfig:
    if isinstance(execution, ExecutionConfig):
        return execution
    if not execution:
        return ExecutionConfig()
    return ExecutionConfig(
        signal_time=str(execution.get("signal_time") or "close_t"),
        fill_price=str(execution.get("fill_price") or "close_t"),
    )


def _liquidity_cost_config(config: dict[str, Any] | LiquidityCostConfig | None) -> LiquidityCostConfig | None:
    if isinstance(config, LiquidityCostConfig):
        return config
    if not config or not bool(config.get("enabled")):
        return None
    return LiquidityCostConfig(
        aum_usd=float(config.get("aum_usd") or 1_000_000),
        participation_cap=float(config.get("participation_cap") or 0.02),
    )


def _borrow_cost_config(config: dict[str, Any] | BorrowCostConfig | None) -> BorrowCostConfig:
    if isinstance(config, BorrowCostConfig):
        return config
    if not config or not bool(config.get("enabled")):
        return BorrowCostConfig(enabled=False)
    return BorrowCostConfig(enabled=True)


def _neutralize_dimensions(neutralize: list[str] | None) -> list[str]:
    allowed = {"beta", "size", "sector"}
    return [dim for dim in (neutralize or []) if dim in allowed]


def _sector_series(universe: UniverseDefinition | None) -> pd.Series | None:
    metadata = (universe.to_dict().get("metadata") if universe is not None else None) or {}
    sectors = metadata.get("gics_sector") if isinstance(metadata, dict) else None
    if not isinstance(sectors, dict) or not sectors:
        return None
    return pd.Series({str(symbol): str(sector) for symbol, sector in sectors.items()})


def _borrow_rates_for_panel(panel: pd.DataFrame, config: BorrowCostConfig) -> pd.DataFrame | None:
    if not config.enabled or panel.empty or not {"timestamp", "symbol", "close", "volume"}.issubset(panel.columns):
        return None
    data = panel.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True)
    data["dollar_volume"] = pd.to_numeric(data["close"], errors="coerce") * pd.to_numeric(data["volume"], errors="coerce")
    dollar_volume = data.pivot_table(index="timestamp", columns="symbol", values="dollar_volume", aggfunc="last").sort_index()
    return borrow_rates_from_dollar_volume(dollar_volume, config)
