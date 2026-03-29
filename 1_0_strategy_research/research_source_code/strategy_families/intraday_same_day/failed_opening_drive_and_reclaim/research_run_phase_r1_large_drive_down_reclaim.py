"""
research_run_phase_r1_large_drive_down_reclaim.py
Track:  intraday_same_day
Family: failed_opening_drive_and_reclaim
Phase:  phase_r1 — parent_002: large drive_down + early reclaim

Purpose:
  Tests the magnitude-conditioned failure condition derived from parent_001 analysis.
  parent_001 showed that unconditional drive failure has no edge, but drive_down sessions
  where the initial drive was large (abs magnitude >= LARGE_DRIVE_THRESH) AND price
  subsequently reclaims the session open show a consistent positive mean return.

  parent_001 finding (111 tickers, 2025-07-01 to 2025-12-31):
    All drive_down failures:          n=3255, mean=+0.019%, win=48.8%  (marginal)
    Large drive_down failures (>= 2%): n=325,  mean=+0.289%, win=53.8%  (signal)
    Early reclaim (within ~60 bars):   n=60,   mean=+0.700%, win=58.3%  (stronger)

  This script tests:
    1. drive_down session
    2. Initial 30-minute drive magnitude >= LARGE_DRIVE_THRESH (default 2.0%)
    3. Post-drive price reclaims session_open (any post-drive bar closes >= session_open)
    4. Optional: reclaim occurs within EARLY_RECLAIM_MAX_BAR bars of drive end

Condition entry point:
  Entry is measured from the failure (reclaim) bar close, toward session close.
  Metric: post_failure_to_close_pct = (session_close - failure_bar_close) / failure_bar_close * 100

Outputs (written to research_outputs/family_lineages/failed_opening_drive_and_reclaim/phase_r1_large_drive_down_reclaim/):
  research_output_failed_opening_drive_and_reclaim__phase_r1_parent002__session_detail__<DATE>.csv
  research_output_failed_opening_drive_and_reclaim__phase_r1_parent002__bucket_summary__<DATE>.csv
  research_output_failed_opening_drive_and_reclaim__phase_r1_parent002__run_info__<DATE>.txt

Cache-only guarantee:
  All data read from research_data_cache/intraday_1m/<TICKER>.parquet.
  Missing cache files are skipped with a logged warning.

Usage:
  python research_run_phase_r1_large_drive_down_reclaim.py \\
    --ticker-file path/to/tickers.csv --start 2025-07-01 --end 2025-12-31

  python research_run_phase_r1_large_drive_down_reclaim.py \\
    --tickers AAPL MSFT NVDA --start 2025-07-01 --end 2025-12-31

  Optional overrides:
    --large-drive-thresh 2.0    minimum abs drive magnitude % (default 2.0)
    --early-reclaim-max  60     max bar number for early-reclaim flag (default 60, 0 = disabled)
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
    "family_lineages", "failed_opening_drive_and_reclaim", "phase_r1_large_drive_down_reclaim"
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

TODAY = datetime.date.today().strftime("%Y_%m_%d")

# -- Defaults (smoke run) -----------------------------------------------------

DEFAULT_TICKERS    = ["AAPL", "MSFT", "NVDA"]
DEFAULT_DATE_START = "2025-07-01"
DEFAULT_DATE_END   = "2025-12-31"

# -- Config -------------------------------------------------------------------

DRIVE_MINUTES        = 30      # bars from session open defining the drive window
DRIVE_FLAT_THRESH    = 0.10    # % magnitude below which drive is classified flat
DEFAULT_LARGE_THRESH = 2.0     # minimum abs drive_magnitude_pct to qualify as large
DEFAULT_EARLY_MAX    = 60      # bar index threshold for early-reclaim classification (0 = no split)
SESSION_START        = "09:30"
SESSION_END          = "15:59"

# -- Cache loader -------------------------------------------------------------

def load_ticker_cache(ticker: str) -> pd.DataFrame | None:
    path = os.path.join(CACHE_DIR, f"{ticker}.parquet")
    if not os.path.exists(path):
        print(f"  {ticker}: WARNING - cache file not found, skipping")
        return None
    return pd.read_parquet(path)

# -- Session analysis ---------------------------------------------------------

def analyze_session(
    date: datetime.date,
    day_df: pd.DataFrame,
    large_drive_thresh: float,
    early_reclaim_max: int,
) -> dict | None:
    """
    Analyze one session. Returns a row dict if conditions are met, else None.

    Condition chain:
      1. Valid session with enough bars
      2. drive_down with abs magnitude >= large_drive_thresh
      3. Price reclaims session_open post-drive (any bar close >= session_open)

    Output row includes:
      - All session metadata
      - failure_bar_minutes (bar index where reclaim occurs)
      - post_failure_to_close_pct (entry from reclaim bar close to session close)
      - early_reclaim flag (True if failure_bar_minutes <= early_reclaim_max)
    """
    session = day_df.between_time(SESSION_START, SESSION_END).copy()
    if len(session) < DRIVE_MINUTES + 5:
        return None

    session_open  = session["open"].iloc[0]
    session_close = session["close"].iloc[-1]
    if session_open <= 0:
        return None

    # Drive window
    drive_bars          = session.iloc[:DRIVE_MINUTES]
    drive_end_price     = drive_bars["close"].iloc[-1]
    drive_magnitude_pct = (drive_end_price - session_open) / session_open * 100

    # Must be a large downward drive
    if drive_magnitude_pct >= -DRIVE_FLAT_THRESH:
        return None  # not drive_down
    if abs(drive_magnitude_pct) < large_drive_thresh:
        return None  # drive too small

    # Post-drive: look for reclaim of session_open
    post_drive = session.iloc[DRIVE_MINUTES:]
    drive_failed        = False
    failure_bar_minutes = None
    failure_bar_close   = None

    for bar_offset, (bar_time, bar) in enumerate(post_drive.iterrows()):
        if bar["close"] >= session_open:
            drive_failed        = True
            failure_bar_minutes = DRIVE_MINUTES + bar_offset + 1
            failure_bar_close   = bar["close"]
            break

    if not drive_failed:
        # Drive did not reclaim — record as continued (no entry signal)
        return {
            "date":                   str(date),
            "condition_met":          False,
            "drive_magnitude_pct":    round(drive_magnitude_pct, 4),
            "drive_volume":           int(drive_bars["volume"].sum()),
            "session_open":           round(session_open, 4),
            "session_close":          round(session_close, 4),
            "failure_bar_minutes":    None,
            "failure_bar_close":      None,
            "post_failure_to_close_pct": None,
            "early_reclaim":          None,
            "drive_end_to_close_pct": round((session_close - drive_end_price) / drive_end_price * 100, 4),
            "open_to_close_pct":      round((session_close - session_open) / session_open * 100, 4),
            "session_range_pct":      round((session["high"].max() - session["low"].min()) / session_open * 100, 4),
        }

    # Condition met: large drive_down that reclaimed open
    post_fail_pct = (session_close - failure_bar_close) / failure_bar_close * 100
    early_reclaim = (early_reclaim_max > 0) and (failure_bar_minutes <= early_reclaim_max)

    return {
        "date":                   str(date),
        "condition_met":          True,
        "drive_magnitude_pct":    round(drive_magnitude_pct, 4),
        "drive_volume":           int(drive_bars["volume"].sum()),
        "session_open":           round(session_open, 4),
        "session_close":          round(session_close, 4),
        "failure_bar_minutes":    int(failure_bar_minutes),
        "failure_bar_close":      round(failure_bar_close, 4),
        "post_failure_to_close_pct": round(post_fail_pct, 4),
        "early_reclaim":          bool(early_reclaim),
        "drive_end_to_close_pct": round((session_close - drive_end_price) / drive_end_price * 100, 4),
        "open_to_close_pct":      round((session_close - session_open) / session_open * 100, 4),
        "session_range_pct":      round((session["high"].max() - session["low"].min()) / session_open * 100, 4),
    }

# -- Stats helper -------------------------------------------------------------

def _bucket_stats(rets: pd.Series) -> dict:
    n = len(rets)
    if n == 0:
        return {"n": 0, "mean": None, "median": None, "std": None, "win_rate": None,
                "p10": None, "p90": None, "t_stat": None}
    mean   = rets.mean()
    median = rets.median()
    std    = rets.std(ddof=1)
    win    = (rets > 0).mean()
    p10    = np.percentile(rets, 10)
    p90    = np.percentile(rets, 90)
    t_stat = mean / (std / np.sqrt(n)) if std > 0 else 0.0
    return {
        "n":        n,
        "mean":     round(mean,   4),
        "median":   round(median, 4),
        "std":      round(std,    4),
        "win_rate": round(win,    4),
        "p10":      round(p10,    4),
        "p90":      round(p90,    4),
        "t_stat":   round(t_stat, 3),
    }

# -- Ticker file loader -------------------------------------------------------

def _load_tickers_from_file(path: str) -> list[str]:
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

# -- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="phase_r1 parent_002 — large drive_down reclaim — failed_opening_drive_and_reclaim"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--tickers",     nargs="+", metavar="TICKER")
    group.add_argument("--ticker-file", metavar="PATH")
    parser.add_argument("--start",               default=DEFAULT_DATE_START, metavar="YYYY-MM-DD")
    parser.add_argument("--end",                 default=DEFAULT_DATE_END,   metavar="YYYY-MM-DD")
    parser.add_argument("--large-drive-thresh",  type=float, default=DEFAULT_LARGE_THRESH,
                        help="Minimum abs drive magnitude %% to qualify (default %(default)s)")
    parser.add_argument("--early-reclaim-max",   type=int,   default=DEFAULT_EARLY_MAX,
                        help="Bar index for early-reclaim split (0 = disable, default %(default)s)")
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

    print("=" * 65)
    print("phase_r1 parent_002 — large drive_down reclaim")
    print(f"Date range         : {date_start} to {date_end}")
    print(f"Tickers            : {ticker_display}")
    print(f"Drive window       : {DRIVE_MINUTES} min | flat thresh: {DRIVE_FLAT_THRESH}%")
    print(f"Large drive thresh : >= {args.large_drive_thresh}% abs magnitude")
    print(f"Early reclaim max  : bar {args.early_reclaim_max} {'(disabled)' if args.early_reclaim_max == 0 else ''}")
    print("Cache-only         : YES")
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
            row = analyze_session(date, day_df.drop(columns=["_date"]),
                                  args.large_drive_thresh, args.early_reclaim_max)
            if row is None:
                sessions_skipped += 1
                continue
            row["ticker"] = ticker
            ticker_rows.append(row)

        if ticker_rows:
            all_rows.extend(ticker_rows)
            tickers_processed += 1
            cond_count = sum(1 for r in ticker_rows if r["condition_met"])
            print(f"  {ticker}: {len(ticker_rows)} large_down sessions | {cond_count} reclaimed ({cond_count/len(ticker_rows):.0%})")
        else:
            tickers_skipped += 1

    if not all_rows:
        print("\nERROR: no session data collected. Check cache and date range.")
        sys.exit(1)

    # -- Output ---------------------------------------------------------------

    col_order = [
        "ticker", "date", "condition_met",
        "drive_magnitude_pct", "drive_volume",
        "session_open", "session_close",
        "failure_bar_minutes", "failure_bar_close",
        "post_failure_to_close_pct", "early_reclaim",
        "drive_end_to_close_pct", "open_to_close_pct", "session_range_pct",
    ]
    detail_df = (
        pd.DataFrame(all_rows)[col_order]
        .sort_values(["ticker", "date"])
        .reset_index(drop=True)
    )

    detail_file = os.path.join(
        OUTPUT_DIR,
        f"research_output_failed_opening_drive_and_reclaim"
        f"__phase_r1_parent002__session_detail__{TODAY}.csv"
    )
    detail_df.to_csv(detail_file, index=False)
    print(f"\nSession detail : {detail_file}  ({len(detail_df)} rows)")

    # -- Bucket summary -------------------------------------------------------

    cond_df    = detail_df[detail_df["condition_met"] == True]
    no_cond_df = detail_df[detail_df["condition_met"] == False]

    buckets = []

    # All large_down (condition met + not met): drive_end_to_close baseline
    all_rets = detail_df["drive_end_to_close_pct"].dropna()
    b = _bucket_stats(all_rets)
    b["bucket"] = "large_drive_down__all"
    b["basis"]  = "drive_end_to_close"
    buckets.append(b)

    # Condition not met (drive continued — never reclaimed open)
    cont_rets = no_cond_df["drive_end_to_close_pct"].dropna()
    b = _bucket_stats(cont_rets)
    b["bucket"] = "large_drive_down__drive_continued"
    b["basis"]  = "drive_end_to_close"
    buckets.append(b)

    # Condition met: all reclaims
    reclaim_rets = cond_df["post_failure_to_close_pct"].dropna()
    b = _bucket_stats(reclaim_rets)
    b["bucket"] = "large_drive_down__reclaimed__all"
    b["basis"]  = "post_failure_to_close"
    buckets.append(b)

    # Condition met: early reclaim
    if args.early_reclaim_max > 0:
        early_df   = cond_df[cond_df["early_reclaim"] == True]
        early_rets = early_df["post_failure_to_close_pct"].dropna()
        b = _bucket_stats(early_rets)
        b["bucket"] = f"large_drive_down__reclaimed__early_lte{args.early_reclaim_max}"
        b["basis"]  = "post_failure_to_close"
        buckets.append(b)

        # Late reclaim
        late_df   = cond_df[cond_df["early_reclaim"] == False]
        late_rets = late_df["post_failure_to_close_pct"].dropna()
        b = _bucket_stats(late_rets)
        b["bucket"] = f"large_drive_down__reclaimed__late_gt{args.early_reclaim_max}"
        b["basis"]  = "post_failure_to_close"
        buckets.append(b)

    # Magnitude sub-buckets for reclaimed sessions
    if len(cond_df) > 0:
        for lo, hi in [(2.0, 3.0), (3.0, 5.0), (5.0, 99.0)]:
            sub = cond_df[(cond_df["drive_magnitude_pct"].abs() >= lo) &
                          (cond_df["drive_magnitude_pct"].abs() < hi)]
            if len(sub) > 0:
                b = _bucket_stats(sub["post_failure_to_close_pct"].dropna())
                b["bucket"] = f"large_drive_down__reclaimed__mag{lo:.0f}to{hi:.0f}"
                b["basis"]  = "post_failure_to_close"
                buckets.append(b)

    summary_df = pd.DataFrame(buckets)[["bucket", "basis", "n", "mean", "median", "std", "win_rate", "p10", "p90", "t_stat"]]
    summary_file = os.path.join(
        OUTPUT_DIR,
        f"research_output_failed_opening_drive_and_reclaim"
        f"__phase_r1_parent002__bucket_summary__{TODAY}.csv"
    )
    summary_df.to_csv(summary_file, index=False)
    print(f"Bucket summary : {summary_file}")

    # -- Run info -------------------------------------------------------------

    run_info = {
        "run_date":               TODAY,
        "phase":                  "phase_r1_parent002",
        "family":                 "failed_opening_drive_and_reclaim",
        "cache_only":             True,
        "date_start":             str(date_start),
        "date_end":               str(date_end),
        "tickers_processed":      tickers_processed,
        "tickers_skipped":        tickers_skipped,
        "sessions_attempted":     sessions_total,
        "sessions_skipped":       sessions_skipped,
        "sessions_in_output":     len(detail_df),
        "condition_met_count":    int(detail_df["condition_met"].sum()),
        "condition_not_met_count": int((detail_df["condition_met"] == False).sum()),
        "drive_minutes":          DRIVE_MINUTES,
        "drive_flat_thresh_pct":  DRIVE_FLAT_THRESH,
        "large_drive_thresh_pct": args.large_drive_thresh,
        "early_reclaim_max_bar":  args.early_reclaim_max,
        "output_dir":             OUTPUT_DIR,
    }
    run_info_file = os.path.join(
        OUTPUT_DIR,
        f"research_output_failed_opening_drive_and_reclaim"
        f"__phase_r1_parent002__run_info__{TODAY}.csv"
    )
    with open(run_info_file, "w") as f:
        json.dump(run_info, f, indent=2)
    print(f"Run info       : {run_info_file}")

    # -- Console summary ------------------------------------------------------

    reclaim_rate = len(cond_df) / len(detail_df) if detail_df is not None and len(detail_df) > 0 else 0.0

    print()
    print("=" * 65)
    print(f"PARENT_002 RESULTS — large drive_down reclaim (thresh={args.large_drive_thresh}%)")
    print("=" * 65)
    print(f"{'Bucket':<52} {'N':>5} {'Mean%':>7} {'WinR':>6} {'t':>6}")
    print("-" * 65)
    for _, row in summary_df.iterrows():
        if row["n"] == 0:
            continue
        print(f"  {row['bucket']:<50} {int(row['n']):>5} {row['mean']:>7.3f} {row['win_rate']:>6.3f} {row['t_stat']:>6.2f}")

    print(f"\nLarge drive_down sessions total : {len(detail_df)}")
    print(f"  Reclaimed open (cond met)     : {len(cond_df)} ({reclaim_rate:.1%})")
    print(f"  Drive continued (cond not met): {len(no_cond_df)}")
    print(f"\nDone. Tickers processed: {tickers_processed}  Skipped: {tickers_skipped}")


if __name__ == "__main__":
    main()
