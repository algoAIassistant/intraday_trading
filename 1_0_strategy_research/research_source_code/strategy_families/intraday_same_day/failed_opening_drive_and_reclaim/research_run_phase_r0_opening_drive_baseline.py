"""
research_run_phase_r0_opening_drive_baseline.py
Track:  intraday_same_day
Family: failed_opening_drive_and_reclaim
Phase:  phase_r0 — baseline (no failure/reclaim condition applied)

Purpose:
  Characterize natural same-day behavior around early-session directional drives.
  No trading condition is applied here. This is the unconditional baseline that
  phase_r1 will later compare conditioned behavior against.

What this script does:
  1. Loads 1-minute parquet cache for each ticker (cache-only — no live fetch).
  2. For each trading day in the date range, identifies the opening drive direction
     (up / down / flat) based on price movement in the first DRIVE_MINUTES bars.
  3. Measures same-day return metrics for each session.
  4. Writes three output artifacts to the family phase_r0 output folder.

Outputs (written to research_outputs/family_lineages/failed_opening_drive_and_reclaim/phase_r0_baseline/):
  research_output_failed_opening_drive_and_reclaim__phase_r0_baseline__session_detail__<DATE>.csv
  research_output_failed_opening_drive_and_reclaim__phase_r0_baseline__bucket_summary__<DATE>.csv
  research_output_failed_opening_drive_and_reclaim__phase_r0_baseline__run_info__<DATE>.txt

Cache-only guarantee:
  All data is read from research_data_cache/intraday_1m/<TICKER>.parquet.
  If a ticker's parquet is missing, that ticker is skipped with a logged warning.
  The Massive provider is never called from this script.

Usage:
  # Smoke run (defaults below)
  python research_run_phase_r0_opening_drive_baseline.py

  # Custom tickers and date range
  python research_run_phase_r0_opening_drive_baseline.py --tickers AAPL MSFT NVDA --start 2024-01-02 --end 2024-01-03

  # Full universe from a CSV file (CSV must have a 'ticker' column)
  python research_run_phase_r0_opening_drive_baseline.py --ticker-file path/to/tickers.csv --start 2022-01-03 --end 2025-12-31
"""

import os
import sys
import json
import argparse
import datetime
import warnings
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")

