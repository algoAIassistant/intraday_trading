"""
research_build_daily_cache.py
Side:  research -- cache builder layer

Purpose:
  Build one daily OHLCV parquet per ticker for the full shared master universe.
  Writes to research_data_cache/daily/<TICKER>.parquet.

  NOTE ON SCOPE:
    The shared master universe is the BROAD canonical registry.
    This script caches raw daily price data for that broad list.
    Price-based filtering (e.g. max price cap) is applied downstream
    by research_derive_working_universe_price_cap.py, not here.

Rate limiting:
  A baseline sleep of RATE_LIMIT_SLEEP seconds is applied between each ticker.
  On a 429 response, the script backs off exponentially (60s, 120s, 240s)
  and retries up to MAX_429_RETRIES times.
  Tickers that still fail after all retries are written to a retry_waitlist CSV
  and are NOT classified as permanent data failures.

Idempotency:
  Tickers already present in the cache are skipped unless --overwrite is set.
  Re-running after a partial failure will skip already-cached tickers.

Usage:
  # Full universe from canonical symbol list (default)
  python research_build_daily_cache.py

  # Custom ticker list
  python research_build_daily_cache.py --tickers AAPL MSFT NVDA

  # Custom ticker file (CSV with a 'ticker' column)
  python research_build_daily_cache.py --ticker-file path/to/tickers.csv

  # Override date range
  python research_build_daily_cache.py --start 2021-03-25 --end 2026-03-24

  # Re-fetch already-cached tickers
  python research_build_daily_cache.py --overwrite

Auth:
  Requires MASSIVE_API_KEY environment variable.

Dependencies:
  pip install -U massive pandas pyarrow
"""

import os
import re
import sys
import time
import argparse
import datetime
import pandas as pd
from massive import RESTClient

# -- Paths --------------------------------------------------------------------

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT    = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
CACHE_DIR    = os.path.join(REPO_ROOT, "1_0_strategy_research", "research_data_cache", "daily")
PROVIDER_DIR = os.path.join(REPO_ROOT, "1_0_strategy_research", "research_source_code", "data_providers")
UNIVERSE_CSV = os.path.join(
    REPO_ROOT,
    "0_1_shared_master_universe", "shared_symbol_lists",
    "shared_master_symbol_list_us_common_stocks.csv"
)
WAITLIST_DIR = os.path.join(REPO_ROOT, "1_0_strategy_research", "research_data_cache")

os.makedirs(CACHE_DIR, exist_ok=True)
sys.path.insert(0, PROVIDER_DIR)

from research_provider_intraday_1m_massive import normalize_aggs, _get_api_key  # noqa: E402

# -- Defaults -----------------------------------------------------------------

DEFAULT_DATE_START = "2021-03-25"
DEFAULT_DATE_END   = "2026-03-24"

# -- Rate limiting config -----------------------------------------------------

RATE_LIMIT_SLEEP  = 0.15   # seconds between successful fetches (~6-7 req/sec)
MAX_429_RETRIES   = 3
BACKOFF_BASE_SECS = 60     # first backoff: 60s, then 120s, then 240s

# -- Ticker resolution --------------------------------------------------------

def load_tickers_from_file(path: str) -> list[str]:
    try:
        df = pd.read_csv(path)
    except FileNotFoundError:
        print(f"ERROR: ticker file not found: {path}")
        sys.exit(1)
    if "ticker" not in df.columns:
        print(f"ERROR: CSV must have a 'ticker' column. Found: {list(df.columns)}")
        sys.exit(1)
    tickers = df["ticker"].dropna().str.strip().str.upper().tolist()
    if not tickers:
        print(f"ERROR: ticker file is empty or all values are blank: {path}")
        sys.exit(1)
    return tickers


def resolve_tickers(args) -> list[str]:
    if args.tickers:
        return [t.strip().upper() for t in args.tickers if t.strip()]
    if args.ticker_file:
        return load_tickers_from_file(args.ticker_file)
    # Default: canonical shared universe
    if not os.path.exists(UNIVERSE_CSV):
        print(f"ERROR: canonical shared universe not found: {UNIVERSE_CSV}")
        print("  Run research_build_shared_master_universe_us_common_stocks.py first.")
        sys.exit(1)
    return load_tickers_from_file(UNIVERSE_CSV)

# -- 429 detection ------------------------------------------------------------

def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "too many" in msg or "rate limit" in msg


def _extract_retry_after(exc: Exception) -> int | None:
    """Parse Retry-After seconds from exception text. Returns None if absent."""
    m = re.search(r"retry-after[:\s]+(\d+)", str(exc), re.IGNORECASE)
    return int(m.group(1)) if m else None

# -- Windows reserved filename guard ------------------------------------------

# Windows device names that cannot be used as filenames regardless of extension.
_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def _safe_cache_path(ticker: str) -> str:
    """
    Return the parquet file path for a ticker.
    If the ticker is a Windows-reserved device name, the filename is suffixed
    with __reserved so the OS will accept it.  The ticker symbol inside the
    parquet data is never altered.
    Mapping is deterministic: CON -> CON__reserved.parquet
    """
    stem = f"{ticker}__reserved" if ticker.upper() in _WIN_RESERVED else ticker
    return os.path.join(CACHE_DIR, f"{stem}.parquet")


