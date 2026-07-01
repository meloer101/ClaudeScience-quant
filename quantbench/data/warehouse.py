from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from quantbench.config import DATA_CACHE_DIR
from quantbench.data.exchange import fetch_ohlcv
from quantbench.data.universe import UniverseDefinition


OHLCV_TABLE = "ohlcv"


def get_connection(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    db_path = Path(db_path or DATA_CACHE_DIR / "quantbench.duckdb")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    ensure_schema(conn)
    return conn


def ensure_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {OHLCV_TABLE} (
            symbol VARCHAR NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume DOUBLE,
            provider VARCHAR,
            source VARCHAR,
            PRIMARY KEY (symbol, timestamp)
        )
        """
    )


def upsert_ohlcv(
    conn: duckdb.DuckDBPyConnection,
    symbol: str,
    df: pd.DataFrame,
    provider: str | None = None,
    source: str | None = None,
) -> int:
    ensure_schema(conn)
    if df.empty:
        return 0

    rows = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    rows["timestamp"] = pd.to_datetime(rows["timestamp"], utc=True)
    rows.insert(0, "symbol", symbol)
    rows["provider"] = provider
    rows["source"] = source

    conn.register("_incoming_ohlcv", rows)
    try:
        conn.execute(
            f"""
            INSERT OR REPLACE INTO {OHLCV_TABLE}
            SELECT symbol, timestamp, open, high, low, close, volume, provider, source
            FROM _incoming_ohlcv
            """
        )
    finally:
        conn.unregister("_incoming_ohlcv")
    return len(rows)


def query_universe_ohlcv(
    conn: duckdb.DuckDBPyConnection,
    symbols: list[str],
    start: str,
    end: str,
) -> pd.DataFrame:
    ensure_schema(conn)
    if not symbols:
        return pd.DataFrame(columns=["symbol", "timestamp", "open", "high", "low", "close", "volume"])

    query = f"""
        SELECT symbol, timestamp, open, high, low, close, volume
        FROM {OHLCV_TABLE}
        WHERE symbol IN (SELECT * FROM UNNEST(?))
          AND timestamp >= ?
          AND timestamp < ?
        ORDER BY timestamp, symbol
    """
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    return conn.execute(query, [symbols, start_ts, end_ts]).fetchdf()


def fetch_universe_ohlcv(
    universe: UniverseDefinition,
    timeframe: str,
    start: str,
    end: str,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> tuple[pd.DataFrame, dict]:
    own_conn = conn is None
    conn = conn or get_connection()
    cache_hits = 0
    fetched = 0
    failed: dict[str, str] = {}
    sources: dict[str, int] = {}

    for symbol in universe.symbols:
        try:
            _, df, meta = fetch_ohlcv(symbol, timeframe, start, end)
            upsert_ohlcv(conn, symbol, df, provider=meta.get("provider"), source=meta.get("source"))
            cache_hits += int(bool(meta.get("cache_hit")))
            fetched += 1
            source = str(meta.get("source", "unknown"))
            sources[source] = sources.get(source, 0) + 1
        except Exception as exc:
            failed[symbol] = f"{type(exc).__name__}: {exc}"

    panel = query_universe_ohlcv(conn, universe.symbols, start, end)
    if own_conn:
        conn.close()

    meta = {
        "symbols_requested": len(universe.symbols),
        "symbols_fetched": fetched,
        "cache_hits": cache_hits,
        "failed": failed,
        "sources": sources,
    }
    return panel, meta
