"""
research_build_market_reference_cache.py
Side:  research -- cache builder layer

Purpose:
  Pre-cache shared market reference data for SPY and QQQ.
  Builds two timeframes per ticker:
    - daily    -> research_data_cache/market/daily/<TICKER>.parquet
    - intraday_1m -> research_data_cache/market/intraday_1m/<TICKER>.parquet

  These are secondary market reference files only.
  They do not represent stock-level research universe data.
  Do not use these files as primary family strategy logic.

Idempotency:
  If a cache file already exists and --overwrite is not set, the ticker/timeframe
  combination is skipped. Pass --overwrite to rebuild.

Intraday chunking:
  5 years of 1-minute data exceeds a single comfortable API page count.
  The builder fetches in 6-month chunks and merges into one final parquet.
  Chunk boundaries and row counts are printed for gap detection.

Output contract:
  - DatetimeIndex in America/New_York timezone
  - Lowercase columns: open, high, low, close, volume
  - Sorted ascending, deduplicated

Auth:
  Requires MASSIVE_API_KEY environment variable.

Dependencies:
  pip install -U massive pandas pyarrow
"""

import os
import sys
import datetime
import argparse
import pandas as pd
from massive import RESTClient

# -- Paths --------------------------------------------------------------------

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT    = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
MARKET_ROOT  = os.path.join(REPO_ROOT, "1_0_strategy_research", "research_data_cache", "market")
DAILY_DIR    = os.path.join(MARKET_ROOT, "daily")
INTRA_DIR    = os.path.join(MARKET_ROOT, "intraday_1m")
PROVIDER_DIR = os.path.join(REPO_ROOT, "1_0_strategy_research", "research_source_code", "data_providers")

for d in [DAILY_DIR, INTRA_DIR]:
    os.makedirs(d, exist_ok=True)

sys.path.insert(0, PROVIDER_DIR)
from research_provider_intraday_1m_massive import normalize_aggs, _get_api_key  # noqa: E402

# -- Defaults -----------------------------------------------------------------

DEFAULT_TICKERS    = ["SPY", "QQQ"]
DEFAULT_DATE_START = "2021-03-25"
DEFAULT_DATE_END   = "2026-03-24"
CHUNK_MONTHS       = 6   # intraday 1m only

# -- Daily fetch --------------------------------------------------------------

def fetch_daily(ticker: str, start: str, end: str, client: RESTClient) -> pd.DataFrame | None:
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
        return normalize_aggs(aggs)
    except Exception as exc:
        print(f"  {ticker} daily ERROR: {exc}")
        return None

# -- Intraday 1m fetch (chunked) ----------------------------------------------

def _next_chunk_end(cursor: datetime.date, months: int, hard_end: datetime.date) -> datetime.date:
    month = cursor.month - 1 + months
    year  = cursor.year + month // 12
    month = month % 12 + 1
    day   = min(cursor.day, [31,28,31,30,31,30,31,31,30,31,30,31][month-1])
    return min(datetime.date(year, month, day), hard_end)


def fetch_intraday_1m_chunked(
    ticker: str,
    start_date: datetime.date,
    end_date: datetime.date,
    client: RESTClient,
    chunk_months: int = CHUNK_MONTHS,
) -> pd.DataFrame | None:
    chunks = []
    cursor = start_date
    chunk_num = 0

    while cursor <= end_date:
        chunk_end = _next_chunk_end(cursor, chunk_months, end_date)
        chunk_num += 1
        label = f"{cursor} to {chunk_end}"
        try:
            aggs = list(client.list_aggs(
                ticker=ticker,
                multiplier=1,
                timespan="minute",
                from_=cursor.isoformat(),
                to=chunk_end.isoformat(),
                adjusted=True,
                limit=50000,
            ))
            chunk_df = _normalize(aggs)
            if chunk_df is not None and not chunk_df.empty:
                chunks.append(chunk_df)
                print(f"    chunk {chunk_num} [{label}]: {len(chunk_df)} bars")
            else:
                print(f"    chunk {chunk_num} [{label}]: 0 bars (gap or non-trading period)")
        except Exception as exc:
            print(f"    chunk {chunk_num} [{label}]: ERROR - {exc}")

        # Advance cursor to day after chunk_end
        cursor = chunk_end + datetime.timedelta(days=1)

    if not chunks:
        return None

    combined = pd.concat(chunks).sort_index()
    combined = combined[~combined.index.duplicated(keep="first")]
    return combined[["open", "high", "low", "close", "volume"]]

