from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


COST_MULTIPLIERS = (1.0, 1.5, 2.0)


@dataclass(frozen=True)
class CostSensitivityResult:
    sharpe_by_multiplier: dict[float, float]

    @property
    def unprofitable_at_2x(self) -> bool:
        return self.sharpe_by_multiplier.get(2.0, 0.0) <= 0


def run_cost_sensitivity_check(
    base_cost_bps: float,
    rerun_at_cost: Callable[[float], dict[str, float]],
) -> CostSensitivityResult:
    values: dict[float, float] = {}
    for multiplier in COST_MULTIPLIERS:
        metrics = rerun_at_cost(base_cost_bps * multiplier)
        values[multiplier] = float(metrics.get("sharpe", 0.0) or 0.0)
    return CostSensitivityResult(sharpe_by_multiplier=values)
