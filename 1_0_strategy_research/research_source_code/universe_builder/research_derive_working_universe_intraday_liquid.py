"""
research_derive_working_universe_intraday_liquid.py
Side:  research -- universe builder layer

Purpose:
  From the price-capped working universe, derive a liquid intraday subset
  suitable for intraday research (e.g., phase_r0 baseline studies).

  Filtering criteria applied (in order):
    1. Price >= MIN_CLOSE_USD  (exclude penny stocks)
    2. Price <= cap from input CSV (already applied by upstream script)
    3. Average daily volume >= MIN_AVG_VOLUME over the last AVG_VOLUME_LOOKBACK_DAYS
       in the daily cache
    4. Sort by average volume descending, keep top TOP_N tickers

  Input:
    research_configs/research_working_universe_price_cap_100usd.csv
    (produced by research_derive_working_universe_price_cap.py)

  Outputs (written to research_configs/):
    research_working_universe_intraday_liquid__<DATE>.csv  (dated snapshot)
    research_working_universe_intraday_liquid.csv          (canonical current)

    Columns: ticker, name, primary_exchange, latest_close, avg_volume

Usage:
  python research_derive_working_universe_intraday_liquid.py

  Optional overrides:
  --input PATH          use a different price-capped universe CSV
  --min-price 5.0       minimum close price (default 5.0)
  --min-volume 500000   minimum average daily volume (default 500,000)
  --lookback 252        number of most recent trading days for volume avg
  --top-n 300           max tickers to include (default 300)

Dependencies:
  pip install pandas pyarrow
"""

import os
import sys
import argparse
import datetime
import pandas as pd

# -- Paths --------------------------------------------------------------------

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT    = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
DAILY_DIR    = os.path.join(REPO_ROOT, "1_0_strategy_research", "research_data_cache", "daily")
CONFIG_DIR   = os.path.join(REPO_ROOT, "1_0_strategy_research", "research_configs")
DEFAULT_INPUT = os.path.join(CONFIG_DIR, "research_working_universe_price_cap_100usd.csv")

os.makedirs(CONFIG_DIR, exist_ok=True)

TODAY = datetime.date.today().strftime("%Y_%m_%d")

# -- Defaults -----------------------------------------------------------------

DEFAULT_MIN_PRICE  = 5.0
DEFAULT_MIN_VOLUME = 500_000
DEFAULT_LOOKBACK   = 252
DEFAULT_TOP_N      = 300

# -- Windows reserved filename guard ------------------------------------------

_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def _daily_cache_path(ticker: str) -> str:
    stem = f"{ticker}__reserved" if ticker.upper() in _WIN_RESERVED else ticker
    return os.path.join(DAILY_DIR, f"{stem}.parquet")


