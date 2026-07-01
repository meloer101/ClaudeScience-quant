from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from quantbench.data.providers.sp500_constituents import WIKIPEDIA_SP500_URL, fetch_current_constituents


SURVIVORSHIP_BIAS_NOTE = (
    "This universe uses the current S&P 500 constituents across the requested "
    "history. It is not point-in-time and therefore has survivorship bias: "
    "companies removed from the index before the as-of date are absent from "
    "the historical backtest sample."
)


@dataclass(frozen=True)
class UniverseDefinition:
    name: str
    as_of_date: str
    symbols: list[str]
    point_in_time: bool
    survivorship_bias_note: str
    source: str

    def to_dict(self) -> dict:
        return asdict(self)

    def save_yaml(self, path: Path) -> Path:
        path.write_text(yaml.safe_dump(self.to_dict(), sort_keys=False, allow_unicode=True), encoding="utf-8")
        return path


def build_sp500_universe(as_of_date: str, point_in_time: bool = False) -> UniverseDefinition:
    if point_in_time:
        raise NotImplementedError("Point-in-time S&P 500 membership is not implemented in Phase 1 v1")

    constituents = fetch_current_constituents()
    symbols = sorted(constituents["Symbol"].dropna().astype(str).unique().tolist())
    if len(symbols) < 400:
        raise ValueError(f"S&P 500 constituent parse returned too few symbols: {len(symbols)}")

    return UniverseDefinition(
        name="sp500",
        as_of_date=as_of_date,
        symbols=symbols,
        point_in_time=False,
        survivorship_bias_note=SURVIVORSHIP_BIAS_NOTE,
        source=WIKIPEDIA_SP500_URL,
    )


def build_universe(name: str, as_of_date: str, point_in_time: bool = False) -> UniverseDefinition:
    normalized = name.lower().replace("-", "").replace("_", "")
    if normalized in {"sp500", "s&p500", "sandp500"}:
        return build_sp500_universe(as_of_date=as_of_date, point_in_time=point_in_time)
    raise ValueError(f"Unsupported universe: {name}")
