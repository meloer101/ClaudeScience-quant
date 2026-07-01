from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from quantbench.data.universe import UniverseDefinition


@dataclass
class DataQualityReport:
    total_symbols: int
    symbols_with_data: int
    symbols_missing_entirely: list[str]
    symbols_with_gaps: dict[str, int]
    symbols_delisted_or_dropped: list[str]
    suspicious_price_jumps: dict[str, list[str]]

    def to_dict(self) -> dict:
        return asdict(self)

    def summary_lines(self) -> list[str]:
        return [
            f"Total symbols: {self.total_symbols}",
            f"Symbols with data: {self.symbols_with_data}",
            f"Missing entirely: {len(self.symbols_missing_entirely)}",
            f"Symbols with calendar gaps: {len(self.symbols_with_gaps)}",
            f"Possible delisted/dropped symbols: {len(self.symbols_delisted_or_dropped)}",
            f"Symbols with >50% one-day price jumps: {len(self.suspicious_price_jumps)}",
        ]


def validate_universe_data(panel: pd.DataFrame, universe: UniverseDefinition, end: str | None = None) -> DataQualityReport:
    expected = set(universe.symbols)
    if panel.empty:
        return DataQualityReport(
            total_symbols=len(universe.symbols),
            symbols_with_data=0,
            symbols_missing_entirely=sorted(expected),
            symbols_with_gaps={},
            symbols_delisted_or_dropped=[],
            suspicious_price_jumps={},
        )

    data = panel.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True)
    present = set(data["symbol"].astype(str).unique())
    missing = sorted(expected.difference(present))
    symbols_with_gaps: dict[str, int] = {}
    dropped: list[str] = []
    suspicious: dict[str, list[str]] = {}
    end_ts = pd.to_datetime(end, utc=True) if end else data["timestamp"].max()

    for symbol, symbol_df in data.groupby("symbol"):
        symbol_df = symbol_df.sort_values("timestamp")
        dates = pd.DatetimeIndex(symbol_df["timestamp"].dt.normalize().unique())
        if len(dates) >= 2:
            expected_days = pd.bdate_range(dates.min(), dates.max(), tz="UTC")
            gaps = expected_days.difference(dates)
            if len(gaps):
                symbols_with_gaps[str(symbol)] = int(len(gaps))

        last_timestamp = symbol_df["timestamp"].max()
        if end_ts - last_timestamp > pd.Timedelta(days=10):
            dropped.append(str(symbol))

        jumps = symbol_df["close"].pct_change().abs()
        jump_dates = symbol_df.loc[jumps > 0.5, "timestamp"].dt.date.astype(str).tolist()
        if jump_dates:
            suspicious[str(symbol)] = jump_dates

    return DataQualityReport(
        total_symbols=len(universe.symbols),
        symbols_with_data=len(present.intersection(expected)),
        symbols_missing_entirely=missing,
        symbols_with_gaps=symbols_with_gaps,
        symbols_delisted_or_dropped=sorted(dropped),
        suspicious_price_jumps=suspicious,
    )
