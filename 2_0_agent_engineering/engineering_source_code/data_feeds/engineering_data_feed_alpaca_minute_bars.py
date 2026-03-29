"""
engineering_data_feed_alpaca_minute_bars.py

Fetches 1-minute OHLCV bars from the Alpaca Data v2 REST API.

Returns Dict[str, pd.DataFrame] in the same format as the research parquet
cache so that the existing signal runner can consume it without modification.

Data format contract (matches engineering_signal_runner_intraday_same_day.py):
    Keys   : ticker symbol strings
    Values : DataFrame with DatetimeIndex (tz-aware, America/New_York)
             Index = bar OPEN time (Polygon.io convention)
             Columns : open, high, low, close, volume

API used:
    Alpaca Data v2 — multi-symbol historical bars
    GET /v2/stocks/bars
    Auth : APCA-API-KEY-ID / APCA-API-SECRET-KEY request headers

Pagination:
    Alpaca returns up to 10 000 bars per page. For one session (390 bars per
    ticker) with up to 25 tickers per batch, this is well within one page.
    Pagination via next_page_token is handled automatically.

Usage:
    feed = AlpacaMinuteBarFeed(
        api_key="...",
        api_secret="...",
        data_base_url="https://data.alpaca.markets",
    )
    bar_data = feed.fetch_session_bars(tickers, session_date)
"""

from __future__ import annotations

import datetime
import logging
import time
from typing import Dict, List, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# Alpaca Data v2 endpoint
_BARS_ENDPOINT = "/v2/stocks/bars"

# Session hours in ET (same window used by research cache)
_SESSION_START_ET = datetime.time(9, 30)
_SESSION_END_ET = datetime.time(15, 59)

# Batch size for multi-symbol requests (keep well under rate limits)
_TICKER_BATCH_SIZE = 25