# -- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Derive liquid intraday research universe from price-capped working universe"
    )
    parser.add_argument("--input",      default=DEFAULT_INPUT,   metavar="PATH",
                        help="Price-capped universe CSV (must have 'ticker' and 'latest_close' columns)")
    parser.add_argument("--min-price",  type=float, default=DEFAULT_MIN_PRICE,  metavar="USD")
    parser.add_argument("--min-volume", type=int,   default=DEFAULT_MIN_VOLUME, metavar="SHARES")
    parser.add_argument("--lookback",   type=int,   default=DEFAULT_LOOKBACK,   metavar="DAYS")
    parser.add_argument("--top-n",      type=int,   default=DEFAULT_TOP_N,      metavar="N")
    args = parser.parse_args()

    print("=" * 60)
    print("research_derive_working_universe_intraday_liquid")
    print(f"Input universe : {args.input}")
    print(f"Min price      : >= {args.min_price} USD")
    print(f"Min avg volume : >= {args.min_volume:,} shares/day")
    print(f"Volume lookback: last {args.lookback} trading days")
    print(f"Top N          : {args.top_n}")
    print("=" * 60)

    # -- Load price-capped universe -------------------------------------------

    if not os.path.exists(args.input):
        print(f"ERROR: input file not found: {args.input}")
        print("  Run research_derive_working_universe_price_cap.py first.")
        sys.exit(1)

    universe_df = pd.read_csv(args.input)
    print(f"\nInput universe: {len(universe_df)} tickers")

    # -- Apply minimum price filter -------------------------------------------

    before = len(universe_df)
    universe_df = universe_df[universe_df["latest_close"] >= args.min_price]
    print(f"After price >= {args.min_price} filter: {len(universe_df)} tickers "
          f"(removed {before - len(universe_df)})")

    # -- Compute average volume from daily cache ------------------------------

    print(f"\nReading daily cache for average volume ({args.lookback}-day lookback)...")
    rows = []
    n_no_cache   = 0
    n_no_volume  = 0
    n_below_vol  = 0
    n_accepted   = 0

    for i, record in enumerate(universe_df.itertuples(), 1):
        ticker = record.ticker
        path   = _daily_cache_path(ticker)

        if not os.path.exists(path):
            n_no_cache += 1
            continue

        try:
            df = pd.read_parquet(path, columns=["volume"])
            if df.empty or "volume" not in df.columns:
                n_no_volume += 1
                continue

            # Use the most recent lookback days
            recent = df.tail(args.lookback)
            avg_vol = float(recent["volume"].mean())

            if avg_vol < args.min_volume:
                n_below_vol += 1
                continue

            rows.append({
                "ticker":           ticker,
                "name":             record.name,
                "primary_exchange": record.primary_exchange,
                "latest_close":     record.latest_close,
                "avg_volume":       int(round(avg_vol)),
            })
            n_accepted += 1

        except Exception as exc:
            n_no_volume += 1
            continue

        if i % 500 == 0:
            print(f"  Processed {i}/{len(universe_df)} tickers ...", flush=True)

    print(f"\nVolume filter results:")
    print(f"  Accepted (>= {args.min_volume:,} avg shares/day) : {n_accepted}")
    print(f"  Below volume threshold                          : {n_below_vol}")
    print(f"  No daily cache                                  : {n_no_cache}")
    print(f"  Cache missing volume column or empty            : {n_no_volume}")

    if not rows:
        print("\nERROR: no tickers accepted — check cache and filters.")
        sys.exit(1)

    # -- Sort by volume, apply top-N cap --------------------------------------

    result_df = (
        pd.DataFrame(rows)
        .sort_values("avg_volume", ascending=False)
        .head(args.top_n)
        .sort_values("ticker")
        .reset_index(drop=True)
    )

    print(f"\nTop {args.top_n} by average volume: {len(result_df)} tickers selected")

    # -- Write outputs --------------------------------------------------------

    dated_name = f"research_working_universe_intraday_liquid__{TODAY}.csv"
    dated_file = os.path.join(CONFIG_DIR, dated_name)
    result_df.to_csv(dated_file, index=False)
    print(f"\nDated snapshot  -> {dated_file}")

    canon_name = "research_working_universe_intraday_liquid.csv"
    canon_file = os.path.join(CONFIG_DIR, canon_name)
    result_df.to_csv(canon_file, index=False)
    print(f"Canonical copy  -> {canon_file}")

    # -- Exchange and price breakdowns ----------------------------------------

    print(f"\nExchange breakdown ({len(result_df)} tickers):")
    for exch, cnt in result_df["primary_exchange"].value_counts().items():
        print(f"  {exch:<8}: {cnt}")

    price_bins = [5, 10, 20, 30, 50, 75, 100]
    print(f"\nPrice breakdown (latest_close):")
    for lo, hi in zip([0] + price_bins[:-1], price_bins):
        cnt = ((result_df["latest_close"] >= lo) & (result_df["latest_close"] < hi)).sum()
        if cnt > 0:
            print(f"  ${lo:>3} – ${hi:<3}: {cnt}")
    cnt = (result_df["latest_close"] >= price_bins[-1]).sum()
    if cnt > 0:
        print(f"  ${price_bins[-1]}+      : {cnt}")

    vol_min = result_df["avg_volume"].min()
    vol_max = result_df["avg_volume"].max()
    vol_med = result_df["avg_volume"].median()
    print(f"\nVolume stats (avg daily shares):")
    print(f"  Min    : {vol_min:>15,.0f}")
    print(f"  Median : {vol_med:>15,.0f}")
    print(f"  Max    : {vol_max:>15,.0f}")

    print("\nDone.")


if __name__ == "__main__":
    main()
