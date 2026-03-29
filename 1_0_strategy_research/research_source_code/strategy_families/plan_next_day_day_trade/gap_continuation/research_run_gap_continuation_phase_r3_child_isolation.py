"""
research_run_gap_continuation_phase_r3_child_isolation.py
Side:   research -- strategy family layer
Track:  plan_next_day_day_trade
Family: gap_continuation
Phase:  phase_r3__child_isolation

Purpose:
  Isolate two children inside the gap_continuation family and compare them
  against each other and against the quality-filtered parent baseline.

  This phase does NOT define grandchildren, stops, targets, or execution
  templates. It answers whether a child subtype shows meaningfully better
  structural quality than the broad parent.

Children defined in this script:

  child_1: gap_continuation__liquid_trend_names
    Thesis: high-liquidity names where the gap aligns with the stock's own
    short-term trend (SMA20 position) show stronger next-day continuation
    than the broad parent because the institutional and directional bias
    behind the gap is more consistent.
    Filters (all EOD-observable on signal day):
      1. quality cap: |gap_pct| <= GAP_PCT_MAX_ABS
      2. liquidity: adv_dollar_bucket in CHILD1_LIQUID_BUCKETS
      3. trend alignment: (gap_up AND stock_close_T > stock_sma20_T)
                       OR (gap_down AND stock_close_T < stock_sma20_T)

  child_2: gap_continuation__high_rvol_names
    Thesis: gaps backed by elevated share volume (relative to recent average)
    represent events where more market participants are acting on the signal,
    potentially leading to stronger next-day follow-through.
    Filters (all EOD-observable on signal day):
      1. quality cap: |gap_pct| <= GAP_PCT_MAX_ABS
      2. RVOL proxy: signal_day_volume / prior_20d_avg_volume >= CHILD2_RVOL_MIN
         Note: prior_20d_avg_volume is computed from the 20 trading days
         BEFORE the signal day (no look-ahead). The phase_r0 universe average
         is NOT used here because it is a single point-in-time average that
         would create a time-mismatch for older events.

Inputs:
  parent event rows from phase_r2 parent baseline (CSV)
  daily cache (to compute per-ticker stock SMA20 and rolling avg volume)

Outputs (research_outputs/family_lineages/plan_next_day_day_trade/gap_continuation/phase_r3_child_isolation/):
  child_event_rows__gap_continuation__phase_r3__<DATE>.csv
    (combined rows for both children, with a 'child_name' column)
  child_summary__gap_continuation__phase_r3__<DATE>.csv
    (per-child aggregated metrics, same slices as parent summary)
  child_vs_parent_comparison__gap_continuation__phase_r3__<DATE>.csv
    (side-by-side parent vs child1 vs child2 on key metrics)
  child_yearly_summary__gap_continuation__phase_r3__<DATE>.csv
    (per-year per-child continuation and range metrics)

Usage:
  python research_run_gap_continuation_phase_r3_child_isolation.py

Dependencies:
  pip install pandas pyarrow numpy
"""

import os
import sys
import argparse
import datetime
import warnings
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT  = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", "..", "..", ".."))

