"""
research_build_intraday_1m_cache.py
Track: intraday_same_day
Side: research — cache builder layer

Purpose:
  Populate research_data_cache/intraday_1m/ with one .parquet file per ticker.
  Calls the Massive.com REST API directly with full 429 rate-limit handling.

Usage (two supported modes):

  Mode A — pass a CSV file with one ticker per line (header: ticker):
    python research_build_intraday_1m_cache.py --ticker-file path/to/tickers.csv

  Mode B — pass tickers directly on the command line:
    python research_build_intraday_1m_cache.py --tickers AAPL MSFT NVDA

  If neither is provided, the script exits with a clear error.

Optional flags:
  --start YYYY-MM-DD   override default DATE_START
  --end   YYYY-MM-DD   override default DATE_END
  --overwrite          re-fetch even if .parquet already exists
  --max-tickers N      limit to first N tickers (smoke-test mode)

Rate limiting:
  Intraday 1-minute data requires multiple paginated API sub-requests per ticker
  (5 years of 1-min bars ~ 490K rows, paged at 50K per call = ~10 sub-requests).
  A generous RATE_LIMIT_SLEEP is applied between each ticker to avoid burst 429s.
  On a 429 response, the script backs off exponentially (60s, 120s, 240s) and
  retries up to MAX_429_RETRIES times.
  Tickers that still fail after all retries are written to a retry_waitlist CSV.

Idempotency:
  Tickers already present in the cache are skipped unless --overwrite is set.
  Re-running after a partial failure will skip already-cached tickers.

Cache location:
  <repo_root>/1_0_strategy_research/research_data_cache/intraday_1m/<TICKER>.parquet

Auth:
  Requires MASSIVE_API_KEY environment variable (read by the provider module).

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
CACHE_DIR    = os.path.join(REPO_ROOT, "1_0_strategy_research", "research_data_cache", "intraday_1m")
PROVIDER_DIR = os.path.join(REPO_ROOT, "1_0_strategy_research", "research_source_code", "data_providers")
WAITLIST_DIR = os.path.join(REPO_ROOT, "1_0_strategy_research", "research_data_cache")

os.makedirs(CACHE_DIR, exist_ok=True)
sys.path.insert(0, PROVIDER_DIR)

from research_provider_intraday_1m_massive import normalize_aggs, _get_api_key  # noqa: E402

# -- Defaults -----------------------------------------------------------------

DEFAULT_DATE_START = "2021-01-04"
DEFAULT_DATE_END   = "2026-03-21"

# -- Rate limiting config -----------------------------------------------------

RATE_LIMIT_SLEEP  = 2.0    # seconds between successful fetches (intraday data = many sub-requests)
MAX_429_RETRIES   = 3
BACKOFF_BASE_SECS = 60     # first backoff: 60s, then 120s, then 240s

# -- 429 detection ------------------------------------------------------------

def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "too many" in msg or "rate limit" in msg


def _extract_retry_after(exc: Exception) -> int | None:
    """Parse Retry-After seconds from exception text. Returns None if absent."""
    m = re.search(r"retry-after[:\s]+(\d+)", str(exc), re.IGNORECASE)
    return int(m.group(1)) if m else None

# -- Windows reserved filename guard ------------------------------------------

_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def _safe_cache_path(ticker: str) -> str:
    """
    Return the parquet file path for a ticker.
    Windows-reserved device names get a __reserved suffix so the OS accepts them.
    Mapping is deterministic: CON -> CON__reserved.parquet
    """
    stem = f"{ticker}__reserved" if ticker.upper() in _WIN_RESERVED else ticker
    return os.path.join(CACHE_DIR, f"{stem}.parquet")

# -- Ticker resolution --------------------------------------------------------

def load_tickers_from_file(path: str) -> list[str]:
    """Read tickers from a CSV file. Expects a column named 'ticker'."""
    if not os.path.exists(path):
        print(f"ERROR: ticker file not found: {path}")
        sys.exit(1)
    df = pd.read_csv(path)
    if "ticker" not in df.columns:
        print(f"ERROR: ticker file must have a column named 'ticker'. Found: {list(df.columns)}")
        sys.exit(1)
    tickers = df["ticker"].dropna().str.strip().str.upper().tolist()
    if not tickers:
        print(f"ERROR: ticker file is empty or all values are blank: {path}")
        sys.exit(1)
    return tickers


def resolve_tickers(args) -> list[str]:
    """Return ticker list from --ticker-file or --tickers. Fail if neither is provided."""
    if args.ticker_file:
        return load_tickers_from_file(args.ticker_file)
    if args.tickers:
        return [t.strip().upper() for t in args.tickers if t.strip()]
    print(
        "ERROR: no ticker source provided.\n"
        "  Use --ticker-file path/to/tickers.csv\n"
        "  or  --tickers AAPL MSFT NVDA ..."
    )
    sys.exit(1)

# -- Cache writer with backoff ------------------------------------------------

def cache_ticker(
    ticker: str,
    start: datetime.date,
    end: datetime.date,
    client: RESTClient,
    overwrite: bool,
) -> str:
    """
    Fetch and cache one ticker's 1-minute OHLCV data.
    Returns: 'cached' | 'skipped' | 'failed' | 'rate_limited'
    'rate_limited' means all retries exhausted on 429 - not a permanent data failure.
    """
    path = _safe_cache_path(ticker)

    if os.path.exists(path) and os.path.getsize(path) > 0 and not overwrite:
        return "skipped"

    for attempt in range(MAX_429_RETRIES + 1):
        try:
            aggs = list(client.list_aggs(
                ticker=ticker,
                multiplier=1,
                timespan="minute",
                from_=start.isoformat(),
                to=end.isoformat(),
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

    return "rate_limited"  # satisfies type checker

# -- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Build intraday 1-min parquet cache from Massive.com"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--ticker-file",
        metavar="PATH",
        help="Path to a CSV file with a 'ticker' column",
    )
    group.add_argument(
        "--tickers",
        nargs="+",
        metavar="TICKER",
        help="One or more ticker symbols passed directly",
    )
    parser.add_argument("--start",       default=DEFAULT_DATE_START, metavar="YYYY-MM-DD")
    parser.add_argument("--end",         default=DEFAULT_DATE_END,   metavar="YYYY-MM-DD")
    parser.add_argument("--overwrite",   action="store_true",
                        help="Re-fetch and overwrite existing parquet files")
    parser.add_argument("--max-tickers", type=int, default=None, metavar="N",
                        help="Limit to first N tickers (smoke-test mode).")
    args = parser.parse_args()

    tickers = resolve_tickers(args)
    if args.max_tickers is not None:
        tickers = tickers[: args.max_tickers]

    start  = datetime.date.fromisoformat(args.start)
    end    = datetime.date.fromisoformat(args.end)
    client = RESTClient(api_key=_get_api_key())

    print(f"\n{'='*60}")
    print("research_build_intraday_1m_cache - Massive.com")
    print(f"Date range : {start} to {end}")
    print(f"Tickers    : {len(tickers)}" + (" [SMOKE TEST]" if args.max_tickers is not None else ""))
    print(f"Cache dir  : {CACHE_DIR}")
    print(f"Overwrite  : {args.overwrite}")
    print(f"Rate limit : {RATE_LIMIT_SLEEP}s baseline sleep, {BACKOFF_BASE_SECS}s base backoff on 429")
    print(f"{'='*60}\n")

    n_cached       = 0
    n_skipped      = 0
    n_failed       = 0
    n_rate_limited = 0
    rate_limited_list = []
    failed_list       = []

    for i, ticker in enumerate(tickers, 1):
        status = cache_ticker(ticker, start, end, client, args.overwrite)
        if status == "cached":
            n_cached += 1
            print(f"  {ticker}: cached")
        elif status == "skipped":
            n_skipped += 1
        elif status == "rate_limited":
            n_rate_limited += 1
            rate_limited_list.append(ticker)
        else:
            n_failed += 1
            failed_list.append(ticker)

        if i % 25 == 0 or i == len(tickers):
            print(f"  [{i}/{len(tickers)}] cached={n_cached} skipped={n_skipped} "
                  f"rate_limited={n_rate_limited} failed={n_failed}", flush=True)

    # Write retry waitlist for rate-limited tickers
    today = datetime.date.today().strftime("%Y_%m_%d")
    if rate_limited_list:
        wl_df   = pd.DataFrame({"ticker": rate_limited_list, "reason": "429_all_retries_exhausted"})
        wl_file = os.path.join(WAITLIST_DIR, f"intraday_1m_cache_retry_waitlist__{today}.csv")
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
