"""
research_derive_working_universe_plan_next_day_day_trade_candidates.py
Side:  research -- universe builder layer
Track: plan_next_day_day_trade
Phase: phase_r0__tradable_universe_foundation

Purpose:
  Build a first working candidate universe for the plan_next_day_day_trade
  research track from U.S. common stocks.

  This is not strategy discovery. This is building a practical research
  sandbox for night-before next-day planning candidates.

  Research questions answered here:
    - Which names are liquid enough for preplanned next-day execution?
    - Which names are not too cheap to be practical?
    - Which names show enough daily movement to make preset stops / targets
      realistic?
    - Which names gap frequently enough to be worth studying as plan candidates?

Design intent:
  - Transparent thresholds grouped near the top; easy to tune.
  - All metrics derived from daily cache only (no intraday dependency).
  - Diagnostic columns retained even for excluded names.
  - Score is a simple weighted composite -- not a ranking signal.
  - No stop / target / reward:risk assumptions. That belongs in later phases.

Input:
  shared_master_symbol_list_us_common_stocks.csv (from 0_1_shared_master_universe)
  Daily parquet cache under 1_0_strategy_research/research_data_cache/daily/

Outputs (written to 1_0_strategy_research/research_configs/):
  research_working_universe_plan_next_day_day_trade_candidates__<DATE>.csv
  research_working_universe_plan_next_day_day_trade_candidates.csv  (canonical)

  Output columns:
    ticker, name, primary_exchange,
    latest_close, latest_close_date,
    average_daily_volume, average_daily_dollar_volume,
    price_bucket, adv_dollar_bucket,
    recent_gap_frequency_proxy, recent_range_expansion_proxy,
    overnight_planning_suitability_score,
    include_in_working_universe, exclusion_reason

Usage:
  python research_derive_working_universe_plan_next_day_day_trade_candidates.py

  Optional overrides:
  --min-price 5.0           minimum latest close (default 5.0)
  --max-price 500.0         maximum latest close (default 500.0)
  --min-adv-dollar 5000000  minimum avg daily dollar volume (default 5_000_000)
  --min-adv-shares 300000   minimum avg daily share volume (default 300_000)
  --lookback 63             trading-day lookback for all metrics (default 63)
  --gap-threshold 0.005     fraction gap counts as gap (default 0.005 = 0.5%)

Dependencies:
  pip install pandas pyarrow
"""

import os
import sys
import argparse
import datetime
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT  = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", ".."))

DAILY_DIR   = os.path.join(REPO_ROOT, "1_0_strategy_research", "research_data_cache", "daily")
CONFIG_DIR  = os.path.join(REPO_ROOT, "1_0_strategy_research", "research_configs")
UNIVERSE_CSV = os.path.join(
    REPO_ROOT,
    "0_1_shared_master_universe", "shared_symbol_lists",
    "shared_master_symbol_list_us_common_stocks.csv",
)

os.makedirs(CONFIG_DIR, exist_ok=True)

TODAY = datetime.date.today().strftime("%Y_%m_%d")

# ---------------------------------------------------------------------------
# Default thresholds  <-- tune these without touching logic below
# ---------------------------------------------------------------------------

DEFAULT_MIN_CLOSE_USD    = 5.0          # exclude sub-$5 names
DEFAULT_MAX_CLOSE_USD    = 500.0        # exclude ultra-high-price names
DEFAULT_MIN_ADV_DOLLAR   = 5_000_000   # $5M avg daily dollar volume
DEFAULT_MIN_ADV_SHARES   = 300_000     # 300k avg daily shares
DEFAULT_LOOKBACK_DAYS    = 63          # ~3 months of trading days
DEFAULT_GAP_THRESHOLD    = 0.005       # 0.5% open vs. prev-close = gap event

# Score weights -- must sum to 1.0
SCORE_WEIGHT_ADV_DOLLAR  = 0.50
SCORE_WEIGHT_RANGE       = 0.30
SCORE_WEIGHT_GAP_FREQ    = 0.20

# Price bucket edges (USD) -- used for diagnostic bucketing only
PRICE_BUCKET_EDGES = [5, 10, 20, 40, 80, 200, 500]

# ADV dollar bucket edges -- used for diagnostic bucketing only
ADV_DOLLAR_BUCKET_EDGES = [5_000_000, 20_000_000, 50_000_000, 100_000_000]

# ---------------------------------------------------------------------------
# Windows reserved filename guard  (same pattern as other repo scripts)
# ---------------------------------------------------------------------------

_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def _daily_cache_path(ticker: str) -> str:
    stem = f"{ticker}__reserved" if ticker.upper() in _WIN_RESERVED else ticker
    return os.path.join(DAILY_DIR, f"{stem}.parquet")


