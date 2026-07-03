from __future__ import annotations

from datetime import datetime, timedelta, timezone

import duckdb
import pandas as pd

from quantbench.config import MONITOR_REFRESH_LOOKBACK_DAYS
from quantbench.data.exchange import fetch_ohlcv
from quantbench.data.universe import UniverseDefinition
from quantbench.data.warehouse import fetch_universe_ohlcv, get_connection, upsert_ohlcv


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def refresh_symbol(
    symbol: str,
    timeframe: str,
    start: str | None = None,
    lookback_days: int = MONITOR_REFRESH_LOOKBACK_DAYS,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> dict:
    """Re-fetch a symbol's data from `start` (or, if not given, the last
    `lookback_days`) through today and upsert into the DuckDB warehouse.

    Callers checking decay since a run's own data cutoff must pass that
    cutoff as `start` (with a small buffer) - a run whose data ends months
    ago would otherwise only get the last `lookback_days` refreshed, leaving
    a silent gap between the cutoff and that fixed window while
    check_run_decay's "since creation" framing claimed full coverage.
    `lookback_days` alone remains the default for standalone/ad-hoc use.

    The overlap/buffer (rather than fetching strictly "since last known
    bar") deliberately re-fetches a few already-known days too - providers
    sometimes revise a still-open/most-recent bar, and upsert_ohlcv is
    idempotent on (symbol, timestamp) so the overlap costs nothing but a
    slightly larger fetch.
    """
    own_conn = conn is None
    conn = conn or get_connection()
    if start is None:
        start = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end = _today_utc()
    _, df, meta = fetch_ohlcv(symbol, timeframe, start, end)
    rows = upsert_ohlcv(conn, symbol, df, provider=meta.get("provider"), source=meta.get("source"))
    if own_conn:
        conn.close()
    return {
        "symbol": symbol,
        "start": start,
        "end": end,
        "rows_upserted": rows,
        "source": meta.get("source"),
        "df": df,
    }


def refresh_universe(
    symbols: list[str],
    timeframe: str,
    asset_class: str = "equity",
    start: str | None = None,
    lookback_days: int = MONITOR_REFRESH_LOOKBACK_DAYS,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> dict:
    """Same idea as refresh_symbol (see its docstring for why `start` should
    be the run's own data cutoff, not just `lookback_days` back from today)
    but for a list of symbols, reusing fetch_universe_ohlcv (which already
    loops fetch+upsert per symbol)."""
    own_conn = conn is None
    conn = conn or get_connection()
    if start is None:
        start = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end = _today_utc()
    universe = UniverseDefinition(
        name="monitor_refresh",
        as_of_date=end,
        symbols=symbols,
        point_in_time=False,
        survivorship_bias_note="",
        source="monitor_refresh",
        asset_class=asset_class,
    )
    _, meta = fetch_universe_ohlcv(universe, timeframe, start, end, conn=conn)
    if own_conn:
        conn.close()
    return {"start": start, "end": end, **meta}


def recent_bars(
    symbols: list[str],
    since: pd.Timestamp,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> pd.DataFrame:
    """Warehouse rows strictly after `since`, across one or more symbols. Callers
    should refresh_symbol/refresh_universe first so the warehouse actually has
    anything past `since` to return."""
    from quantbench.data.warehouse import query_universe_ohlcv

    own_conn = conn is None
    conn = conn or get_connection()
    end = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    start = (since + pd.Timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")
    df = query_universe_ohlcv(conn, symbols, start, end)
    if own_conn:
        conn.close()
    return df