# -- Cache writer with backoff ------------------------------------------------

def cache_ticker(
    ticker: str,
    start: str,
    end: str,
    client: RESTClient,
    overwrite: bool,
) -> str:
    """
    Returns: 'cached' | 'skipped' | 'failed' | 'rate_limited'
    'rate_limited' means all retries exhausted on 429 - not a data failure.
    """
    path = _safe_cache_path(ticker)

    if os.path.exists(path) and os.path.getsize(path) > 0 and not overwrite:
        return "skipped"

    for attempt in range(MAX_429_RETRIES + 1):
        try:
            aggs = list(client.list_aggs(
                ticker=ticker,
                multiplier=1,
                timespan="day",
                from_=start,
                to=end,
                adjusted=True,
                limit=50000,
            ))
            df = normalize_aggs(aggs)
            if df is None or df.empty:
                return "failed"
            df.to_parquet(path)
            time.sleep(RATE_LIMIT_SLEEP)
            return "cached"

        except Exception as exc:
            if _is_rate_limit_error(exc):
                if attempt < MAX_429_RETRIES:
                    retry_after = _extract_retry_after(exc)
                    wait = retry_after if retry_after is not None else BACKOFF_BASE_SECS * (2 ** attempt)
                    print(f"  {ticker}: 429 rate limited - waiting {wait}s (retry {attempt + 1}/{MAX_429_RETRIES}) ...")
                    time.sleep(wait)
                else:
                    print(f"  {ticker}: 429 rate limited - all retries exhausted, adding to waitlist")
                    return "rate_limited"
            else:
                print(f"  {ticker}: ERROR - {exc}")
                return "failed"

    return "rate_limited"  # unreachable but satisfies type checker

# -- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Build daily OHLCV parquet cache from Massive.com"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--tickers",     nargs="+", metavar="TICKER")
    group.add_argument("--ticker-file", metavar="PATH")
    parser.add_argument("--start",      default=DEFAULT_DATE_START, metavar="YYYY-MM-DD")
    parser.add_argument("--end",        default=DEFAULT_DATE_END,   metavar="YYYY-MM-DD")
    parser.add_argument("--overwrite",  action="store_true")
    parser.add_argument("--max-tickers", type=int, default=None, metavar="N",
                        help="Limit to first N tickers (smoke-test mode).")
    args = parser.parse_args()

    tickers = resolve_tickers(args)
    if args.max_tickers is not None:
        tickers = tickers[: args.max_tickers]
    client  = RESTClient(api_key=_get_api_key())

    ticker_source = "canonical shared universe" if (not args.tickers and not args.ticker_file) else (
        "command-line list" if args.tickers else args.ticker_file
    )

    print("=" * 60)
    print("research_build_daily_cache")
    print("NOTE: shared master universe = BROAD canonical registry")
    print("NOTE: price-cap filtering is applied DOWNSTREAM, not here")
    print(f"Ticker source : {ticker_source}")
    print(f"Ticker count  : {len(tickers)}" + (" [SMOKE TEST]" if args.max_tickers is not None else ""))
    print(f"Date range    : {args.start} to {args.end}")
    print(f"Cache dir     : {CACHE_DIR}")
    print(f"Overwrite     : {args.overwrite}")
    print(f"Rate limit    : {RATE_LIMIT_SLEEP}s baseline, {BACKOFF_BASE_SECS}s base backoff on 429")
    print("=" * 60)

    n_cached       = 0
    n_skipped      = 0
    n_failed       = 0
    n_rate_limited = 0
    rate_limited_list = []
    failed_list       = []

    for i, ticker in enumerate(tickers, 1):
        status = cache_ticker(ticker, args.start, args.end, client, args.overwrite)
        if status == "cached":
            n_cached += 1
        elif status == "skipped":
            n_skipped += 1
        elif status == "rate_limited":
            n_rate_limited += 1
            rate_limited_list.append(ticker)
        else:
            n_failed += 1
            failed_list.append(ticker)

        if i % 100 == 0 or i == len(tickers):
            print(f"  [{i}/{len(tickers)}] cached={n_cached} skipped={n_skipped} "
                  f"rate_limited={n_rate_limited} failed={n_failed}", flush=True)

    # Write retry waitlist for rate-limited tickers
    today = datetime.date.today().strftime("%Y_%m_%d")
    if rate_limited_list:
        wl_df   = pd.DataFrame({"ticker": rate_limited_list, "reason": "429_all_retries_exhausted"})
        wl_file = os.path.join(WAITLIST_DIR, f"daily_cache_retry_waitlist__{today}.csv")
        wl_df.to_csv(wl_file, index=False)
        print(f"\nRetry waitlist ({len(rate_limited_list)} tickers): {wl_file}")
        print(f"  Re-run with the same command to retry (already-cached tickers are skipped).")

    print(f"\nDone. Cached: {n_cached}  Skipped: {n_skipped}  "
          f"Rate-limited: {n_rate_limited}  Failed: {n_failed}")

    if failed_list:
        print(f"Permanent failures ({len(failed_list)}): {failed_list[:20]}")
        if len(failed_list) > 20:
            print(f"  ... and {len(failed_list) - 20} more")


if __name__ == "__main__":
    main()