# ---------------------------------------------------------------------------
# Bucketing helpers
# ---------------------------------------------------------------------------

def _price_bucket(price: float) -> str:
    edges = PRICE_BUCKET_EDGES
    if price < edges[0]:
        return f"below_{edges[0]}"
    for lo, hi in zip(edges[:-1], edges[1:]):
        if lo <= price < hi:
            return f"price_{lo}_{hi}"
    return f"price_{edges[-1]}_plus"


def _adv_dollar_bucket(adv: float) -> str:
    edges = ADV_DOLLAR_BUCKET_EDGES
    if adv < edges[0]:
        return f"adv_below_{edges[0] // 1_000_000}m"
    for lo, hi in zip(edges[:-1], edges[1:]):
        if lo <= adv < hi:
            lo_m = lo // 1_000_000
            hi_m = hi // 1_000_000
            return f"adv_{lo_m}m_{hi_m}m"
    top = edges[-1] // 1_000_000
    return f"adv_{top}m_plus"


# ---------------------------------------------------------------------------
# Per-ticker metric extraction
# ---------------------------------------------------------------------------

def _compute_metrics(ticker: str, lookback: int, gap_threshold: float) -> dict:
    """
    Returns a dict with all computed metrics for one ticker.
    Returns None if the daily cache is missing or unreadable.
    """
    path = _daily_cache_path(ticker)
    if not os.path.exists(path):
        return None

    try:
        df = pd.read_parquet(path)
    except Exception:
        return None

    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(df.columns):
        return None

    if len(df) < 5:
        return None

    # Sort by timestamp ascending (defensive)
    df = df.sort_index()

    # Latest close
    latest_close      = float(df["close"].iloc[-1])
    latest_close_date = str(df.index[-1].date())

    # Use last `lookback` rows for metric computation
    recent = df.tail(lookback).copy()

    # Average daily share volume
    avg_volume = float(recent["volume"].mean())

    # Average daily dollar volume  (close * volume as proxy)
    recent["dollar_volume"] = recent["close"] * recent["volume"]
    avg_dollar_volume = float(recent["dollar_volume"].mean())

    # Daily range as fraction of close  ((high - low) / close)
    recent["range_pct"] = (recent["high"] - recent["low"]) / recent["close"]
    avg_range_pct = float(recent["range_pct"].mean())

    # Gap frequency proxy
    #   gap = |open_t - close_{t-1}| / close_{t-1} >= gap_threshold
    #   Requires at least 2 rows; compute on `recent` only.
    if len(recent) >= 2:
        prev_close = recent["close"].shift(1)
        gap_size   = (recent["open"] - prev_close).abs() / prev_close
        gap_events = (gap_size >= gap_threshold).sum()
        # Denominator: rows with a valid prev_close (all except first)
        gap_freq = float(gap_events) / (len(recent) - 1)
    else:
        gap_freq = float("nan")

    return {
        "latest_close":                  round(latest_close, 4),
        "latest_close_date":             latest_close_date,
        "average_daily_volume":          int(round(avg_volume)),
        "average_daily_dollar_volume":   int(round(avg_dollar_volume)),
        "recent_range_expansion_proxy":  round(avg_range_pct, 6),
        "recent_gap_frequency_proxy":    round(gap_freq, 4) if not np.isnan(gap_freq) else None,
    }


# ---------------------------------------------------------------------------
# Score computation  (applied after all rows are collected)
# ---------------------------------------------------------------------------