DAILY_DIR  = os.path.join(REPO_ROOT, "1_0_strategy_research", "research_data_cache", "daily")
OUTPUT_DIR = os.path.join(
    REPO_ROOT,
    "1_0_strategy_research", "research_outputs",
    "family_lineages", "plan_next_day_day_trade",
    "gap_continuation", "phase_r3_child_isolation",
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

PARENT_EVENTS_CSV = os.path.join(
    REPO_ROOT,
    "1_0_strategy_research", "research_outputs",
    "family_lineages", "plan_next_day_day_trade",
    "gap_continuation", "phase_r2_parent_baseline",
    "parent_event_rows__gap_continuation__phase_r2__2026_03_27.csv",
)

TODAY = datetime.date.today().strftime("%Y_%m_%d")

# ---------------------------------------------------------------------------
# Thresholds  <-- tune here
# ---------------------------------------------------------------------------

# Data quality cap: removes cache data errors (extreme erroneous gaps)
GAP_PCT_MAX_ABS = 0.30       # 30% max absolute gap

# Child 1: gap_continuation__liquid_trend_names
CHILD1_LIQUID_BUCKETS = {"adv_20m_50m", "adv_50m_100m", "adv_100m_plus"}
CHILD1_SMA_PERIOD     = 20   # stock's own SMA period for trend alignment check

# Child 2: gap_continuation__high_rvol_names
CHILD2_RVOL_MIN      = 1.5   # signal_day_volume >= 1.5x prior rolling avg
CHILD2_RVOL_LOOKBACK = 20    # trading days to compute rolling prior avg volume

# Windows reserved filename guard
_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1","COM2","COM3","COM4","COM5","COM6","COM7","COM8","COM9",
    "LPT1","LPT2","LPT3","LPT4","LPT5","LPT6","LPT7","LPT8","LPT9",
}


def _daily_path(ticker: str) -> str:
    stem = f"{ticker}__reserved" if ticker.upper() in _WIN_RESERVED else ticker
    return os.path.join(DAILY_DIR, f"{stem}.parquet")


# ---------------------------------------------------------------------------
# Enrichment: per-ticker SMA20 and RVOL from daily cache
# ---------------------------------------------------------------------------

def _enrich_ticker(
    ticker: str,
    event_dates: set,
) -> dict[str, dict]:
    """
    For one ticker, load the daily cache and compute for each signal date
    in event_dates:
      - stock_sma20: 20-day rolling mean of close (inclusive of signal day)
      - stock_above_sma20: close > sma20 (1/0)
      - stock_rvol_20d_prior: signal_day_volume / mean(volume of prior 20 days)

    Returns a dict keyed by date string: {date_str: {sma20, above_sma20, rvol_20d_prior}}
    Returns {} if cache is unavailable or insufficient.
    """
    path = _daily_path(ticker)
    if not os.path.exists(path):
        return {}

    try:
        df = pd.read_parquet(path, columns=["close", "volume"])
    except Exception:
        return {}

    if len(df) < CHILD1_SMA_PERIOD + 2:
        return {}

    df = df.sort_index()
    if hasattr(df.index, "tz") and df.index.tz is not None:
        df.index = df.index.tz_convert("America/New_York").normalize().tz_localize(None)
    df.index = pd.to_datetime(df.index).normalize().date
    df.index.name = "date"
    df = df[~df.index.duplicated(keep="last")]

    # SMA20: rolling mean of close, inclusive of current row
    df["sma20"] = df["close"].rolling(CHILD1_SMA_PERIOD, min_periods=CHILD1_SMA_PERIOD).mean()
    df["stock_above_sma20"] = (df["close"] > df["sma20"]).astype("Int8")

    # RVOL prior: rolling mean of the prior CHILD2_RVOL_LOOKBACK days of volume
    # shift(1) so the current day's volume is excluded from the denominator
    df["vol_prior_avg"] = (
        df["volume"]
        .shift(1)
        .rolling(CHILD2_RVOL_LOOKBACK, min_periods=CHILD2_RVOL_LOOKBACK)
        .mean()
    )
    df["rvol_20d_prior"] = df["volume"] / df["vol_prior_avg"]

    result = {}
    for date_str in event_dates:
        try:
            d = datetime.date.fromisoformat(date_str)
        except (ValueError, TypeError):
            continue
        if d not in df.index:
            continue
        row = df.loc[d]
        result[date_str] = {
            "stock_sma20":        round(float(row["sma20"]), 4) if not pd.isna(row["sma20"]) else None,
            "stock_above_sma20":  int(row["stock_above_sma20"]) if not pd.isna(row["stock_above_sma20"]) else None,
            "stock_rvol_20d_prior": round(float(row["rvol_20d_prior"]), 4) if not pd.isna(row["rvol_20d_prior"]) else None,
        }
    return result


