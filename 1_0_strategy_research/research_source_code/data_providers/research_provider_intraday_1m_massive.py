"""
research_provider_intraday_1m_massive.py
Track: intraday_same_day
Side: research - data provider layer

Purpose:
  Thin fetch-only wrapper around the Massive.com data API.
  Returns 1-minute OHLCV bars for a single ticker over a date range.
  No cache logic lives here. This module only fetches.

Public interface:
  normalize_aggs(aggs)                      -> pd.DataFrame | None
  fetch_intraday_1m(ticker, start, end)     -> pd.DataFrame | None

Output contract:
  - DatetimeIndex in America/New_York timezone
  - Columns (lowercase): open, high, low, close, volume
  - Sorted ascending by timestamp
  - Returns None on fetch failure (caller decides how to handle)

Auth:
  Reads MASSIVE_API_KEY from the environment.
  Set it before running any cache builder:
    export MASSIVE_API_KEY=<your_key>   (Linux/macOS)
    set MASSIVE_API_KEY=<your_key>      (Windows cmd)
    $env:MASSIVE_API_KEY="<your_key>"   (Windows PowerShell)

  If the key is not set, fetch_intraday_1m raises EnvironmentError immediately.

Dependencies:
  pip install -U massive pandas pyarrow
"""

import os
import datetime
import pandas as pd
from massive import RESTClient

_MASSIVE_API_KEY_ENV = "MASSIVE_API_KEY"


def _get_api_key() -> str:
    key = os.environ.get(_MASSIVE_API_KEY_ENV, "").strip()
    if not key:
        raise EnvironmentError(
            f"MASSIVE_API_KEY is not set. "
            f"Set the environment variable before running the cache builder.\n"
            f"  export {_MASSIVE_API_KEY_ENV}=<your_key>"
        )
    return key


def normalize_aggs(aggs: list) -> pd.DataFrame | None:
    """
    Convert a list of Massive Agg objects to the project output contract.
    Shared by all cache builders that call the Massive API directly.
    Fields used: timestamp (ms UTC), open, high, low, close, volume.
    """
    if not aggs:
        return None
    records = [
        {
            "timestamp": a.timestamp,
            "open":   a.open,
            "high":   a.high,
            "low":    a.low,
            "close":  a.close,
            "volume": a.volume,
        }
        for a in aggs
    ]
    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp")
    df.index = df.index.tz_convert("America/New_York")
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df[["open", "high", "low", "close", "volume"]]


def fetch_intraday_1m(
    ticker: str,
    start_date: datetime.date,
    end_date: datetime.date,
    client: RESTClient | None = None,
) -> pd.DataFrame | None:
    """
    Fetch 1-minute OHLCV bars from Massive.com for a single ticker.

    Parameters
    ----------
    ticker     : str                  - uppercase ticker symbol, e.g. "AAPL"
    start_date : datetime.date        - inclusive start
    end_date   : datetime.date        - inclusive end
    client     : RESTClient | None    - pass a shared client to avoid per-call construction

    Returns None on any fetch error (error is printed).
    Raises EnvironmentError if MASSIVE_API_KEY is not set and no client is provided.
    """
    if client is None:
        client = RESTClient(api_key=_get_api_key())

    try:
        aggs = list(
            client.list_aggs(
                ticker=ticker,
                multiplier=1,
                timespan="minute",
                from_=start_date.isoformat(),
                to=end_date.isoformat(),
                limit=50000,
            )
        )
        df = normalize_aggs(aggs)
        if df is None or df.empty:
            print(f"  {ticker}: no data returned from Massive")
            return None
        return df

    except Exception as exc:
        print(f"  {ticker}: fetch_intraday_1m ERROR - {exc}")
        return None
