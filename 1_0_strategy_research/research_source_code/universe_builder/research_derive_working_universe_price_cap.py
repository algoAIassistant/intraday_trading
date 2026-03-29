"""
research_derive_working_universe_price_cap.py
Side:  research -- universe builder layer

Purpose:
  Derive a price-capped working research universe from the broad shared master
  universe and the locally cached daily price data.

  NOTE ON SCOPE SEPARATION:
    - shared_master_symbol_list_us_common_stocks.csv  = BROAD canonical registry
      This file is never modified by this script.
    - research_working_universe_price_cap_100usd.csv  = DERIVED research scope
      This file reflects tickers whose most-recent cached daily close is <= cap.

  Why price-capping is done here (not in the universe builder):
    The shared master universe is a market-structure definition.
    Price is a time-varying observable. Applying a price filter inside the
    universe builder would embed a point-in-time decision into a structural file.
    Instead, the working universe is re-derived from current daily cache each time
    research scope needs to be updated.

Price cap logic:
  For each ticker in the shared master universe:
    1. Check whether a daily parquet exists in research_data_cache/daily/.
    2. If yes, read the most recent available close price.
    3. Accept the ticker into the working universe if close <= PRICE_CAP_USD.
    4. Tickers with no cache file are listed as uncached (not included).

Outputs (written to 1_0_strategy_research/research_configs/):
  research_working_universe_price_cap_100usd__<DATE>.csv   (dated snapshot)
  research_working_universe_price_cap_100usd.csv           (canonical current)

  Columns: ticker, name, primary_exchange, latest_close, latest_close_date

Usage:
  python research_derive_working_universe_price_cap.py

  Optional overrides:
  --cap 50.0          use a different price cap
  --start-date ...    filter: only use close prices on or after this date

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
UNIVERSE_CSV = os.path.join(
    REPO_ROOT,
    "0_1_shared_master_universe", "shared_symbol_lists",
    "shared_master_symbol_list_us_common_stocks.csv"
)
OUTPUT_DIR   = os.path.join(REPO_ROOT, "1_0_strategy_research", "research_configs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

TODAY = datetime.date.today().strftime("%Y_%m_%d")

# -- Default cap --------------------------------------------------------------

DEFAULT_PRICE_CAP = 100.0

# -- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Derive price-capped working research universe from daily cache"
    )
    parser.add_argument("--cap",        type=float, default=DEFAULT_PRICE_CAP,
                        metavar="USD",  help="Max close price to include (default: 100.0)")
    parser.add_argument("--start-date", default=None, metavar="YYYY-MM-DD",
                        help="Use only close prices on or after this date")
    args = parser.parse_args()

    cap = args.cap
    cap_label = str(int(cap)) if cap == int(cap) else str(cap)

    print("=" * 60)
    print("research_derive_working_universe_price_cap")
    print(f"NOTE: shared master universe stays BROAD and is not modified")
    print(f"NOTE: this derives a price-capped research working universe")
    print(f"Price cap      : <= {cap} USD")
    print(f"Close date min : {args.start_date or 'any (most recent available)'}")
    print(f"Daily cache    : {DAILY_DIR}")
    print("=" * 60)

    # -- Load shared master universe ------------------------------------------

    if not os.path.exists(UNIVERSE_CSV):
        print(f"ERROR: canonical shared universe not found: {UNIVERSE_CSV}")
        sys.exit(1)
    universe_df = pd.read_csv(UNIVERSE_CSV)
    print(f"\nShared master universe: {len(universe_df)} tickers (broad, unfiltered)")

    # -- Scan daily cache for latest close ------------------------------------

    start_date_filter = (
        datetime.date.fromisoformat(args.start_date) if args.start_date else None
    )

    accepted   = []
    over_cap   = []
    no_cache   = []
    no_data    = []

    for _, row in universe_df.iterrows():
        ticker = row["ticker"]
        path   = os.path.join(DAILY_DIR, f"{ticker}.parquet")

        if not os.path.exists(path):
            no_cache.append(ticker)
            continue

        try:
            df = pd.read_parquet(path, columns=["close"])
            if df.empty:
                no_data.append(ticker)
                continue

            if start_date_filter is not None:
                df = df[df.index.date >= start_date_filter]
                if df.empty:
                    no_data.append(ticker)
                    continue

            latest_close      = float(df["close"].iloc[-1])
            latest_close_date = str(df.index[-1].date())

            if latest_close <= cap:
                accepted.append({
                    "ticker":            ticker,
                    "name":              row.get("name", ""),
                    "primary_exchange":  row.get("primary_exchange", ""),
                    "latest_close":      round(latest_close, 4),
                    "latest_close_date": latest_close_date,
                })
            else:
                over_cap.append(ticker)

        except Exception as exc:
            print(f"  {ticker}: read error - {exc}")
            no_data.append(ticker)

    # -- Summary counts -------------------------------------------------------

    print(f"\nClassification:")
    print(f"  Accepted (<= {cap} USD) : {len(accepted)}")
    print(f"  Over cap (> {cap} USD)  : {len(over_cap)}")
    print(f"  No daily cache          : {len(no_cache)}")
    print(f"  Cache present but empty : {len(no_data)}")
    print(f"  Total input             : {len(universe_df)}")

    if not accepted:
        print("\nERROR: no tickers accepted - check cache build status.")
        sys.exit(1)

    # -- Write outputs --------------------------------------------------------

    out_df = pd.DataFrame(accepted).sort_values("ticker").reset_index(drop=True)

    # Dated snapshot
    dated_name = f"research_working_universe_price_cap_{cap_label}usd__{TODAY}.csv"
    dated_file = os.path.join(OUTPUT_DIR, dated_name)
    out_df.to_csv(dated_file, index=False)
    print(f"\nDated snapshot  -> {dated_file}")

    # Canonical current
    canon_name = f"research_working_universe_price_cap_{cap_label}usd.csv"
    canon_file = os.path.join(OUTPUT_DIR, canon_name)
    out_df.to_csv(canon_file, index=False)
    print(f"Canonical copy  -> {canon_file}")

    # -- Exchange breakdown ---------------------------------------------------

    print(f"\nExchange breakdown (working universe, {len(out_df)} tickers):")
    for exch, cnt in out_df["primary_exchange"].value_counts().items():
        print(f"  {exch:<8}: {cnt}")

    if no_cache:
        print(f"\nNo-cache tickers: {len(no_cache)} (run research_build_daily_cache.py to fill)")

    print("\nDone.")


if __name__ == "__main__":
    main()