# -- Paths --------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT  = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", "..", "..", ".."))
CACHE_DIR  = os.path.join(REPO_ROOT, "1_0_strategy_research", "research_data_cache", "intraday_1m")
OUTPUT_DIR = os.path.join(
    REPO_ROOT,
    "1_0_strategy_research", "research_outputs",
    "family_lineages", "failed_opening_drive_and_reclaim", "phase_r0_baseline"
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

TODAY = datetime.date.today().strftime("%Y_%m_%d")

# -- Defaults (smoke run) -----------------------------------------------------

DEFAULT_TICKERS    = ["AAPL", "MSFT", "NVDA"]
DEFAULT_DATE_START = "2024-01-02"
DEFAULT_DATE_END   = "2024-01-03"

# -- Config -------------------------------------------------------------------

DRIVE_MINUTES     = 30      # bars from session open defining the drive window
DRIVE_FLAT_THRESH = 0.10    # % magnitude below which drive is classified flat
SESSION_START     = "09:30"
SESSION_END       = "15:59"

# -- Cache loader -------------------------------------------------------------

def load_ticker_cache(ticker: str) -> pd.DataFrame | None:
    """
    Load a ticker's 1-min parquet from cache.
    Returns None with a printed warning if the file is missing.
    """
    path = os.path.join(CACHE_DIR, f"{ticker}.parquet")
    if not os.path.exists(path):
        print(f"  {ticker}: WARNING - cache file not found, skipping ({path})")
        return None
    df = pd.read_parquet(path)
    return df

# -- Session analysis ---------------------------------------------------------

def analyze_session(date: datetime.date, day_df: pd.DataFrame) -> dict | None:
    """
    Analyze one session for one ticker.
    Returns a dict of baseline metrics or None if the session is too short.

    No failure/reclaim condition is applied here.
    This is the unconditional baseline characterization only.
    """
    session = day_df.between_time(SESSION_START, SESSION_END).copy()
    if len(session) < DRIVE_MINUTES + 5:
        return None

    session_open  = session["open"].iloc[0]
    session_close = session["close"].iloc[-1]
    if session_open <= 0:
        return None

    # Drive window: first DRIVE_MINUTES bars
    drive_bars      = session.iloc[:DRIVE_MINUTES]
    drive_end_price = drive_bars["close"].iloc[-1]
    drive_high      = drive_bars["high"].max()
    drive_low       = drive_bars["low"].min()
    drive_volume    = drive_bars["volume"].sum()

    drive_magnitude_pct = (drive_end_price - session_open) / session_open * 100

    if drive_magnitude_pct > DRIVE_FLAT_THRESH:
        drive_direction = "drive_up"
    elif drive_magnitude_pct < -DRIVE_FLAT_THRESH:
        drive_direction = "drive_down"
    else:
        drive_direction = "flat"

    # Post-drive session range
    post_drive = session.iloc[DRIVE_MINUTES:]
    post_high  = post_drive["high"].max()  if not post_drive.empty else float("nan")
    post_low   = post_drive["low"].min()   if not post_drive.empty else float("nan")

    # Return metrics (unconditional)
    open_to_close_pct        = (session_close - session_open)  / session_open  * 100
    drive_end_to_close_pct   = (session_close - drive_end_price) / drive_end_price * 100
    session_range_pct        = (session["high"].max() - session["low"].min()) / session_open * 100

    return {
        "date":                     str(date),
        "drive_direction":           drive_direction,
        "drive_magnitude_pct":       round(drive_magnitude_pct,     4),
        "drive_high":                round(drive_high,              4),
        "drive_low":                 round(drive_low,               4),
        "drive_volume":              int(drive_volume),
        "session_open":              round(session_open,            4),
        "session_close":             round(session_close,           4),
        "open_to_close_pct":         round(open_to_close_pct,       4),
        "drive_end_to_close_pct":    round(drive_end_to_close_pct,  4),
        "session_range_pct":         round(session_range_pct,       4),
        "post_drive_high":           round(post_high,               4) if not np.isnan(post_high) else None,
        "post_drive_low":            round(post_low,                4) if not np.isnan(post_low)  else None,
        "session_bar_count":         len(session),
    }

# -- Main ---------------------------------------------------------------------

def _load_tickers_from_file(path: str) -> list[str]:
    """Read tickers from a CSV file with a 'ticker' column."""
    if not os.path.exists(path):
        print(f"ERROR: ticker file not found: {path}")
        sys.exit(1)
    df = pd.read_csv(path)
    if "ticker" not in df.columns:
        print(f"ERROR: ticker file must have a 'ticker' column. Found: {list(df.columns)}")
        sys.exit(1)
    tickers = df["ticker"].dropna().str.strip().str.upper().tolist()
    if not tickers:
        print(f"ERROR: ticker file is empty or all values are blank: {path}")
        sys.exit(1)
    return tickers


def main():
    parser = argparse.ArgumentParser(
        description="phase_r0 baseline runner — failed_opening_drive_and_reclaim"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--tickers",     nargs="+", metavar="TICKER",
                       help="One or more ticker symbols passed directly")
    group.add_argument("--ticker-file", metavar="PATH",
                       help="CSV with a 'ticker' column — overrides --tickers")
    parser.add_argument("--start",   default=DEFAULT_DATE_START, metavar="YYYY-MM-DD")
    parser.add_argument("--end",     default=DEFAULT_DATE_END,   metavar="YYYY-MM-DD")
    args = parser.parse_args()

    if args.ticker_file:
        tickers = _load_tickers_from_file(args.ticker_file)
    elif args.tickers:
        tickers = [t.upper() for t in args.tickers]
    else:
        tickers = [t.upper() for t in DEFAULT_TICKERS]
    date_start = datetime.date.fromisoformat(args.start)
    date_end   = datetime.date.fromisoformat(args.end)

    ticker_display = str(tickers) if len(tickers) <= 10 else f"{len(tickers)} tickers (first 5: {tickers[:5]})"

    print("=" * 60)
    print("phase_r0 baseline - failed_opening_drive_and_reclaim")
    print(f"Date range : {date_start} to {date_end}")
    print(f"Tickers    : {ticker_display}")
    print(f"Drive win  : {DRIVE_MINUTES} min | flat thresh: {DRIVE_FLAT_THRESH}%")
    print("Cache-only : YES")
    print("=" * 60)

    all_rows          = []
    tickers_processed = 0
    tickers_skipped   = 0
    sessions_total    = 0
    sessions_skipped  = 0

    for ticker in tickers:
        df = load_ticker_cache(ticker)
        if df is None:
            tickers_skipped += 1
            continue

        # Filter to date range
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        df.index = df.index.tz_convert("America/New_York")

        mask = (df.index.date >= date_start) & (df.index.date <= date_end)
        df   = df.loc[mask]

        if df.empty:
            print(f"  {ticker}: WARNING - no bars in date range, skipping")
            tickers_skipped += 1
            continue

        df["_date"] = df.index.date
        groups      = df.groupby("_date")
        ticker_rows = []

        for date, day_df in groups:
            sessions_total += 1
            result = analyze_session(date, day_df.drop(columns=["_date"]))
            if result is None:
                sessions_skipped += 1
                continue
            result["ticker"] = ticker
            ticker_rows.append(result)

        if ticker_rows:
            all_rows.extend(ticker_rows)
            tickers_processed += 1
            print(f"  {ticker}: {len(ticker_rows)} sessions processed")
        else:
            print(f"  {ticker}: WARNING - no valid sessions extracted")
            tickers_skipped += 1

    if not all_rows:
        print("\nERROR: no session data collected. Check cache and date range.")
        sys.exit(1)

    # -- Session detail output ------------------------------------------------

    col_order = [
        "ticker", "date", "drive_direction", "drive_magnitude_pct",
        "drive_high", "drive_low", "drive_volume",
        "session_open", "session_close",
        "open_to_close_pct", "drive_end_to_close_pct", "session_range_pct",
        "post_drive_high", "post_drive_low", "session_bar_count",
    ]
    detail_df = (
        pd.DataFrame(all_rows)[col_order]
        .sort_values(["ticker", "date"])
        .reset_index(drop=True)
    )
    detail_file = os.path.join(
        OUTPUT_DIR,
        f"research_output_failed_opening_drive_and_reclaim"
        f"__phase_r0_baseline__session_detail__{TODAY}.csv"
    )
    detail_df.to_csv(detail_file, index=False)
    print(f"\nSession detail : {detail_file}")
    print(f"  Rows         : {len(detail_df)}")

    # -- Bucket summary output ------------------------------------------------

    def bucket_stats(grp):
        rets = grp["drive_end_to_close_pct"]
        return pd.Series({
            "n_sessions":        len(grp),
            "mean_return_pct":   round(rets.mean(),   4),
            "median_return_pct": round(rets.median(), 4),
            "std_return_pct":    round(rets.std(),     4),
            "win_rate":          round((rets > 0).mean(), 4),
            "pct_10":            round(np.percentile(rets, 10), 4),
            "pct_90":            round(np.percentile(rets, 90), 4),
        })

    bucket_order = ["drive_up", "drive_down", "flat"]
    summary_df   = (
        detail_df.groupby("drive_direction")
        .apply(bucket_stats, include_groups=False)
        .reindex([b for b in bucket_order if b in detail_df["drive_direction"].unique()])
        .reset_index()
    )
    summary_file = os.path.join(
        OUTPUT_DIR,
        f"research_output_failed_opening_drive_and_reclaim"
        f"__phase_r0_baseline__bucket_summary__{TODAY}.csv"
    )
    summary_df.to_csv(summary_file, index=False)
    print(f"Bucket summary : {summary_file}")

    # -- Run info output ------------------------------------------------------

    run_info = {
        "run_date":          TODAY,
        "phase":             "phase_r0_baseline",
        "family":            "failed_opening_drive_and_reclaim",
        "cache_only":        True,
        "date_start":        str(date_start),
        "date_end":          str(date_end),
        "tickers_requested": tickers,
        "tickers_processed": tickers_processed,
        "tickers_skipped":   tickers_skipped,
        "sessions_attempted": sessions_total,
        "sessions_skipped":   sessions_skipped,
        "sessions_in_output": len(detail_df),
        "drive_minutes":     DRIVE_MINUTES,
        "drive_flat_thresh_pct": DRIVE_FLAT_THRESH,
        "output_dir":        OUTPUT_DIR,
    }
    run_info_file = os.path.join(
        OUTPUT_DIR,
        f"research_output_failed_opening_drive_and_reclaim"
        f"__phase_r0_baseline__run_info__{TODAY}.txt"
    )
    with open(run_info_file, "w") as f:
        json.dump(run_info, f, indent=2)
    print(f"Run info       : {run_info_file}")

    # -- Console summary ------------------------------------------------------

    print()
    print("Bucket summary (drive_end_to_close_pct):")
    print(f"{'Direction':<14} {'N':>5} {'Mean%':>8} {'Median%':>9} {'WinRate':>9} {'P10':>8} {'P90':>8}")
    print("-" * 65)
    for _, row in summary_df.iterrows():
        print(
            f"{row['drive_direction']:<14} {int(row['n_sessions']):>5} "
            f"{row['mean_return_pct']:>8.3f} {row['median_return_pct']:>9.3f} "
            f"{row['win_rate']:>9.3f} {row['pct_10']:>8.3f} {row['pct_90']:>8.3f}"
        )

    print(f"\nDone. Tickers processed: {tickers_processed}  Skipped: {tickers_skipped}")
    print(f"      Sessions in output: {len(detail_df)}  Skipped: {sessions_skipped}")


if __name__ == "__main__":
    main()
