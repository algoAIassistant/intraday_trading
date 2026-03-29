"""
engineering_build_regime_map.py

Builds (or refreshes) the precomputed regime map CSV used by the RegimeGate.

Regime definition (from frozen research):
    Universe-average daily open-to-close (OTC) return, averaged by calendar month.
    Bearish = monthly average <= -0.10%.
    Non-bearish = monthly average > -0.10%.

Data source:
    Research daily cache (research_data_cache/daily/*.parquet).
    Each parquet file contains one ticker's daily OHLCV data with a tz-aware
    DatetimeIndex (America/New_York). Daily OTC = (close - open) / open * 100.

Output:
    engineering_configs/engineering_regime_map__<YYYY_MM_DD>.csv
    Columns: year_month, universe_avg_otc, regime, n_tickers, is_partial_month

Usage:
    python engineering_build_regime_map.py
    python engineering_build_regime_map.py --ticker-file path/to/universe.csv
    python engineering_build_regime_map.py --output-dir engineering_configs

The output file path is printed to stdout on success. Update the YAML config's
regime_map_path to point to the new file.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths — relative to 2_0_agent_engineering/ (the engineering root)
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
_ENGINEERING_ROOT = _SCRIPT_DIR.parent.parent          # 2_0_agent_engineering/
_REPO_ROOT = _ENGINEERING_ROOT.parent                  # repo root

_DEFAULT_DAILY_CACHE = _REPO_ROOT / "1_0_strategy_research" / "research_data_cache" / "daily"
_DEFAULT_TICKER_FILE = _REPO_ROOT / "1_0_strategy_research" / "research_configs" / "research_working_universe_intraday_liquid.csv"
_DEFAULT_OUTPUT_DIR  = _ENGINEERING_ROOT / "engineering_configs"

_BEARISH_THRESHOLD = -0.10   # monthly OTC <= this = bearish


def build_regime_map(
    daily_cache_dir: Path,
    ticker_list: list[str],
    bearish_threshold: float = _BEARISH_THRESHOLD,
) -> pd.DataFrame:
    """
    Compute universe-average monthly OTC from daily cache files.

    Returns DataFrame with columns:
        year_month        : e.g. "2024-03"
        universe_avg_otc  : float, universe-average monthly OTC in percent
        regime            : "bearish" or "non_bearish"
        n_tickers         : number of tickers contributing to this month
        is_partial_month  : True if the month is not yet fully complete
    """
    today = datetime.date.today()
    all_daily_otc: list[pd.Series] = []
    loaded = 0
    skipped = 0

    for ticker in ticker_list:
        path = daily_cache_dir / f"{ticker}.parquet"
        if not path.exists():
            skipped += 1
            continue
        try:
            df = pd.read_parquet(path)
        except Exception as e:
            print(f"  Warning: could not read {path.name}: {e}")
            skipped += 1
            continue

        # Normalise tz
        if df.index.tz is None:
            df.index = pd.to_datetime(df.index).tz_localize("UTC").tz_convert("America/New_York")
        elif str(df.index.tz) != "America/New_York":
            df.index = df.index.tz_convert("America/New_York")

        if "open" not in df.columns or "close" not in df.columns:
            skipped += 1
            continue

        otc = (df["close"] - df["open"]) / df["open"] * 100.0
        otc.index = pd.DatetimeIndex(otc.index)
        all_daily_otc.append(otc)
        loaded += 1

    if not all_daily_otc:
        raise RuntimeError("No valid daily cache files found.")

    print(f"  Loaded {loaded} tickers ({skipped} skipped).")

    # Concatenate all tickers, sort by date, compute monthly universe average
    combined = pd.concat(all_daily_otc)
    combined.index = pd.DatetimeIndex(combined.index)
    monthly = combined.groupby(combined.index.to_period("M"))

    # Also compute per-month ticker count
    ticker_counts = (
        pd.concat(all_daily_otc, keys=range(len(all_daily_otc)))
        .reset_index(level=0, drop=True)
    )
    ticker_counts.index = pd.DatetimeIndex(ticker_counts.index)
    monthly_n = ticker_counts.groupby(ticker_counts.index.to_period("M")).apply(
        lambda x: x.index.normalize().nunique()
    )

    rows = []
    for period, avg_otc in monthly.mean().items():
        month_start = period.to_timestamp()
        month_end   = period.to_timestamp("M")

        # A month is partial if today falls within it (month not fully elapsed)
        is_partial = month_end.date() >= today

        regime = "bearish" if avg_otc <= bearish_threshold else "non_bearish"
        n_days = monthly_n.get(period, 0)

        rows.append({
            "year_month":       str(period),
            "universe_avg_otc": round(float(avg_otc), 4),
            "regime":           regime,
            "n_tickers":        loaded,
            "is_partial_month": is_partial,
        })

    df_out = pd.DataFrame(rows).sort_values("year_month").reset_index(drop=True)
    return df_out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build/refresh regime map CSV for the RegimeGate."
    )
    parser.add_argument(
        "--ticker-file",
        default=str(_DEFAULT_TICKER_FILE),
        help="CSV with a 'ticker' column (default: research liquid universe).",
    )
    parser.add_argument(
        "--daily-cache",
        default=str(_DEFAULT_DAILY_CACHE),
        help="Directory of daily parquet files.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(_DEFAULT_OUTPUT_DIR),
        help="Directory to write the regime map CSV.",
    )
    parser.add_argument(
        "--bearish-threshold",
        type=float,
        default=_BEARISH_THRESHOLD,
        help="Monthly OTC threshold below which a month is bearish (default -0.10).",
    )
    parser.add_argument(
        "--start-month",
        default=None,
        help="Include months from this period onward, e.g. '2024-03' (default: all).",
    )
    args = parser.parse_args()

    daily_cache_dir = Path(args.daily_cache)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load ticker list
    ticker_path = Path(args.ticker_file)
    if not ticker_path.exists():
        print(f"Error: ticker file not found: {ticker_path}")
        sys.exit(1)
    universe_df = pd.read_csv(ticker_path)
    if "ticker" not in universe_df.columns:
        print(f"Error: ticker file must have a 'ticker' column. Found: {list(universe_df.columns)}")
        sys.exit(1)
    tickers = universe_df["ticker"].dropna().tolist()
    print(f"Building regime map from {len(tickers)} tickers...")
    print(f"Daily cache: {daily_cache_dir}")

    df_regime = build_regime_map(
        daily_cache_dir=daily_cache_dir,
        ticker_list=tickers,
        bearish_threshold=args.bearish_threshold,
    )

    # Optionally filter to start_month onward
    if args.start_month:
        df_regime = df_regime[df_regime["year_month"] >= args.start_month].reset_index(drop=True)

    # Print summary
    non_bearish = (df_regime["regime"] == "non_bearish").sum()
    bearish = (df_regime["regime"] == "bearish").sum()
    partial = df_regime["is_partial_month"].sum()
    print(f"\nRegime map: {len(df_regime)} months — {non_bearish} non-bearish, {bearish} bearish, {partial} partial")
    print()
    print(f"  {'Month':<10} {'avg_otc':>8}  regime          partial")
    print(f"  {'-'*10} {'-'*8}  {'-'*15} {'-'*7}")
    for _, row in df_regime.iterrows():
        marker = " <-- BEARISH" if row["regime"] == "bearish" else ""
        partial_tag = " [partial]" if row["is_partial_month"] else ""
        print(f"  {row['year_month']:<10} {row['universe_avg_otc']:>+.3f}%  {row['regime']:<15}{partial_tag}{marker}")

    # Write output
    today_str = datetime.date.today().strftime("%Y_%m_%d")
    out_path = output_dir / f"engineering_regime_map__{today_str}.csv"
    df_regime.to_csv(out_path, index=False)
    print(f"\nRegime map written: {out_path}")
    print(f"Update regime_map_path in your config YAML to: {out_path}")


if __name__ == "__main__":
    main()