# ---------------------------------------------------------------------------
# Summary builders
# ---------------------------------------------------------------------------

def _metrics_row(label_key: str, label_val: str, sub: pd.DataFrame) -> dict:
    valid = sub.dropna(subset=["next_day_open_to_close_pct", "continuation_flag"])
    n = len(sub)
    nv = len(valid)
    return {
        "slice":                          f"{label_key}={label_val}",
        "n_events":                       n,
        "n_with_next_day":                nv,
        "continuation_rate_pct":          round(valid["continuation_flag"].mean() * 100, 1) if nv else None,
        "mean_nd_open_to_high_pct":       round(valid["next_day_open_to_high_pct"].mean() * 100, 3) if nv else None,
        "mean_nd_open_to_low_pct":        round(valid["next_day_open_to_low_pct"].mean() * 100, 3) if nv else None,
        "mean_nd_open_to_close_pct":      round(valid["next_day_open_to_close_pct"].mean() * 100, 3) if nv else None,
        "mean_nd_range_pct":              round(valid["next_day_range_pct"].mean() * 100, 3) if nv else None,
        "pct_gap_up":                     round((sub["gap_direction"] == "up").mean() * 100, 1),
    }


def _build_child_summary(child_name: str, df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    rows.append(_metrics_row("all", "all", df))
    for direction in ["up", "down"]:
        rows.append(_metrics_row("gap_direction", direction, df[df["gap_direction"] == direction]))
    for regime in ["bullish", "neutral", "bearish"]:
        rows.append(_metrics_row("market_regime", regime, df[df["market_regime_label"] == regime]))
    for direction in ["up", "down"]:
        for regime in ["bullish", "neutral", "bearish"]:
            sub = df[(df["gap_direction"] == direction) & (df["market_regime_label"] == regime)]
            rows.append(_metrics_row(f"gap_{direction}_x_regime", regime, sub))
    result = pd.DataFrame(rows)
    result.insert(0, "child_name", child_name)
    return result


def _build_comparison(parent_q: pd.DataFrame, child1: pd.DataFrame, child2: pd.DataFrame) -> pd.DataFrame:
    """Side-by-side comparison on the 'all' slice and the direction slices."""
    rows = []
    slices = [
        ("all", lambda df: df),
        ("gap_up",   lambda df: df[df["gap_direction"] == "up"]),
        ("gap_down", lambda df: df[df["gap_direction"] == "down"]),
        ("bullish",  lambda df: df[df["market_regime_label"] == "bullish"]),
        ("bearish",  lambda df: df[df["market_regime_label"] == "bearish"]),
    ]
    metrics = [
        ("n_events",               lambda df: len(df)),
        ("continuation_rate_pct",  lambda df: round(df.dropna(subset=["continuation_flag"])["continuation_flag"].mean() * 100, 1)),
        ("mean_nd_open_to_close",  lambda df: round(df.dropna(subset=["next_day_open_to_close_pct"])["next_day_open_to_close_pct"].mean() * 100, 3)),
        ("mean_nd_range_pct",      lambda df: round(df.dropna(subset=["next_day_range_pct"])["next_day_range_pct"].mean() * 100, 3)),
        ("mean_nd_open_to_high",   lambda df: round(df.dropna(subset=["next_day_open_to_high_pct"])["next_day_open_to_high_pct"].mean() * 100, 3)),
        ("mean_nd_open_to_low",    lambda df: round(df.dropna(subset=["next_day_open_to_low_pct"])["next_day_open_to_low_pct"].mean() * 100, 3)),
    ]
    datasets = [
        ("parent_quality_filtered", parent_q),
        ("child1_liquid_trend",     child1),
        ("child2_high_rvol",        child2),
    ]
    for slice_name, slice_fn in slices:
        for metric_name, metric_fn in metrics:
            row = {"slice": slice_name, "metric": metric_name}
            for ds_name, ds in datasets:
                subset = slice_fn(ds)
                try:
                    row[ds_name] = metric_fn(subset) if len(subset) > 0 else None
                except Exception:
                    row[ds_name] = None
            rows.append(row)
    return pd.DataFrame(rows)


def _build_yearly_summary(child1: pd.DataFrame, child2: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for child_name, df in [
        ("child1_liquid_trend_names", child1),
        ("child2_high_rvol_names",    child2),
    ]:
        df = df.copy()
        df["year"] = df["signal_date"].str[:4].astype(int)
        for yr in sorted(df["year"].unique()):
            for direction in ["all", "up", "down"]:
                if direction == "all":
                    sub = df[df["year"] == yr]
                else:
                    sub = df[(df["year"] == yr) & (df["gap_direction"] == direction)]
                if len(sub) < 10:
                    continue
                sub_v = sub.dropna(subset=["next_day_open_to_close_pct", "continuation_flag"])
                rows.append({
                    "child_name":                 child_name,
                    "year":                       yr,
                    "gap_direction":              direction,
                    "n_events":                   len(sub),
                    "continuation_rate_pct":      round(sub_v["continuation_flag"].mean() * 100, 1) if len(sub_v) else None,
                    "mean_nd_open_to_close_pct":  round(sub_v["next_day_open_to_close_pct"].mean() * 100, 3) if len(sub_v) else None,
                    "mean_nd_range_pct":          round(sub_v["next_day_range_pct"].mean() * 100, 3) if len(sub_v) else None,
                })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="phase_r3 child isolation: gap_continuation"
    )
    parser.add_argument("--parent-events", default=PARENT_EVENTS_CSV,
                        help="Path to parent event rows CSV from phase_r2")
    parser.add_argument("--gap-cap", type=float, default=GAP_PCT_MAX_ABS,
                        metavar="FRAC", help="Max |gap_pct| quality cap (default 0.30)")
    parser.add_argument("--rvol-min", type=float, default=CHILD2_RVOL_MIN,
                        metavar="X", help="RVOL minimum for child2 (default 1.5)")
    args = parser.parse_args()

    print("=" * 70)
    print("research_run_gap_continuation_phase_r3_child_isolation")
    print("Track  : plan_next_day_day_trade")
    print("Family : gap_continuation")
    print("Phase  : phase_r3__child_isolation")
    print(f"Run date: {TODAY}")
    print("-" * 70)
    print(f"Parent events CSV : {args.parent_events}")
    print(f"Quality cap       : |gap_pct| <= {args.gap_cap * 100:.0f}%")
    print(f"Child 1 liquidity : adv_dollar_bucket in {sorted(CHILD1_LIQUID_BUCKETS)}")
    print(f"Child 1 SMA period: {CHILD1_SMA_PERIOD} days")
    print(f"Child 2 RVOL min  : >= {args.rvol_min}x prior {CHILD2_RVOL_LOOKBACK}-day avg volume")
    print("=" * 70)

    # -- Load parent events ---------------------------------------------------

    if not os.path.exists(args.parent_events):
        print(f"ERROR: parent events file not found:\n  {args.parent_events}")
        sys.exit(1)

    parent = pd.read_csv(args.parent_events)
    print(f"\nParent events loaded: {len(parent):,} rows")

    # Quality filter
    parent_q = parent[parent["gap_pct"].abs() <= args.gap_cap].copy()
    print(f"After quality cap (|gap_pct| <= {args.gap_cap*100:.0f}%): "
          f"{len(parent_q):,} events (removed {len(parent)-len(parent_q):,})")

    # -- Enrich with per-ticker SMA20 and RVOL --------------------------------

    unique_tickers = parent_q["ticker"].unique()
    print(f"\nEnriching {len(unique_tickers):,} tickers with SMA20 and RVOL from daily cache ...")

    # Build per-ticker event date sets for efficient lookup
    ticker_dates = parent_q.groupby("ticker")["signal_date"].apply(set).to_dict()

    enrichment_rows = []
    n_no_cache = 0

    for i, ticker in enumerate(unique_tickers, 1):
        event_dates = ticker_dates.get(ticker, set())
        enriched = _enrich_ticker(ticker, event_dates)
        if not enriched:
            n_no_cache += 1
            continue
        for date_str, vals in enriched.items():
            enrichment_rows.append({"ticker": ticker, "signal_date": date_str, **vals})
        if i % 300 == 0:
            print(f"  Enriched {i}/{len(unique_tickers)} tickers ...", flush=True)

    print(f"Enrichment complete:")
    print(f"  Tickers enriched : {len(unique_tickers) - n_no_cache:,}")
    print(f"  No daily cache   : {n_no_cache}")

    enrichment_df = pd.DataFrame(enrichment_rows)

    # Merge enrichment back to parent events
    parent_enriched = parent_q.merge(
        enrichment_df[["ticker", "signal_date", "stock_above_sma20", "stock_rvol_20d_prior"]],
        on=["ticker", "signal_date"],
        how="left",
    )
    print(f"Merged enrichment columns into parent events: {len(parent_enriched):,} rows")

    sma_available = parent_enriched["stock_above_sma20"].notna().sum()
    rvol_available = parent_enriched["stock_rvol_20d_prior"].notna().sum()
    print(f"  stock_above_sma20 available : {sma_available:,} ({sma_available/len(parent_enriched)*100:.1f}%)")
    print(f"  stock_rvol_20d_prior available: {rvol_available:,} ({rvol_available/len(parent_enriched)*100:.1f}%)")

    # -- Apply child filters --------------------------------------------------

    # Child 1: liquid + trend-aligned
    liq_mask = parent_enriched["adv_dollar_bucket"].isin(CHILD1_LIQUID_BUCKETS)
    trend_up_mask   = (parent_enriched["gap_direction"] == "up")   & (parent_enriched["stock_above_sma20"] == 1)
    trend_down_mask = (parent_enriched["gap_direction"] == "down") & (parent_enriched["stock_above_sma20"] == 0)
    trend_mask = trend_up_mask | trend_down_mask
    child1_mask = liq_mask & trend_mask & parent_enriched["stock_above_sma20"].notna()

    child1 = parent_enriched[child1_mask].copy()
    child1["child_name"] = "gap_continuation__liquid_trend_names"

    # Child 2: high RVOL
    rvol_mask = (
        parent_enriched["stock_rvol_20d_prior"].notna()
        & (parent_enriched["stock_rvol_20d_prior"] >= args.rvol_min)
    )
    child2_mask = rvol_mask
    child2 = parent_enriched[child2_mask].copy()
    child2["child_name"] = "gap_continuation__high_rvol_names"

    print(f"\nChild sample sizes:")
    print(f"  Parent (quality-filtered)           : {len(parent_enriched):,}")
    print(f"  Child 1 (liquid + trend-aligned)    : {len(child1):,}  "
          f"({len(child1)/len(parent_enriched)*100:.1f}% of parent)")
    print(f"  Child 2 (high RVOL >= {args.rvol_min}x)         : {len(child2):,}  "
          f"({len(child2)/len(parent_enriched)*100:.1f}% of parent)")

    # -- Print key metrics per child ------------------------------------------

    print(f"\n{'='*70}")
    print("KEY METRICS COMPARISON")
    print(f"{'='*70}")

    datasets = [
        ("Parent (quality-filtered)", parent_enriched),
        ("Child 1: liquid_trend_names", child1),
        ("Child 2: high_rvol_names",    child2),
    ]
    slices = [
        ("ALL",          lambda df: df),
        ("gap_up",       lambda df: df[df["gap_direction"] == "up"]),
        ("gap_down",     lambda df: df[df["gap_direction"] == "down"]),
        ("bullish",      lambda df: df[df["market_regime_label"] == "bullish"]),
        ("bearish",      lambda df: df[df["market_regime_label"] == "bearish"]),
    ]

    for slice_name, slice_fn in slices:
        print(f"\n  Slice: {slice_name}")
        print(f"  {'Name':<38}  {'n':>8}  {'cont%':>6}  {'o->c':>7}  {'o->h':>7}  {'o->l':>7}  {'range':>6}")
        for ds_name, ds in datasets:
            sub = slice_fn(ds)
            v = sub.dropna(subset=["continuation_flag", "next_day_open_to_close_pct"])
            n = len(sub)
            if n == 0:
                print(f"  {ds_name:<38}  {'—':>8}")
                continue
            cont  = v["continuation_flag"].mean() * 100 if len(v) else float("nan")
            oc    = v["next_day_open_to_close_pct"].mean() * 100 if len(v) else float("nan")
            oh    = v["next_day_open_to_high_pct"].mean() * 100 if len(v) else float("nan")
            ol    = v["next_day_open_to_low_pct"].mean() * 100 if len(v) else float("nan")
            rng   = v["next_day_range_pct"].mean() * 100 if len(v) else float("nan")
            print(f"  {ds_name:<38}  {n:>8,}  {cont:>6.1f}  {oc:>+7.3f}  {oh:>+7.3f}  {ol:>+7.3f}  {rng:>6.3f}")

    # -- Write outputs --------------------------------------------------------

    combined_children = pd.concat([child1, child2], ignore_index=True)
    child1_summary = _build_child_summary("child1_liquid_trend_names", child1)
    child2_summary = _build_child_summary("child2_high_rvol_names", child2)
    combined_summary = pd.concat([child1_summary, child2_summary], ignore_index=True)
    comparison_df = _build_comparison(parent_enriched, child1, child2)
    yearly_df = _build_yearly_summary(child1, child2)

    events_file     = os.path.join(OUTPUT_DIR, f"child_event_rows__gap_continuation__phase_r3__{TODAY}.csv")
    summary_file    = os.path.join(OUTPUT_DIR, f"child_summary__gap_continuation__phase_r3__{TODAY}.csv")
    comparison_file = os.path.join(OUTPUT_DIR, f"child_vs_parent_comparison__gap_continuation__phase_r3__{TODAY}.csv")
    yearly_file     = os.path.join(OUTPUT_DIR, f"child_yearly_summary__gap_continuation__phase_r3__{TODAY}.csv")

    combined_children.to_csv(events_file,  index=False)
    combined_summary.to_csv(summary_file,  index=False)
    comparison_df.to_csv(comparison_file,  index=False)
    yearly_df.to_csv(yearly_file,          index=False)

    print(f"\n{'='*70}")
    print("OUTPUTS WRITTEN")
    print(f"{'='*70}")
    print(f"  Event rows    : {events_file}")
    print(f"                  ({len(combined_children):,} combined child rows)")
    print(f"  Summary       : {summary_file}")
    print(f"  Comparison    : {comparison_file}")
    print(f"  Yearly        : {yearly_file}")

    # -- Yearly stability (child 1) -------------------------------------------

    print(f"\nYearly stability — child 1 (liquid_trend_names, all directions):")
    yr1 = yearly_df[(yearly_df["child_name"] == "child1_liquid_trend_names") & (yearly_df["gap_direction"] == "all")]
    print(yr1[["year","n_events","continuation_rate_pct","mean_nd_open_to_close_pct","mean_nd_range_pct"]].to_string(index=False))

    print(f"\nYearly stability — child 2 (high_rvol_names, all directions):")
    yr2 = yearly_df[(yearly_df["child_name"] == "child2_high_rvol_names") & (yearly_df["gap_direction"] == "all")]
    print(yr2[["year","n_events","continuation_rate_pct","mean_nd_open_to_close_pct","mean_nd_range_pct"]].to_string(index=False))

    print(f"\nDone. phase_r3 child isolation for gap_continuation complete.")


if __name__ == "__main__":
    main()
