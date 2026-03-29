"""
research_run_child_001_price_filtered_regime_gated.py
Track:  intraday_same_day
Family: failed_opening_drive_and_reclaim
Phase:  phase_r2 child_001 — locked validation

Purpose:
  Locked validation for child_001: the narrowed, regime-gated branch derived from parent_002.

  parent_002 phase_r2 findings:
    - Signal (t=2.33) is real but concentrated in $10-20 stocks and completely inverts
      in bearish market months (Oct 2025 only at the time: mean=-1.028%, t=-3.27).
    - $10-20 ex-bearish: n=170, mean=+1.256%, win=61.2%, t=4.11

  Locked child_001 condition:
    1. drive_down with abs magnitude >= 2.0% in first 30 minutes
    2. session_open in $5-20 price range
    3. Price reclaims session_open post-drive (any post-drive bar close >= session_open)
    4. Market regime: non-bearish month (universe-avg open_to_close > BEARISH_THRESH)

  Regime definition:
    - Universe-avg monthly OTC computed from all extended-cache tickers in the analysis window
    - Bearish = universe_avg_otc_monthly < BEARISH_THRESH (default -0.10%)
    - Non-bearish = bearish months excluded from analysis

Outputs (written to research_outputs/family_lineages/failed_opening_drive_and_reclaim/child_001_price_filtered_regime_gated/):
  ...__session_detail__<DATE>.csv
  ...__bucket_summary__<DATE>.csv
  ...__regime_map__<DATE>.csv
  ...__run_info__<DATE>.txt

Usage:
  python research_run_child_001_price_filtered_regime_gated.py \\
    --ticker-file path/to/tickers.csv --start 2024-03-25 --end 2025-12-31

  python research_run_child_001_price_filtered_regime_gated.py \\
    --tickers AAPL MSFT NVDA --start 2024-03-25 --end 2025-12-31

Optional overrides:
  --large-drive-thresh  2.0      minimum abs drive magnitude % (default 2.0)
  --price-min           5.0      minimum session open price (default 5.0)
  --price-max          20.0      maximum session open price (default 20.0)
  --bearish-thresh     -0.10     monthly universe-avg OTC below which month = bearish (default -0.10)
  --early-reclaim-max   60       bar index for early-reclaim flag (0 = disabled)
  --regime-ticker-file  PATH     CSV with tickers used for regime computation (defaults to same as analysis tickers)
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
    "family_lineages", "failed_opening_drive_and_reclaim", "child_001_price_filtered_regime_gated"
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

TODAY = datetime.date.today().strftime("%Y_%m_%d")

# -- Defaults -----------------------------------------------------------------

DEFAULT_DATE_START   = "2024-03-25"
DEFAULT_DATE_END     = "2025-12-31"
DEFAULT_LARGE_THRESH = 2.0
DEFAULT_PRICE_MIN    = 5.0
DEFAULT_PRICE_MAX    = 20.0
DEFAULT_BEARISH_THRESH = -0.10   # universe-avg monthly OTC below this = bearish
DEFAULT_EARLY_MAX    = 60

# -- Drive config (must match family constants) --------------------------------

DRIVE_MINUTES     = 30
DRIVE_FLAT_THRESH = 0.10
SESSION_START     = "09:30"
SESSION_END       = "15:59"

# -- Cache loader -------------------------------------------------------------

def _safe_cache_path(ticker: str) -> str:
    _WIN_RESERVED = {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    }
    stem = f"{ticker}__reserved" if ticker.upper() in _WIN_RESERVED else ticker
    return os.path.join(CACHE_DIR, f"{stem}.parquet")


def load_ticker_cache(ticker: str, date_start: datetime.date, date_end: datetime.date) -> pd.DataFrame | None:
    path = _safe_cache_path(ticker)
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert("America/New_York")
    mask = (df.index.date >= date_start) & (df.index.date <= date_end)
    df = df.loc[mask]
    if df.empty:
        return None
    return df

# -- Regime computation -------------------------------------------------------

def build_regime_map(
    tickers: list[str],
    date_start: datetime.date,
    date_end: datetime.date,
    bearish_thresh: float,
) -> pd.DataFrame:
    """
    Compute universe-average open_to_close by month.
    Returns DataFrame with columns: year_month, universe_avg_otc, regime
    where regime is 'bearish' or 'non_bearish'.
    """
    all_daily = []
    n_used = 0
    for ticker in tickers:
        df = load_ticker_cache(ticker, date_start, date_end)
        if df is None:
            continue
        session = df.between_time(SESSION_START, SESSION_END)
        daily_open  = session.groupby(session.index.date)["open"].first()
        daily_close = session.groupby(session.index.date)["close"].last()
        otc = (daily_close - daily_open) / daily_open * 100
        all_daily.append(otc)
        n_used += 1

    if not all_daily:
        raise RuntimeError("Could not compute regime map: no valid cache files found")

    combined = pd.concat(all_daily)
    combined.index = pd.to_datetime(combined.index)
    monthly_avg = combined.groupby(combined.index.to_period("M")).mean()

    rows = []
    for month, avg_otc in monthly_avg.items():
        rows.append({
            "year_month":       str(month),
            "universe_avg_otc": round(avg_otc, 4),
            "regime":           "bearish" if avg_otc < bearish_thresh else "non_bearish",
        })

    print(f"\nRegime map computed from {n_used} tickers:")
    print(f"  {'Month':<10} {'avg_otc':>8}  regime")
    for r in rows:
        marker = " <-- EXCLUDED" if r["regime"] == "bearish" else ""
        print(f"  {r['year_month']:<10} {r['universe_avg_otc']:>+.3f}%  {r['regime']}{marker}")

    return pd.DataFrame(rows)

# -- Session analysis ---------------------------------------------------------

def analyze_session(
    date: datetime.date,
    day_df: pd.DataFrame,
    large_drive_thresh: float,
    price_min: float,
    price_max: float,
    early_reclaim_max: int,
) -> dict | None:
    """
    Analyze one session with price filter applied before drive analysis.
    Returns a result dict if large drive_down found, None otherwise.
    condition_met = True only if all conditions pass (price + drive + reclaim).
    """
    session = day_df.between_time(SESSION_START, SESSION_END).copy()
    if len(session) < DRIVE_MINUTES + 5:
        return None

    session_open  = session["open"].iloc[0]
    session_close = session["close"].iloc[-1]
    if session_open <= 0:
        return None

    # Price filter — applied first to avoid unnecessary drive computation
    if session_open < price_min or session_open > price_max:
        return None

    # Drive window
    drive_bars          = session.iloc[:DRIVE_MINUTES]
    drive_end_price     = drive_bars["close"].iloc[-1]
    drive_magnitude_pct = (drive_end_price - session_open) / session_open * 100

    # Must be a large downward drive
    if drive_magnitude_pct >= -DRIVE_FLAT_THRESH:
        return None
    if abs(drive_magnitude_pct) < large_drive_thresh:
        return None

    # Post-drive: look for reclaim of session_open
    post_drive          = session.iloc[DRIVE_MINUTES:]
    drive_failed        = False
    failure_bar_minutes = None
    failure_bar_close   = None

    for bar_offset, (_, bar) in enumerate(post_drive.iterrows()):
        if bar["close"] >= session_open:
            drive_failed        = True
            failure_bar_minutes = DRIVE_MINUTES + bar_offset + 1
            failure_bar_close   = bar["close"]
            break

    base_row = {
        "date":                str(date),
        "drive_magnitude_pct": round(drive_magnitude_pct, 4),
        "drive_volume":        int(drive_bars["volume"].sum()),
        "session_open":        round(session_open, 4),
        "session_close":       round(session_close, 4),
        "drive_end_to_close_pct": round((session_close - drive_end_price) / drive_end_price * 100, 4),
        "open_to_close_pct":   round((session_close - session_open) / session_open * 100, 4),
        "session_range_pct":   round((session["high"].max() - session["low"].min()) / session_open * 100, 4),
    }

    if not drive_failed:
        return {**base_row,
                "condition_met": False,
                "failure_bar_minutes": None,
                "failure_bar_close":   None,
                "post_failure_to_close_pct": None,
                "early_reclaim":       None}

    post_fail_pct = (session_close - failure_bar_close) / failure_bar_close * 100
    early_reclaim = (early_reclaim_max > 0) and (failure_bar_minutes <= early_reclaim_max)

    return {**base_row,
            "condition_met":             True,
            "failure_bar_minutes":       int(failure_bar_minutes),
            "failure_bar_close":         round(failure_bar_close, 4),
            "post_failure_to_close_pct": round(post_fail_pct, 4),
            "early_reclaim":             bool(early_reclaim)}

# -- Stats helper -------------------------------------------------------------

def _bucket_stats(rets: pd.Series, label: str = "") -> dict:
    n = len(rets)
    if n == 0:
        return {"bucket": label, "n": 0, "mean": None, "median": None, "std": None,
                "win_rate": None, "p10": None, "p90": None, "t_stat": None}
    mean   = rets.mean()
    median = rets.median()
    std    = rets.std(ddof=1)
    win    = (rets > 0).mean()
    p10    = np.percentile(rets, 10)
    p90    = np.percentile(rets, 90)
    t_stat = mean / (std / np.sqrt(n)) if std > 0 else 0.0
    return {
        "bucket":   label,
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
        description="child_001 locked validation — price-filtered + regime-gated"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--tickers",     nargs="+", metavar="TICKER")
    group.add_argument("--ticker-file", metavar="PATH")
    parser.add_argument("--start",               default=DEFAULT_DATE_START, metavar="YYYY-MM-DD")
    parser.add_argument("--end",                 default=DEFAULT_DATE_END,   metavar="YYYY-MM-DD")
    parser.add_argument("--large-drive-thresh",  type=float, default=DEFAULT_LARGE_THRESH)
    parser.add_argument("--price-min",           type=float, default=DEFAULT_PRICE_MIN)
    parser.add_argument("--price-max",           type=float, default=DEFAULT_PRICE_MAX)
    parser.add_argument("--bearish-thresh",      type=float, default=DEFAULT_BEARISH_THRESH)
    parser.add_argument("--early-reclaim-max",   type=int,   default=DEFAULT_EARLY_MAX)
    parser.add_argument("--regime-ticker-file",  metavar="PATH", default=None,
                        help="Separate ticker file for regime computation (default: same as analysis tickers)")
    args = parser.parse_args()

    if args.ticker_file:
        tickers = _load_tickers_from_file(args.ticker_file)
    elif args.tickers:
        tickers = [t.upper() for t in args.tickers]
    else:
        print("ERROR: provide --ticker-file or --tickers")
        sys.exit(1)

    regime_tickers = (
        _load_tickers_from_file(args.regime_ticker_file)
        if args.regime_ticker_file else tickers
    )

    date_start = datetime.date.fromisoformat(args.start)
    date_end   = datetime.date.fromisoformat(args.end)

    print("=" * 68)
    print("child_001 locked validation — price-filtered + regime-gated")
    print(f"Date range         : {date_start} to {date_end}")
    print(f"Tickers            : {len(tickers)}")
    print(f"Drive window       : {DRIVE_MINUTES} min | flat thresh: {DRIVE_FLAT_THRESH}%")
    print(f"Drive thresh       : >= {args.large_drive_thresh}% abs magnitude")
    print(f"Price filter       : session_open ${args.price_min:.0f}–${args.price_max:.0f}")
    print(f"Bearish threshold  : universe_avg_otc < {args.bearish_thresh}%")
    print(f"Early reclaim max  : bar {args.early_reclaim_max}")
    print("=" * 68)

    # -- Step 1: Build regime map ------------------------------------------------
    regime_df  = build_regime_map(regime_tickers, date_start, date_end, args.bearish_thresh)
    bearish_set = set(regime_df[regime_df["regime"] == "bearish"]["year_month"].tolist())
    print(f"\nBearish months excluded ({len(bearish_set)}): {sorted(bearish_set)}")

    # -- Step 2: Collect sessions ------------------------------------------------
    all_rows          = []
    tickers_processed = 0
    tickers_skipped   = 0

    for ticker in tickers:
        df = load_ticker_cache(ticker, date_start, date_end)
        if df is None:
            tickers_skipped += 1
            continue

        df["_date"] = df.index.date
        ticker_rows = []

        for date, day_df in df.groupby("_date"):
            # Regime gate: skip bearish months
            year_month = pd.Timestamp(date).strftime("%Y-%m")
            if year_month in bearish_set:
                continue

            row = analyze_session(
                date, day_df.drop(columns=["_date"]),
                args.large_drive_thresh, args.price_min, args.price_max,
                args.early_reclaim_max,
            )
            if row is None:
                continue
            row["ticker"]     = ticker
            row["year_month"] = year_month
            ticker_rows.append(row)

        if ticker_rows:
            all_rows.extend(ticker_rows)
            tickers_processed += 1
        else:
            tickers_skipped += 1

    if not all_rows:
        print("\nERROR: no session data collected. Check cache, date range, and price filter.")
        sys.exit(1)

    # -- Step 3: Outputs ---------------------------------------------------------

    col_order = [
        "ticker", "date", "year_month", "condition_met",
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

    prefix = "research_output_failed_opening_drive_and_reclaim__child001"
    detail_df.to_csv(os.path.join(OUTPUT_DIR, f"{prefix}__session_detail__{TODAY}.csv"), index=False)
    regime_df.to_csv(os.path.join(OUTPUT_DIR, f"{prefix}__regime_map__{TODAY}.csv"),    index=False)

    # -- Step 4: Bucket stats ----------------------------------------------------

    cond_df    = detail_df[detail_df["condition_met"] == True]
    no_cond_df = detail_df[detail_df["condition_met"] == False]
    reclaim_rets = cond_df["post_failure_to_close_pct"].dropna()

    buckets = []

    # All large_down (price-filtered, regime-gated)
    buckets.append(_bucket_stats(detail_df["drive_end_to_close_pct"].dropna(),
                                 "large_down__price_gated__regime_gated__all"))
    # Drive continued
    buckets.append(_bucket_stats(no_cond_df["drive_end_to_close_pct"].dropna(),
                                 "large_down__drive_continued"))
    # Reclaimed — all
    buckets.append(_bucket_stats(reclaim_rets,
                                 "large_down__reclaimed__all"))
    # Reclaimed — early / late
    if args.early_reclaim_max > 0:
        buckets.append(_bucket_stats(
            cond_df[cond_df["early_reclaim"] == True]["post_failure_to_close_pct"].dropna(),
            f"large_down__reclaimed__early_lte{args.early_reclaim_max}"))
        buckets.append(_bucket_stats(
            cond_df[cond_df["early_reclaim"] == False]["post_failure_to_close_pct"].dropna(),
            f"large_down__reclaimed__late_gt{args.early_reclaim_max}"))

    # Price sub-buckets within $5-20
    for lo, hi in [(5.0, 10.0), (10.0, 15.0), (15.0, 20.0)]:
        sub = cond_df[(cond_df["session_open"] >= lo) & (cond_df["session_open"] < hi)]
        buckets.append(_bucket_stats(sub["post_failure_to_close_pct"].dropna(),
                                     f"large_down__reclaimed__price_{lo:.0f}to{hi:.0f}"))

    # Magnitude sub-buckets
    for lo, hi in [(2.0, 3.0), (3.0, 5.0), (5.0, 99.0)]:
        sub = cond_df[(cond_df["drive_magnitude_pct"].abs() >= lo) &
                      (cond_df["drive_magnitude_pct"].abs() < hi)]
        if len(sub) > 0:
            buckets.append(_bucket_stats(sub["post_failure_to_close_pct"].dropna(),
                                         f"large_down__reclaimed__mag_{lo:.0f}to{hi:.0f}"))

    # Monthly breakdown (reclaimed only)
    if len(cond_df) > 0:
        for ym, grp in cond_df.groupby("year_month"):
            rets = grp["post_failure_to_close_pct"].dropna()
            buckets.append(_bucket_stats(rets, f"monthly__{ym}"))

    summary_df = pd.DataFrame(buckets)[["bucket", "n", "mean", "median", "std", "win_rate", "p10", "p90", "t_stat"]]
    summary_df.to_csv(os.path.join(OUTPUT_DIR, f"{prefix}__bucket_summary__{TODAY}.csv"), index=False)

    # -- Step 5: Concentration analysis ------------------------------------------

    ticker_returns = (
        cond_df.groupby("ticker")["post_failure_to_close_pct"]
        .agg(["sum", "count", lambda x: (x > 0).mean()])
        .rename(columns={"sum": "total_return", "count": "n_events", "<lambda_0>": "win_rate"})
        .sort_values("total_return", ascending=False)
    )
    total_pos_return = ticker_returns[ticker_returns["total_return"] > 0]["total_return"].sum()
    top5_share  = ticker_returns.head(5)["total_return"].sum() / total_pos_return if total_pos_return > 0 else 0
    top10_share = ticker_returns.head(10)["total_return"].sum() / total_pos_return if total_pos_return > 0 else 0
    pct_positive_tickers = (ticker_returns["total_return"] > 0).mean()

    # -- Step 6: Run info --------------------------------------------------------

    run_info = {
        "run_date":           TODAY,
        "phase":              "child_001_locked_validation",
        "family":             "failed_opening_drive_and_reclaim",
        "date_start":         str(date_start),
        "date_end":           str(date_end),
        "tickers_processed":  tickers_processed,
        "tickers_skipped":    tickers_skipped,
        "bearish_months_excluded": sorted(bearish_set),
        "total_sessions_in_output": len(detail_df),
        "condition_met_count":      int(detail_df["condition_met"].sum()),
        "condition_not_met_count":  int((detail_df["condition_met"] == False).sum()),
        "price_min":          args.price_min,
        "price_max":          args.price_max,
        "bearish_thresh":     args.bearish_thresh,
        "large_drive_thresh": args.large_drive_thresh,
        "early_reclaim_max":  args.early_reclaim_max,
    }
    with open(os.path.join(OUTPUT_DIR, f"{prefix}__run_info__{TODAY}.txt"), "w") as f:
        json.dump(run_info, f, indent=2)

    # -- Console output ----------------------------------------------------------

    reclaim_rate = len(cond_df) / len(detail_df) if len(detail_df) > 0 else 0

    print()
    print("=" * 68)
    print("CHILD_001 LOCKED VALIDATION RESULTS")
    print(f"Price filter: ${args.price_min:.0f}–${args.price_max:.0f} | Non-bearish months only")
    print("=" * 68)
    main_buckets = [b for b in buckets if b["bucket"].startswith("large_down__reclaimed__all")
                    or b["bucket"].startswith("large_down__reclaimed__early")
                    or b["bucket"].startswith("large_down__reclaimed__late")]
    print(f"\n{'Bucket':<56} {'N':>5} {'Mean%':>7} {'Win':>6} {'t':>6}")
    print("-" * 68)
    for b in buckets:
        if b["n"] == 0:
            continue
        if not (b["bucket"].startswith("large_down__") or b["bucket"].startswith("monthly__")):
            continue
        print(f"  {b['bucket']:<54} {b['n']:>5} {b['mean']:>+7.3f} {b['win_rate']:>6.3f} {b['t_stat']:>+6.2f}")

    print()
    print(f"Large drive_down sessions (price-gated, non-bearish): {len(detail_df)}")
    print(f"  Reclaimed open (condition met)   : {len(cond_df)} ({reclaim_rate:.1%})")
    print(f"  Drive continued (no reclaim)     : {len(no_cond_df)}")
    print()
    print(f"Concentration (reclaimed sessions):")
    print(f"  Top-5  tickers : {top5_share:.1%} of total return")
    print(f"  Top-10 tickers : {top10_share:.1%} of total return")
    print(f"  Tickers positive: {pct_positive_tickers:.1%}")
    print()
    print(f"Tickers processed: {tickers_processed}  |  Skipped: {tickers_skipped}")
    print(f"Outputs: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
