"""
research_extend_intraday_1m_cache.py
Track: intraday_same_day
Side: research — cache builder layer

Purpose:
  Extend existing intraday_1m parquet files backward in time.
  For each ticker, fetches the specified EXTENSION window (e.g. 2024-03-25 to 2025-06-30),
  merges with any existing cached data, deduplicates, and overwrites the parquet file.

  Designed specifically for tickers that were cached with a short window (e.g. 2025-07-01 to
  2025-12-31) and need their history extended backward without losing existing data.

Usage:
  Mode A — ticker file:
    python research_extend_intraday_1m_cache.py --ticker-file path/to/tickers.csv

  Mode B — tickers directly:
    python research_extend_intraday_1m_cache.py --tickers AAPL MSFT NVDA

Optional flags:
  --start YYYY-MM-DD   Start of the extension window (default: 2024-03-25)
  --end   YYYY-MM-DD   End of the extension window (default: 2025-06-30)
  --max-tickers N      Limit to first N tickers (smoke-test mode)

Merge behavior:
  - Fetches the extension range from the API.
  - Loads existing parquet (if present).
  - Concatenates new + existing, drops duplicate timestamps, sorts ascending.
  - Overwrites the parquet file with the merged result.
  - If the extension range already exists in the file, no data is added (idempotent).

Rate limiting:
  Same as research_build_intraday_1m_cache.py: 2s sleep between tickers,
  exponential backoff on 429 (60s / 120s / 240s), max 3 retries.

Cache location:
  <repo_root>/1_0_strategy_research/research_data_cache/intraday_1m/<TICKER>.parquet

Auth:
  Requires MASSIVE_API_KEY environment variable.
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

DEFAULT_EXT_START = "2024-03-25"
DEFAULT_EXT_END   = "2025-06-30"

# -- Rate limiting config -----------------------------------------------------

RATE_LIMIT_SLEEP  = 5.0    # increased from 2.0 — 15-month range = ~4 sub-requests per ticker
MAX_429_RETRIES   = 3
BACKOFF_BASE_SECS = 60

# -- 429 detection ------------------------------------------------------------

def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "too many" in msg or "rate limit" in msg


def _extract_retry_after(exc: Exception) -> int | None:
    m = re.search(r"retry-after[:\s]+(\d+)", str(exc), re.IGNORECASE)
    return int(m.group(1)) if m else None

# -- Windows reserved filename guard ------------------------------------------

_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def _safe_cache_path(ticker: str) -> str:
    stem = f"{ticker}__reserved" if ticker.upper() in _WIN_RESERVED else ticker
    return os.path.join(CACHE_DIR, f"{stem}.parquet")

# -- Ticker resolution --------------------------------------------------------

def load_tickers_from_file(path: str) -> list[str]:
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

# -- Extension skip check -----------------------------------------------------

def _extension_already_covered(path: str, ext_start: datetime.date) -> bool:
    """
    Return True if the parquet file already has data starting at or before ext_start.
    In that case, extending is a no-op and we can skip the API call.
    """
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return False
    try:
        df = pd.read_parquet(path)
        if df.empty:
            return False
        file_min_date = df.index.min().date()
        # Allow 5-day tolerance for weekends/holidays around the start boundary
        return file_min_date <= (ext_start + datetime.timedelta(days=5))
    except Exception:
        return False

# -- Per-ticker extend-and-merge ----------------------------------------------

def extend_ticker(
    ticker: str,
    ext_start: datetime.date,
    ext_end: datetime.date,
    client: RESTClient,
) -> str:
    """
    Fetch ext_start..ext_end from API, merge with existing parquet, overwrite.
    Returns: 'extended' | 'already_covered' | 'failed' | 'rate_limited'
    """
    path = _safe_cache_path(ticker)

    # Skip if file already covers the requested extension range
    if _extension_already_covered(path, ext_start):
        return "already_covered"

    # Load existing data if present
    existing_df = None
    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            existing_df = pd.read_parquet(path)
        except Exception as e:
            print(f"  {ticker}: WARNING - could not read existing parquet: {e}")

    # Fetch the extension range from API
    for attempt in range(MAX_429_RETRIES + 1):
        try:
            aggs = list(client.list_aggs(
                ticker=ticker,
                multiplier=1,
                timespan="minute",
                from_=ext_start.isoformat(),
                to=ext_end.isoformat(),
                limit=50000,
            ))
            new_df = normalize_aggs(aggs)
            if new_df is None or new_df.empty:
                # No data in range — treat as permanent gap (e.g. ticker listed after ext_end)
                if existing_df is not None:
                    # Preserve existing file unchanged — just no new data available
                    return "already_covered"
                return "failed"

            # Merge: concatenate new + existing, dedup, sort
            if existing_df is not None and not existing_df.empty:
                merged = pd.concat([new_df, existing_df])
                merged = merged[~merged.index.duplicated(keep="first")]
                merged = merged.sort_index()
            else:
                merged = new_df

            merged.to_parquet(path)
            time.sleep(RATE_LIMIT_SLEEP)
            return "extended"

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

    return "rate_limited"

# -- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extend existing intraday 1-min parquet cache backward in time"
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
    parser.add_argument("--start",       default=DEFAULT_EXT_START, metavar="YYYY-MM-DD",
                        help=f"Start of extension window (default: {DEFAULT_EXT_START})")
    parser.add_argument("--end",         default=DEFAULT_EXT_END,   metavar="YYYY-MM-DD",
                        help=f"End of extension window (default: {DEFAULT_EXT_END})")
    parser.add_argument("--max-tickers", type=int, default=None, metavar="N",
                        help="Limit to first N tickers (smoke-test mode).")
    args = parser.parse_args()

    tickers = resolve_tickers(args)
    if args.max_tickers is not None:
        tickers = tickers[: args.max_tickers]

    ext_start = datetime.date.fromisoformat(args.start)
    ext_end   = datetime.date.fromisoformat(args.end)
    client    = RESTClient(api_key=_get_api_key())

    print(f"\n{'='*60}")
    print("research_extend_intraday_1m_cache - Massive.com")
    print(f"Extension range: {ext_start} to {ext_end}")
    print(f"Tickers        : {len(tickers)}" + (" [SMOKE TEST]" if args.max_tickers is not None else ""))
    print(f"Cache dir      : {CACHE_DIR}")
    print(f"Rate limit     : {RATE_LIMIT_SLEEP}s baseline sleep, {BACKOFF_BASE_SECS}s base backoff on 429")
    print(f"{'='*60}\n")

    n_extended        = 0
    n_already_covered = 0
    n_failed          = 0
    n_rate_limited    = 0
    rate_limited_list = []
    failed_list       = []

    for i, ticker in enumerate(tickers, 1):
        status = extend_ticker(ticker, ext_start, ext_end, client)
        if status == "extended":
            n_extended += 1
            print(f"  {ticker}: extended", flush=True)
        elif status == "already_covered":
            n_already_covered += 1
        elif status == "rate_limited":
            n_rate_limited += 1
            rate_limited_list.append(ticker)
        else:
            n_failed += 1
            failed_list.append(ticker)

        if i % 25 == 0 or i == len(tickers):
            print(
                f"  [{i}/{len(tickers)}] extended={n_extended} "
                f"already_covered={n_already_covered} "
                f"rate_limited={n_rate_limited} failed={n_failed}",
                flush=True,
            )

    # Write retry waitlist
    today = datetime.date.today().strftime("%Y_%m_%d")
    if rate_limited_list:
        wl_df   = pd.DataFrame({"ticker": rate_limited_list, "reason": "429_all_retries_exhausted"})
        wl_file = os.path.join(WAITLIST_DIR, f"intraday_1m_extend_retry_waitlist__{today}.csv")
        wl_df.to_csv(wl_file, index=False)
        print(f"\nRetry waitlist ({len(rate_limited_list)} tickers): {wl_file}")

    print(
        f"\nDone. Extended: {n_extended}  Already covered: {n_already_covered}  "
        f"Rate-limited: {n_rate_limited}  Failed: {n_failed}"
    )

    if failed_list:
        print(f"Permanent failures ({len(failed_list)}): {failed_list[:20]}")
        if len(failed_list) > 20:
            print(f"  ... and {len(failed_list) - 20} more")


if __name__ == "__main__":
    main()
