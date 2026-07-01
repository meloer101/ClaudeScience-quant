from __future__ import annotations

import pandas as pd


WIKIPEDIA_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def fetch_current_constituents() -> pd.DataFrame:
    """Fetch the current S&P 500 constituents from Wikipedia.

    Wikipedia tickers use dots for share classes (BRK.B). yfinance expects
    dashes (BRK-B), so normalize symbols before returning.
    """
    tables = pd.read_html(WIKIPEDIA_SP500_URL)
    if not tables:
        raise ValueError("Wikipedia returned no tables for S&P 500 constituents")

    table = tables[0].copy()
    required = {"Symbol", "Security"}
    missing = required.difference(table.columns)
    if missing:
        raise ValueError(f"S&P 500 table missing required columns: {sorted(missing)}")

    table["Symbol"] = table["Symbol"].astype(str).str.replace(".", "-", regex=False).str.strip()
    table["Security"] = table["Security"].astype(str).str.strip()
    return table