# -- Cache writer -------------------------------------------------------------

def cache_ticker_timeframe(
    ticker: str,
    timeframe: str,
    start: str,
    end: str,
    client: RESTClient,
    overwrite: bool,
) -> tuple[str, int | None]:
    """
    Fetch and write one ticker+timeframe parquet.
    Returns (status, row_count).  status: 'cached' | 'skipped' | 'failed'
    """
    out_dir  = DAILY_DIR if timeframe == "daily" else INTRA_DIR
    out_path = os.path.join(out_dir, f"{ticker}.parquet")

    if os.path.exists(out_path) and not overwrite:
        print(f"  {ticker} {timeframe}: skipped (already cached)")
        return "skipped", None

    start_date = datetime.date.fromisoformat(start)
    end_date   = datetime.date.fromisoformat(end)

    if timeframe == "daily":
        print(f"  {ticker} daily: fetching {start} to {end} ...", flush=True)
        df = fetch_daily(ticker, start, end, client)
    else:
        print(f"  {ticker} intraday_1m: fetching {start} to {end} in {CHUNK_MONTHS}-month chunks ...", flush=True)
        df = fetch_intraday_1m_chunked(ticker, start_date, end_date, client)

    if df is None or df.empty:
        print(f"  {ticker} {timeframe}: FAILED - no data returned")
        return "failed", None

    df.to_parquet(out_path)
    print(f"  {ticker} {timeframe}: cached {len(df)} rows -> {out_path}")
    return "cached", len(df)

# -- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Build shared market reference cache (SPY, QQQ) from Massive.com"
    )
    parser.add_argument("--tickers",    nargs="+", default=DEFAULT_TICKERS)
    parser.add_argument("--start",      default=DEFAULT_DATE_START, metavar="YYYY-MM-DD")
    parser.add_argument("--end",        default=DEFAULT_DATE_END,   metavar="YYYY-MM-DD")
    parser.add_argument("--timeframes", nargs="+", default=["daily", "intraday_1m"],
                        choices=["daily", "intraday_1m"])
    parser.add_argument("--overwrite",  action="store_true")
    args = parser.parse_args()

    api_key = _get_api_key()
    client  = RESTClient(api_key=api_key)

    print("=" * 60)
    print("research_build_market_reference_cache")
    print(f"Tickers    : {args.tickers}")
    print(f"Timeframes : {args.timeframes}")
    print(f"Date range : {args.start} to {args.end}")
    print(f"Overwrite  : {args.overwrite}")
    print(f"Daily dir  : {DAILY_DIR}")
    print(f"Intra dir  : {INTRA_DIR}")
    print("=" * 60)

    results = []
    for ticker in args.tickers:
        for tf in args.timeframes:
            status, rows = cache_ticker_timeframe(
                ticker, tf, args.start, args.end, client, args.overwrite
            )
            results.append({"ticker": ticker, "timeframe": tf, "status": status, "rows": rows})

    print()
    print("Summary:")
    print(f"  {'Ticker':<6} {'Timeframe':<14} {'Status':<10} {'Rows'}")
    print("  " + "-" * 44)
    for r in results:
        rows_str = str(r["rows"]) if r["rows"] is not None else "-"
        print(f"  {r['ticker']:<6} {r['timeframe']:<14} {r['status']:<10} {rows_str}")

    failures = [r for r in results if r["status"] == "failed"]
    if failures:
        print(f"\nWARNING: {len(failures)} failure(s) detected - check output above for details.")
    else:
        print("\nAll builds completed with no failures.")


if __name__ == "__main__":
    main()