class AlpacaMinuteBarFeed:
    """
    Fetches 1-minute bars from Alpaca Data v2 REST API.

    For the same-day intraday module, bars are fetched once per session
    (either for replay or at/after market close for a live session run).
    The result is a Dict[str, pd.DataFrame] that the signal runner consumes
    identically to the research parquet cache.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        data_base_url: str = "https://data.alpaca.markets",
        request_timeout: int = 30,
    ) -> None:
        self.data_base_url = data_base_url.rstrip("/")
        self.request_timeout = request_timeout
        self._headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret,
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_session_bars(
        self,
        tickers: List[str],
        session_date: datetime.date,
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch all 1-minute bars for session_date for the given tickers.

        Filters to regular session hours (09:30–15:59 ET) to match the
        research cache format exactly.

        Parameters:
            tickers      : list of ticker symbols
            session_date : the trading date

        Returns:
            Dict mapping ticker → DataFrame (may omit tickers with no data).
        """
        start_utc, end_utc = _session_utc_window(session_date)
        logger.info(
            f"Fetching Alpaca 1-min bars for {len(tickers)} tickers "
            f"on {session_date} (UTC {start_utc.isoformat()} – {end_utc.isoformat()})"
        )

        bar_data: Dict[str, pd.DataFrame] = {}

        for batch in _batched(tickers, _TICKER_BATCH_SIZE):
            batch_data = self._fetch_batch(batch, start_utc, end_utc)
            bar_data.update(batch_data)

        loaded = len(bar_data)
        missing = len(tickers) - loaded
        logger.info(
            f"Alpaca bars loaded: {loaded} tickers"
            + (f" ({missing} returned no data)" if missing else "")
        )
        return bar_data

    def validate_connectivity(self) -> dict:
        """
        Light connectivity check. Fetches the last 5 bars of SPY.

        Returns a dict with 'ok' (bool), 'message' (str), and optional
        'error' field on failure.
        """
        try:
            end = datetime.datetime.now(datetime.timezone.utc)
            start = end - datetime.timedelta(minutes=15)
            result = self._get(
                _BARS_ENDPOINT,
                params={
                    "symbols": "SPY",
                    "timeframe": "1Min",
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "limit": 5,
                    "feed": "iex",
                },
            )
            bars = result.get("bars", {}).get("SPY", [])
            return {
                "ok": True,
                "message": f"Alpaca data connectivity OK — received {len(bars)} SPY bar(s).",
            }
        except Exception as exc:
            return {"ok": False, "message": str(exc), "error": type(exc).__name__}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_batch(
        self,
        tickers: List[str],
        start_utc: datetime.datetime,
        end_utc: datetime.datetime,
    ) -> Dict[str, pd.DataFrame]:
        """Fetch bars for a batch of tickers. Handles pagination."""
        params: dict = {
            "symbols": ",".join(tickers),
            "timeframe": "1Min",
            "start": start_utc.isoformat(),
            "end": end_utc.isoformat(),
            "adjustment": "raw",
            "feed": "iex",
            "limit": 10000,
        }

        all_raw: Dict[str, list] = {t: [] for t in tickers}

        while True:
            try:
                response = self._get(_BARS_ENDPOINT, params=params)
            except Exception as exc:
                logger.error(f"Alpaca bars request failed: {exc}")
                break

            raw_bars: Dict[str, list] = response.get("bars") or {}
            for ticker, bars in raw_bars.items():
                if ticker in all_raw:
                    all_raw[ticker].extend(bars)

            next_token = response.get("next_page_token")
            if not next_token:
                break
            params["page_token"] = next_token

        # Convert raw dicts to DataFrames
        result: Dict[str, pd.DataFrame] = {}
        for ticker, bars in all_raw.items():
            if not bars:
                continue
            df = _bars_to_dataframe(bars)
            if not df.empty:
                result[ticker] = df

        return result

    def _get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """Make a GET request to the Alpaca Data API. Raises on HTTP errors."""
        url = self.data_base_url + endpoint
        response = requests.get(
            url,
            headers=self._headers,
            params=params,
            timeout=self.request_timeout,
        )
        if response.status_code == 429:
            # Basic rate-limit back-off (should not occur with small batches)
            logger.warning("Alpaca rate limit hit — waiting 2s before retry.")
            time.sleep(2)
            response = requests.get(
                url,
                headers=self._headers,
                params=params,
                timeout=self.request_timeout,
            )
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _session_utc_window(
    session_date: datetime.date,
) -> tuple[datetime.datetime, datetime.datetime]:
    """
    Return the UTC start and end of the regular trading session for session_date.

    Uses pandas to handle EDT/EST transitions correctly.
    Start = 09:30 ET = session open.
    End   = 16:01 ET = one minute past close (captures the 16:00 bar if present).
    """
    tz = "America/New_York"
    start_et = pd.Timestamp(
        year=session_date.year,
        month=session_date.month,
        day=session_date.day,
        hour=9,
        minute=30,
        tz=tz,
    )
    end_et = pd.Timestamp(
        year=session_date.year,
        month=session_date.month,
        day=session_date.day,
        hour=16,
        minute=1,
        tz=tz,
    )
    return start_et.tz_convert("UTC").to_pydatetime(), end_et.tz_convert("UTC").to_pydatetime()


def _bars_to_dataframe(raw_bars: list) -> pd.DataFrame:
    """
    Convert a list of Alpaca bar dicts to a research-cache-compatible DataFrame.

    Alpaca bar timestamp 't' is the bar OPEN time in RFC3339 UTC format.
    This matches the Polygon.io convention used by the research cache.
    """
    if not raw_bars:
        return pd.DataFrame()

    rows = []
    for b in raw_bars:
        rows.append({
            "timestamp": b["t"],
            "open":   float(b["o"]),
            "high":   float(b["h"]),
            "low":    float(b["l"]),
            "close":  float(b["c"]),
            "volume": float(b["v"]),
        })

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert("America/New_York")
    df = df.set_index("timestamp").sort_index()

    # Clip to regular session hours (09:30–15:59 ET)
    df = df.between_time("09:30", "15:59")
    return df


def _batched(items: List[str], size: int):
    """Yield successive batches of up to `size` items."""
    for i in range(0, len(items), size):
        yield items[i : i + size]