def _add_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds overnight_planning_suitability_score to the dataframe.
    Score = weighted sum of percentile ranks on three dimensions:
      - average_daily_dollar_volume  (weight 0.50)
      - recent_range_expansion_proxy (weight 0.30)
      - recent_gap_frequency_proxy   (weight 0.20)
    Range: 0.0 (worst) to 1.0 (best).
    Rows with missing gap_freq get gap_freq treated as 0 for scoring.
    """
    gap_col = df["recent_gap_frequency_proxy"].fillna(0.0)

    rank_adv   = df["average_daily_dollar_volume"].rank(pct=True)
    rank_range = df["recent_range_expansion_proxy"].rank(pct=True)
    rank_gap   = gap_col.rank(pct=True)

    df["overnight_planning_suitability_score"] = (
        SCORE_WEIGHT_ADV_DOLLAR * rank_adv
        + SCORE_WEIGHT_RANGE    * rank_range
        + SCORE_WEIGHT_GAP_FREQ * rank_gap
    ).round(4)

    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "phase_r0: derive working candidate universe for plan_next_day_day_trade"
        )
    )
    parser.add_argument("--min-price",      type=float, default=DEFAULT_MIN_CLOSE_USD,
                        metavar="USD",   help="Minimum latest close price")
    parser.add_argument("--max-price",      type=float, default=DEFAULT_MAX_CLOSE_USD,
                        metavar="USD",   help="Maximum latest close price")
    parser.add_argument("--min-adv-dollar", type=float, default=DEFAULT_MIN_ADV_DOLLAR,
                        metavar="USD",   help="Minimum avg daily dollar volume")
    parser.add_argument("--min-adv-shares", type=int,   default=DEFAULT_MIN_ADV_SHARES,
                        metavar="SHARES", help="Minimum avg daily share volume")
    parser.add_argument("--lookback",       type=int,   default=DEFAULT_LOOKBACK_DAYS,
                        metavar="DAYS",  help="Trading-day lookback for all metrics")
    parser.add_argument("--gap-threshold",  type=float, default=DEFAULT_GAP_THRESHOLD,
                        metavar="FRAC",  help="Fractional gap size that counts as a gap event")
    args = parser.parse_args()

    print("=" * 70)
    print("research_derive_working_universe_plan_next_day_day_trade_candidates")
    print(f"Track  : plan_next_day_day_trade")
    print(f"Phase  : phase_r0__tradable_universe_foundation")
    print(f"Run date: {TODAY}")
    print("-" * 70)
    print(f"Min close             : >= ${args.min_price}")
    print(f"Max close             : <= ${args.max_price}")
    print(f"Min ADV (dollar)      : >= ${args.min_adv_dollar:,.0f}")
    print(f"Min ADV (shares)      : >= {args.min_adv_shares:,}")
    print(f"Metric lookback       : {args.lookback} trading days (~{args.lookback // 21} months)")
    print(f"Gap threshold         : {args.gap_threshold * 100:.2f}%")
    print(f"Score weights         : ADV {SCORE_WEIGHT_ADV_DOLLAR:.0%} | "
          f"Range {SCORE_WEIGHT_RANGE:.0%} | Gap {SCORE_WEIGHT_GAP_FREQ:.0%}")
    print("=" * 70)

    # -- Load shared master universe ------------------------------------------

    if not os.path.exists(UNIVERSE_CSV):
        print(f"\nERROR: shared master universe not found:\n  {UNIVERSE_CSV}")
        sys.exit(1)

    master = pd.read_csv(UNIVERSE_CSV)
    print(f"\nShared master universe loaded: {len(master)} tickers")

    # Confirm U.S. common stocks only (type == CS already ensured by upstream
    # build, but guard explicitly here)
    if "type" in master.columns:
        before = len(master)
        master = master[master["type"] == "CS"]
        print(f"After CS (common stock) type filter: {len(master)} "
              f"(removed {before - len(master)})")

    master = master.dropna(subset=["ticker"])
    master["ticker"] = master["ticker"].astype(str).str.strip()
    master = master[master["ticker"] != ""]
    tickers = master["ticker"].tolist()

    # Build a lookup from the master for name + exchange
    master_lookup = master.set_index("ticker")[["name", "primary_exchange"]].to_dict("index")

    # -- Iterate tickers and compute metrics ----------------------------------

    print(f"\nReading daily cache for {len(tickers)} tickers ...")

    all_rows = []
    n_no_cache   = 0
    n_bad_cache  = 0
    n_processed  = 0

    for i, ticker in enumerate(tickers, 1):
        info = master_lookup.get(ticker, {})
        name     = info.get("name", "")
        exchange = info.get("primary_exchange", "")

        metrics = _compute_metrics(ticker, args.lookback, args.gap_threshold)

        if metrics is None:
            n_no_cache += 1
            continue

        n_processed += 1

        # Determine inclusion and exclusion reason
        reason_parts = []

        if metrics["latest_close"] < args.min_price:
            reason_parts.append(f"close_below_{args.min_price}")
        if metrics["latest_close"] > args.max_price:
            reason_parts.append(f"close_above_{args.max_price}")
        if metrics["average_daily_dollar_volume"] < args.min_adv_dollar:
            reason_parts.append(f"adv_dollar_below_{int(args.min_adv_dollar // 1_000_000)}m")
        if metrics["average_daily_volume"] < args.min_adv_shares:
            reason_parts.append(f"adv_shares_below_{args.min_adv_shares // 1000}k")

        included = len(reason_parts) == 0
        exclusion_reason = "; ".join(reason_parts) if reason_parts else ""

        row = {
            "ticker":                          ticker,
            "name":                            name,
            "primary_exchange":                exchange,
            "latest_close":                    metrics["latest_close"],
            "latest_close_date":               metrics["latest_close_date"],
            "average_daily_volume":            metrics["average_daily_volume"],
            "average_daily_dollar_volume":     metrics["average_daily_dollar_volume"],
            "price_bucket":                    _price_bucket(metrics["latest_close"]),
            "adv_dollar_bucket":               _adv_dollar_bucket(metrics["average_daily_dollar_volume"]),
            "recent_gap_frequency_proxy":      metrics["recent_gap_frequency_proxy"],
            "recent_range_expansion_proxy":    metrics["recent_range_expansion_proxy"],
            "overnight_planning_suitability_score": None,  # filled after scoring pass
            "include_in_working_universe":     included,
            "exclusion_reason":                exclusion_reason,
        }
        all_rows.append(row)

        if i % 500 == 0:
            print(f"  Processed {i}/{len(tickers)} tickers ...", flush=True)

    print(f"\nCache read complete:")
    print(f"  Tickers with daily cache  : {n_processed}")
    print(f"  No cache or unreadable    : {n_no_cache}")

    if not all_rows:
        print("\nERROR: no rows produced -- check daily cache and thresholds.")
        sys.exit(1)

    result_df = pd.DataFrame(all_rows)

    # -- Add score (computed across all rows, not just included) --------------

    result_df = _add_score(result_df)

    # -- Filter summary -------------------------------------------------------

    included_df = result_df[result_df["include_in_working_universe"]]
    excluded_df = result_df[~result_df["include_in_working_universe"]]

    print(f"\nInclusion results:")
    print(f"  Included in working universe : {len(included_df)}")
    print(f"  Excluded                     : {len(excluded_df)}")

    if len(excluded_df) > 0:
        reason_counts = (
            excluded_df["exclusion_reason"]
            .str.split("; ")
            .explode()
            .value_counts()
        )
        print(f"\n  Exclusion reasons (tickers may have multiple):")
        for reason, cnt in reason_counts.items():
            print(f"    {reason:<45}: {cnt}")

    # -- Breakdowns for included tickers --------------------------------------

    if len(included_df) > 0:
        print(f"\nIncluded universe breakdown:")
        print(f"\n  Exchange:")
        for exch, cnt in included_df["primary_exchange"].value_counts().items():
            print(f"    {exch:<8}: {cnt}")

        print(f"\n  Price bucket:")
        for bucket, cnt in included_df["price_bucket"].value_counts().sort_index().items():
            print(f"    {bucket:<25}: {cnt}")

        print(f"\n  ADV dollar bucket:")
        for bucket, cnt in included_df["adv_dollar_bucket"].value_counts().sort_index().items():
            print(f"    {bucket:<30}: {cnt}")

        score_min = included_df["overnight_planning_suitability_score"].min()
        score_med = included_df["overnight_planning_suitability_score"].median()
        score_max = included_df["overnight_planning_suitability_score"].max()
        print(f"\n  Overnight planning suitability score (included):")
        print(f"    Min    : {score_min:.4f}")
        print(f"    Median : {score_med:.4f}")
        print(f"    Max    : {score_max:.4f}")

        gap_valid = included_df["recent_gap_frequency_proxy"].dropna()
        if len(gap_valid) > 0:
            print(f"\n  Gap frequency proxy (included, non-null):")
            print(f"    Min    : {gap_valid.min():.4f}")
            print(f"    Median : {gap_valid.median():.4f}")
            print(f"    Max    : {gap_valid.max():.4f}")

        range_vals = included_df["recent_range_expansion_proxy"].dropna()
        if len(range_vals) > 0:
            print(f"\n  Range expansion proxy (included, non-null):")
            print(f"    Min    : {range_vals.min():.4f}")
            print(f"    Median : {range_vals.median():.4f}")
            print(f"    Max    : {range_vals.max():.4f}")

    # -- Sort output: included first (by score desc), then excluded -----------

    result_df = pd.concat([
        included_df.sort_values("overnight_planning_suitability_score", ascending=False),
        excluded_df.sort_values("ticker"),
    ]).reset_index(drop=True)

    # -- Write outputs --------------------------------------------------------

    base_name = "research_working_universe_plan_next_day_day_trade_candidates"

    dated_file = os.path.join(CONFIG_DIR, f"{base_name}__{TODAY}.csv")
    canon_file = os.path.join(CONFIG_DIR, f"{base_name}.csv")

    result_df.to_csv(dated_file, index=False)
    result_df.to_csv(canon_file, index=False)

    print(f"\nOutputs written:")
    print(f"  Dated snapshot : {dated_file}")
    print(f"  Canonical copy : {canon_file}")
    print(f"  Total rows     : {len(result_df)}")
    print(f"  Included rows  : {len(included_df)}")
    print(f"  Excluded rows  : {len(excluded_df)}")
    print(f"\nDone. phase_r0__tradable_universe_foundation output complete.")


if __name__ == "__main__":
    main()
