"""
research_run_phase_r1_failed_drive_condition.py
Track:  intraday_same_day
Family: failed_opening_drive_and_reclaim
Phase:  phase_r1 — conditional behavior

Purpose:
  Test the first failure condition against the phase_r0 unconditional baseline.
  Isolates sessions where the opening drive definitively fails — defined as the
  stock trading back through the session open price at any point after the drive
  window — and measures what happens to price from that failure point to close.

Condition tested (parent_001 — drive_failure_through_open):
  A session qualifies as a "failed drive" if, at any point after bar DRIVE_MINUTES,
  any 1-minute bar's CLOSE crosses back through the session open price:
    drive_up  failed: post-drive bar close <= session_open
    drive_down failed: post-drive bar close >= session_open

  The failure event is the first such bar. Its close becomes the entry reference price
  for measuring the post-failure return.

Why session open as the failure threshold:
  - Session open is the structural reference level that the drive departed from.
  - A close back through session open means the entire drive is negated.
  - It is a deterministic, non-fitted level — no parameter tuning required.
  - It is widely tracked by market participants, making it behaviorally meaningful.

What this script measures:
  For each session (drive_up or drive_down, excluding flat):
    - drive_failed: bool — did the stock come back through session open post-drive?
    - failure_bar_minutes: how many minutes into the session the failure occurred
    - post_failure_to_close_pct: (session_close - failure_bar_close) / failure_bar_close × 100
      This is the return FROM the failure event TO close — the core conditional return.
    - open_to_close_pct: full session return (for reference)
    - drive_end_to_close_pct: post-drive return (for comparison with phase_r0 baseline)

Decision logic:
  - Compare post_failure_to_close_pct distribution (failed sessions) against
    drive_end_to_close_pct from phase_r0 baseline (all sessions).
  - If the conditioned distribution shows meaningful, non-trivial lift (or suppression)
    above the baseline, the condition is worth advancing to phase_r2.
  - If failed-drive sessions look the same as all-drive sessions, reject the condition.

Outputs (written to research_outputs/family_lineages/failed_opening_drive_and_reclaim/phase_r1_failed_drive_condition/):
  research_output_...__phase_r1__session_detail__<DATE>.csv
  research_output_...__phase_r1__bucket_summary__<DATE>.csv
  research_output_...__phase_r1__run_info__<DATE>.txt

Cache-only guarantee:
  All data is read from research_data_cache/intraday_1m/<TICKER>.parquet.
  The Massive provider is never called from this script.

Usage:
  # Full universe from a CSV file
  python research_run_phase_r1_failed_drive_condition.py --ticker-file path/to/tickers.csv

  # Custom tickers
  python research_run_phase_r1_failed_drive_condition.py --tickers INTC F BAC --start 2024-04-01 --end 2025-12-31

  # Custom date range
  python research_run_phase_r1_failed_drive_condition.py --ticker-file tickers.csv --start 2024-04-01 --end 2025-12-31
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
    "family_lineages", "failed_opening_drive_and_reclaim", "phase_r1_failed_drive_condition"
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

TODAY = datetime.date.today().strftime("%Y_%m_%d")

# -- Defaults -----------------------------------------------------------------

DEFAULT_DATE_START = "2024-04-01"
DEFAULT_DATE_END   = "2025-12-31"

# -- Config -------------------------------------------------------------------

DRIVE_MINUTES     = 30      # same drive window as phase_r0
DRIVE_FLAT_THRESH = 0.10    # same flat threshold as phase_r0
SESSION_START     = "09:30"
SESSION_END       = "15:59"

# -- Cache loader -------------------------------------------------------------

def load_ticker_cache(ticker: str) -> pd.DataFrame | None:
    path = os.path.join(CACHE_DIR, f"{ticker}.parquet")
    if not os.path.exists(path):
        print(f"  {ticker}: WARNING - cache file not found, skipping")
        return None
    return pd.read_parquet(path)


# -- Session analysis ---------------------------------------------------------

def analyze_session(date: datetime.date, day_df: pd.DataFrame) -> dict | None:
    """
    Analyze one session for the phase_r1 failed-drive condition.

    Computes all phase_r0 metrics plus drive_failed classification and
    post-failure return metrics. Sessions classified as 'flat' are excluded
    (no drive to fail).
    """
    session = day_df.between_time(SESSION_START, SESSION_END).copy()
    if len(session) < DRIVE_MINUTES + 5:
        return None

    session_open  = session["open"].iloc[0]
    session_close = session["close"].iloc[-1]
    if session_open <= 0:
        return None

    # -- Drive window (first DRIVE_MINUTES bars) ------------------------------

    drive_bars      = session.iloc[:DRIVE_MINUTES]
    drive_end_price = drive_bars["close"].iloc[-1]
    drive_volume    = drive_bars["volume"].sum()
    drive_magnitude_pct = (drive_end_price - session_open) / session_open * 100

    if drive_magnitude_pct > DRIVE_FLAT_THRESH:
        drive_direction = "drive_up"
    elif drive_magnitude_pct < -DRIVE_FLAT_THRESH:
        drive_direction = "drive_down"
    else:
        return None  # flat sessions excluded from phase_r1 analysis

    # -- Failure detection (post-drive bars) ----------------------------------

    post_drive = session.iloc[DRIVE_MINUTES:]
    drive_failed        = False
    failure_bar_minutes = None
    failure_bar_close   = None
    post_failure_to_close_pct = None

    for bar_offset, (bar_time, bar) in enumerate(post_drive.iterrows()):
        bar_close = bar["close"]
        failed_this_bar = False

        if drive_direction == "drive_up" and bar_close <= session_open:
            failed_this_bar = True
        elif drive_direction == "drive_down" and bar_close >= session_open:
            failed_this_bar = True

        if failed_this_bar:
            drive_failed        = True
            failure_bar_minutes = DRIVE_MINUTES + bar_offset + 1  # 1-indexed minutes from open
            failure_bar_close   = bar_close
            if failure_bar_close > 0:
                post_failure_to_close_pct = (
                    (session_close - failure_bar_close) / failure_bar_close * 100
                )
            break

    # -- Standard return metrics ----------------------------------------------

    open_to_close_pct      = (session_close - session_open) / session_open * 100
    drive_end_to_close_pct = (session_close - drive_end_price) / drive_end_price * 100
    session_range_pct      = (session["high"].max() - session["low"].min()) / session_open * 100

    return {
        "date":                        str(date),
        "drive_direction":             drive_direction,
        "drive_magnitude_pct":         round(drive_magnitude_pct,            4),
        "drive_volume":                int(drive_volume),
        "session_open":                round(session_open,                   4),
        "session_close":               round(session_close,                  4),
        "drive_end_price":             round(drive_end_price,                4),
        # -- Failure classification
        "drive_failed":                drive_failed,
        "failure_bar_minutes":         failure_bar_minutes,        # None if not failed
        "failure_bar_close":           round(failure_bar_close, 4) if failure_bar_close else None,
        # -- Return metrics
        "post_failure_to_close_pct":   round(post_failure_to_close_pct, 4)  if post_failure_to_close_pct is not None else None,
        "open_to_close_pct":           round(open_to_close_pct,          4),
        "drive_end_to_close_pct":      round(drive_end_to_close_pct,     4),
        "session_range_pct":           round(session_range_pct,          4),
        "session_bar_count":           len(session),
    }


# -- Bucket statistics --------------------------------------------------------

def bucket_stats(grp: pd.DataFrame, return_col: str) -> pd.Series:
    rets = grp[return_col].dropna()
    if len(rets) == 0:
        return pd.Series({
            "n_sessions":   0, "mean_return_pct": None, "median_return_pct": None,
            "std_return_pct": None, "win_rate": None, "pct_10": None, "pct_90": None,
        })
    return pd.Series({
        "n_sessions":        len(rets),
        "mean_return_pct":   round(rets.mean(),                4),
        "median_return_pct": round(rets.median(),              4),
        "std_return_pct":    round(rets.std(),                 4),
        "win_rate":          round((rets > 0).mean(),          4),
        "pct_10":            round(np.percentile(rets, 10),    4),
        "pct_90":            round(np.percentile(rets, 90),    4),
    })


# -- Ticker loading helpers ---------------------------------------------------

def _load_tickers_from_file(path: str) -> list[str]:
    if not os.path.exists(path):
        print(f"ERROR: ticker file not found: {path}")
        sys.exit(1)
    df = pd.read_csv(path)
    if "ticker" not in df.columns:
        print(f"ERROR: CSV must have a 'ticker' column. Found: {list(df.columns)}")
        sys.exit(1)
    tickers = df["ticker"].dropna().str.strip().str.upper().tolist()
    if not tickers:
        print(f"ERROR: ticker file is empty: {path}")
        sys.exit(1)
    return tickers


# -- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="phase_r1 failed-drive condition runner — failed_opening_drive_and_reclaim"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--tickers",     nargs="+", metavar="TICKER")
    group.add_argument("--ticker-file", metavar="PATH")
    parser.add_argument("--start", default=DEFAULT_DATE_START, metavar="YYYY-MM-DD")
    parser.add_argument("--end",   default=DEFAULT_DATE_END,   metavar="YYYY-MM-DD")
    args = parser.parse_args()

    if args.ticker_file:
        tickers = _load_tickers_from_file(args.ticker_file)
    elif args.tickers:
        tickers = [t.upper() for t in args.tickers]
    else:
        print("ERROR: provide --ticker-file or --tickers")
        sys.exit(1)

    date_start = datetime.date.fromisoformat(args.start)
    date_end   = datetime.date.fromisoformat(args.end)

    ticker_display = (
        str(tickers) if len(tickers) <= 10
        else f"{len(tickers)} tickers (first 5: {tickers[:5]})"
    )
    print("=" * 65)
    print("phase_r1 — failed_drive_condition — failed_opening_drive_and_reclaim")
    print(f"Date range   : {date_start} to {date_end}")
    print(f"Tickers      : {ticker_display}")
    print(f"Drive window : {DRIVE_MINUTES} min | flat thresh: {DRIVE_FLAT_THRESH}%")
    print(f"Condition    : drive reverses back through session open post-drive")
    print("Cache-only   : YES")
    print("=" * 65)

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
        ticker_rows = []

        for date, day_df in df.groupby("_date"):
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
            failed_count = sum(1 for r in ticker_rows if r["drive_failed"])
            print(f"  {ticker}: {len(ticker_rows)} sessions | {failed_count} failed drives "
                  f"({100*failed_count/len(ticker_rows):.1f}%)")
        else:
            print(f"  {ticker}: WARNING - no valid sessions extracted")
            tickers_skipped += 1

    if not all_rows:
        print("\nERROR: no session data collected.")
        sys.exit(1)

    # -- Build detail dataframe -----------------------------------------------

    col_order = [
        "ticker", "date", "drive_direction", "drive_magnitude_pct", "drive_volume",
        "session_open", "session_close", "drive_end_price",
        "drive_failed", "failure_bar_minutes", "failure_bar_close",
        "post_failure_to_close_pct",
        "open_to_close_pct", "drive_end_to_close_pct", "session_range_pct",
        "session_bar_count",
    ]
    detail_df = (
        pd.DataFrame(all_rows)[col_order]
        .sort_values(["ticker", "date"])
        .reset_index(drop=True)
    )

    detail_file = os.path.join(
        OUTPUT_DIR,
        f"research_output_failed_opening_drive_and_reclaim"
        f"__phase_r1__session_detail__{TODAY}.csv"
    )
    detail_df.to_csv(detail_file, index=False)
    print(f"\nSession detail : {detail_file}  ({len(detail_df)} rows)")

    # -- Build bucket summary -------------------------------------------------

    # Four buckets: drive_up / drive_down, each split by failed vs continued
    records = []
    for direction in ["drive_up", "drive_down"]:
        dir_df = detail_df[detail_df["drive_direction"] == direction]
        failed_df    = dir_df[dir_df["drive_failed"] == True]
        continued_df = dir_df[dir_df["drive_failed"] == False]

        # Overall (phase_r0 comparable): drive_end_to_close_pct for all sessions
        all_stats = bucket_stats(dir_df, "drive_end_to_close_pct")
        all_stats["bucket"]        = f"{direction}__all_sessions"
        all_stats["failure_rate"]  = round(len(failed_df) / len(dir_df), 4) if len(dir_df) else None
        all_stats["return_basis"]  = "drive_end_to_close"
        records.append(all_stats.to_dict())

        # Failed drives: post_failure_to_close_pct (core conditional measurement)
        failed_stats = bucket_stats(failed_df, "post_failure_to_close_pct")
        failed_stats["bucket"]       = f"{direction}__drive_failed"
        failed_stats["failure_rate"] = None
        failed_stats["return_basis"] = "post_failure_to_close"
        records.append(failed_stats.to_dict())

        # Continued drives: drive_end_to_close_pct (drives that did NOT fail)
        cont_stats = bucket_stats(continued_df, "drive_end_to_close_pct")
        cont_stats["bucket"]       = f"{direction}__drive_continued"
        cont_stats["failure_rate"] = None
        cont_stats["return_basis"] = "drive_end_to_close"
        records.append(cont_stats.to_dict())

    col_order_summary = [
        "bucket", "return_basis", "failure_rate",
        "n_sessions", "mean_return_pct", "median_return_pct",
        "std_return_pct", "win_rate", "pct_10", "pct_90",
    ]
    summary_df = pd.DataFrame(records)[col_order_summary]

    summary_file = os.path.join(
        OUTPUT_DIR,
        f"research_output_failed_opening_drive_and_reclaim"
        f"__phase_r1__bucket_summary__{TODAY}.csv"
    )
    summary_df.to_csv(summary_file, index=False)
    print(f"Bucket summary : {summary_file}")

    # -- Run info -------------------------------------------------------------

    total_sessions    = len(detail_df)
    total_failed      = detail_df["drive_failed"].sum()
    overall_fail_rate = total_failed / total_sessions if total_sessions else 0

    run_info = {
        "run_date":               TODAY,
        "phase":                  "phase_r1_failed_drive_condition",
        "family":                 "failed_opening_drive_and_reclaim",
        "condition":              "drive_reverses_through_session_open",
        "cache_only":             True,
        "date_start":             str(date_start),
        "date_end":               str(date_end),
        "drive_minutes":          DRIVE_MINUTES,
        "drive_flat_thresh_pct":  DRIVE_FLAT_THRESH,
        "tickers_requested":      len(tickers),
        "tickers_processed":      tickers_processed,
        "tickers_skipped":        tickers_skipped,
        "sessions_attempted":     sessions_total,
        "sessions_skipped":       sessions_skipped,
        "sessions_in_output":     total_sessions,
        "sessions_drive_failed":  int(total_failed),
        "overall_failure_rate":   round(overall_fail_rate, 4),
        "output_dir":             OUTPUT_DIR,
    }
    run_info_file = os.path.join(
        OUTPUT_DIR,
        f"research_output_failed_opening_drive_and_reclaim"
        f"__phase_r1__run_info__{TODAY}.txt"
    )
    with open(run_info_file, "w") as f:
        json.dump(run_info, f, indent=2)
    print(f"Run info       : {run_info_file}")

    # -- Console summary ------------------------------------------------------

    print()
    print("=" * 65)
    print("PHASE_R1 RESULTS — drive_failure_through_open")
    print("=" * 65)
    print(f"{'Bucket':<35} {'N':>6} {'Mean%':>7} {'WinRate':>8} {'P10':>7} {'P90':>7}")
    print("-" * 65)
    for _, row in summary_df.iterrows():
        if row["n_sessions"] == 0:
            continue
        fail_str = f"  [fail_rate={row['failure_rate']:.2f}]" if row["failure_rate"] is not None else ""
        print(
            f"{row['bucket']:<35}{fail_str}"
        )
        print(
            f"  basis={row['return_basis']:<25} "
            f"{int(row['n_sessions']):>6} {row['mean_return_pct']:>7.3f} "
            f"{row['win_rate']:>8.3f} {row['pct_10']:>7.3f} {row['pct_90']:>7.3f}"
        )

    print(f"\nOverall drive failure rate: {overall_fail_rate:.1%} "
          f"({int(total_failed)}/{total_sessions} directional sessions)")
    print(f"\nDone. Tickers processed: {tickers_processed}  Skipped: {tickers_skipped}")
    print(f"      Sessions in output: {total_sessions}  Skipped: {sessions_skipped}")


if __name__ == "__main__":
    main()
