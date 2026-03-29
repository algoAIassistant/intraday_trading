"""
research_run_gap_continuation_phase_r2_parent_baseline.py
Side:   research -- strategy family layer
Track:  plan_next_day_day_trade
Family: gap_continuation
Phase:  phase_r2__family_discovery_and_parent_baseline

Purpose:
  Materialize the first parent baseline for the gap_continuation family.

  This phase does NOT define children, grandchildren, or execution templates.
  It establishes whether the broad family has any plausible structure before
  narrowing begins in phase_r3.

Family definition (parent level — intentionally broad):
  A signal day is a gap_continuation parent event when:
    |gap_pct| >= GAP_MIN_PCT
    where gap_pct = (open_T - close_{T-1}) / close_{T-1}

  The stock is in the phase_r0 working universe (include_in_working_universe == True).
  The signal date is within the phase_r1 market-context coverage.

What this script answers (family/parent level only):
  - How common are gap events in this universe?
  - What is the basic next-day opportunity envelope after a gap?
  - Does gap direction (up vs down) affect next-day behavior?
  - Does market regime context at signal creation affect next-day behavior?
  - Are the effects stable across years?

This script does NOT:
  - define stop or target logic
  - define entry rules
  - split into children or grandchildren
  - assume any reward:risk ratio
  - apply execution simulation

Inputs:
  research_configs/research_working_universe_plan_next_day_day_trade_candidates.csv
  research_data_cache/daily/<TICKER>.parquet  (for each universe ticker)
  research_outputs/.../phase_r1_market_context_model/market_context_model_plan_next_day_day_trade.csv

Outputs (research_outputs/family_lineages/plan_next_day_day_trade/gap_continuation/phase_r2_parent_baseline/):
  parent_event_rows__gap_continuation__phase_r2__<DATE>.csv
  parent_summary__gap_continuation__phase_r2__<DATE>.csv
  parent_yearly_summary__gap_continuation__phase_r2__<DATE>.csv

Event row columns:
  ticker, signal_date, next_date,
  gap_pct, gap_direction,
  signal_day_close, signal_day_open, signal_day_range_pct, signal_day_close_location,
  signal_day_volume, signal_day_dollar_volume,
  price_bucket, adv_dollar_bucket,
  next_day_open, next_day_high, next_day_low, next_day_close,
  next_day_gap_pct,
  next_day_open_to_high_pct,
  next_day_open_to_low_pct,
  next_day_open_to_close_pct,
  next_day_range_pct,
  continuation_flag,
  market_regime_label,
  spy_return_1d, spy_return_5d, spy_range_expansion, spy_realized_vol_20d

Usage:
  python research_run_gap_continuation_phase_r2_parent_baseline.py

  Optional overrides:
  --gap-min 0.005     minimum |gap_pct| to qualify (default 0.005 = 0.5%)
  --start 2021-04-23  start date (default: phase_r1 usable range start)
  --end   2026-03-24  end date (default: most recent in cache)

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

DAILY_DIR     = os.path.join(REPO_ROOT, "1_0_strategy_research", "research_data_cache", "daily")
CONFIG_DIR    = os.path.join(REPO_ROOT, "1_0_strategy_research", "research_configs")
OUTPUT_DIR    = os.path.join(
    REPO_ROOT,
    "1_0_strategy_research", "research_outputs",
    "family_lineages", "plan_next_day_day_trade",
    "gap_continuation", "phase_r2_parent_baseline",
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

UNIVERSE_CSV = os.path.join(
    CONFIG_DIR, "research_working_universe_plan_next_day_day_trade_candidates.csv"
)
MARKET_CONTEXT_CSV = os.path.join(
    REPO_ROOT,
    "1_0_strategy_research", "research_outputs",
    "family_lineages", "plan_next_day_day_trade",
    "phase_r1_market_context_model",
    "market_context_model_plan_next_day_day_trade.csv",
)

TODAY = datetime.date.today().strftime("%Y_%m_%d")

# ---------------------------------------------------------------------------
# Config defaults  <-- tune here
# ---------------------------------------------------------------------------

DEFAULT_GAP_MIN     = 0.005     # 0.5% — broad parent threshold
DEFAULT_DATE_START  = "2021-04-23"   # phase_r1 usable range start
DEFAULT_DATE_END    = "2026-03-24"   # latest in market context cache

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
# Daily cache loader
# ---------------------------------------------------------------------------

def _load_daily(ticker: str) -> pd.DataFrame | None:
    path = _daily_path(ticker)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_parquet(path)
        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(df.columns) or len(df) < 3:
            return None
        df = df.sort_index()
        # Normalize index to plain date
        if hasattr(df.index, "tz") and df.index.tz is not None:
            df.index = df.index.tz_convert("America/New_York").normalize().tz_localize(None)
        df.index = pd.to_datetime(df.index).normalize().date
        df.index.name = "date"
        df = df[~df.index.duplicated(keep="last")]
        return df
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Per-ticker event extraction
# ---------------------------------------------------------------------------

def _extract_events(
    ticker: str,
    daily_df: pd.DataFrame,
    gap_min: float,
    date_start: datetime.date,
    date_end: datetime.date,
    price_bucket: str,
    adv_dollar_bucket: str,
) -> list[dict]:
    """
    For one ticker, extract all parent-level gap_continuation events.
    Returns a list of event dicts.
    """
    df = daily_df.copy()
    df = df[(df.index >= date_start) & (df.index <= date_end)]

    if len(df) < 3:
        return []

    dates = list(df.index)
    closes  = df["close"].values
    opens   = df["open"].values
    highs   = df["high"].values
    lows    = df["low"].values
    volumes = df["volume"].values

    events = []

    for i in range(1, len(dates) - 1):   # need i-1 (prev close) and i+1 (next day)
        signal_date = dates[i]
        prev_close  = closes[i - 1]
        if prev_close <= 0:
            continue

        gap_pct = (opens[i] - prev_close) / prev_close

        if abs(gap_pct) < gap_min:
            continue

        gap_direction = "up" if gap_pct > 0 else "down"

        signal_close  = closes[i]
        signal_open   = opens[i]
        signal_high   = highs[i]
        signal_low    = lows[i]
        signal_volume = volumes[i]

        signal_range_pct = (signal_high - signal_low) / signal_close if signal_close > 0 else None
        signal_close_loc = (
            (signal_close - signal_low) / (signal_high - signal_low)
            if (signal_high - signal_low) > 0 else None
        )
        signal_dollar_vol = signal_close * signal_volume

        # Next-day data
        next_date  = dates[i + 1]
        nd_open    = opens[i + 1]
        nd_high    = highs[i + 1]
        nd_low     = lows[i + 1]
        nd_close   = closes[i + 1]

        nd_gap_pct         = (nd_open - signal_close) / signal_close if signal_close > 0 else None
        nd_open_to_high    = (nd_high  - nd_open) / nd_open if nd_open > 0 else None
        nd_open_to_low     = (nd_low   - nd_open) / nd_open if nd_open > 0 else None
        nd_open_to_close   = (nd_close - nd_open) / nd_open if nd_open > 0 else None
        nd_range_pct       = (nd_high  - nd_low)  / nd_close if nd_close > 0 else None

        # Continuation: did next day close in the direction of the gap?
        if nd_open_to_close is not None:
            if gap_direction == "up":
                continuation = 1 if nd_open_to_close > 0 else 0
            else:
                continuation = 1 if nd_open_to_close < 0 else 0
        else:
            continuation = None

        events.append({
            "ticker":                      ticker,
            "signal_date":                 str(signal_date),
            "next_date":                   str(next_date),
            "gap_pct":                     round(gap_pct, 6),
            "gap_direction":               gap_direction,
            "signal_day_close":            round(signal_close, 4),
            "signal_day_open":             round(signal_open, 4),
            "signal_day_range_pct":        round(signal_range_pct, 6) if signal_range_pct is not None else None,
            "signal_day_close_location":   round(signal_close_loc, 4) if signal_close_loc is not None else None,
            "signal_day_volume":           int(round(signal_volume)),
            "signal_day_dollar_volume":    int(round(signal_dollar_vol)),
            "price_bucket":                price_bucket,
            "adv_dollar_bucket":           adv_dollar_bucket,
            "next_day_open":               round(nd_open, 4),
            "next_day_high":               round(nd_high, 4),
            "next_day_low":                round(nd_low, 4),
            "next_day_close":              round(nd_close, 4),
            "next_day_gap_pct":            round(nd_gap_pct, 6) if nd_gap_pct is not None else None,
            "next_day_open_to_high_pct":   round(nd_open_to_high, 6) if nd_open_to_high is not None else None,
            "next_day_open_to_low_pct":    round(nd_open_to_low, 6) if nd_open_to_low is not None else None,
            "next_day_open_to_close_pct":  round(nd_open_to_close, 6) if nd_open_to_close is not None else None,
            "next_day_range_pct":          round(nd_range_pct, 6) if nd_range_pct is not None else None,
            "continuation_flag":           continuation,
        })

    return events


# ---------------------------------------------------------------------------
# Summary builders
# ---------------------------------------------------------------------------

def _pct(series: pd.Series) -> str:
    return f"{series.mean() * 100:.2f}%"


def _build_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate by gap_direction × market_regime_label."""
    rows = []

    groups = [
        ("all_directions", "all_regimes", df),
    ]
    for direction in ["up", "down"]:
        groups.append((direction, "all_regimes", df[df["gap_direction"] == direction]))
    for regime in ["bullish", "neutral", "bearish"]:
        groups.append(("all_directions", regime, df[df["market_regime_label"] == regime]))
    for direction in ["up", "down"]:
        for regime in ["bullish", "neutral", "bearish"]:
            sub = df[(df["gap_direction"] == direction) & (df["market_regime_label"] == regime)]
            groups.append((direction, regime, sub))

    for direction_label, regime_label, sub in groups:
        if len(sub) == 0:
            continue
        sub_valid = sub.dropna(subset=["next_day_open_to_close_pct", "continuation_flag"])
        n = len(sub)
        n_valid = len(sub_valid)
        rows.append({
            "gap_direction":               direction_label,
            "market_regime":              regime_label,
            "n_events":                   n,
            "n_with_next_day":            n_valid,
            "mean_gap_pct":               round(sub["gap_pct"].mean() * 100, 3),
            "mean_nd_open_to_high_pct":   round(sub_valid["next_day_open_to_high_pct"].mean() * 100, 3) if n_valid else None,
            "mean_nd_open_to_low_pct":    round(sub_valid["next_day_open_to_low_pct"].mean() * 100, 3) if n_valid else None,
            "mean_nd_open_to_close_pct":  round(sub_valid["next_day_open_to_close_pct"].mean() * 100, 3) if n_valid else None,
            "mean_nd_range_pct":          round(sub_valid["next_day_range_pct"].mean() * 100, 3) if n_valid else None,
            "continuation_rate":          round(sub_valid["continuation_flag"].mean() * 100, 1) if n_valid else None,
        })

    return pd.DataFrame(rows)


def _build_yearly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Year × gap_direction × basic next-day metrics."""
    df = df.copy()
    df["year"] = df["signal_date"].str[:4].astype(int)
    rows = []
    for yr in sorted(df["year"].unique()):
        for direction in ["up", "down", "all"]:
            if direction == "all":
                sub = df[df["year"] == yr]
            else:
                sub = df[(df["year"] == yr) & (df["gap_direction"] == direction)]
            if len(sub) == 0:
                continue
            sub_v = sub.dropna(subset=["next_day_open_to_close_pct", "continuation_flag"])
            rows.append({
                "year":                       yr,
                "gap_direction":              direction,
                "n_events":                   len(sub),
                "mean_nd_open_to_close_pct":  round(sub_v["next_day_open_to_close_pct"].mean() * 100, 3) if len(sub_v) else None,
                "continuation_rate":          round(sub_v["continuation_flag"].mean() * 100, 1) if len(sub_v) else None,
                "mean_nd_range_pct":          round(sub_v["next_day_range_pct"].mean() * 100, 3) if len(sub_v) else None,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="phase_r2 parent baseline: gap_continuation family"
    )
    parser.add_argument("--gap-min",  type=float, default=DEFAULT_GAP_MIN,
                        metavar="FRAC", help="Minimum |gap_pct| to qualify (default 0.005)")
    parser.add_argument("--start",    default=DEFAULT_DATE_START, metavar="YYYY-MM-DD")
    parser.add_argument("--end",      default=DEFAULT_DATE_END,   metavar="YYYY-MM-DD")
    args = parser.parse_args()

    date_start = datetime.date.fromisoformat(args.start)
    date_end   = datetime.date.fromisoformat(args.end)

    print("=" * 70)
    print("research_run_gap_continuation_phase_r2_parent_baseline")
    print("Track  : plan_next_day_day_trade")
    print("Family : gap_continuation")
    print("Phase  : phase_r2__family_discovery_and_parent_baseline")
    print(f"Run date: {TODAY}")
    print("-" * 70)
    print(f"Gap minimum     : |gap_pct| >= {args.gap_min * 100:.2f}%")
    print(f"Date range      : {date_start} to {date_end}")
    print("=" * 70)

    # -- Load universe --------------------------------------------------------

    if not os.path.exists(UNIVERSE_CSV):
        print(f"ERROR: universe CSV not found:\n  {UNIVERSE_CSV}")
        sys.exit(1)

    universe_df = pd.read_csv(UNIVERSE_CSV)
    universe_df = universe_df[universe_df["include_in_working_universe"] == True].copy()
    print(f"\nPhase_r0 working universe: {len(universe_df)} tickers (included only)")

    # Build lookup dict: ticker -> (price_bucket, adv_dollar_bucket)
    ticker_meta = universe_df.set_index("ticker")[["price_bucket","adv_dollar_bucket"]].to_dict("index")

    # -- Load market context --------------------------------------------------

    if not os.path.exists(MARKET_CONTEXT_CSV):
        print(f"ERROR: market context CSV not found:\n  {MARKET_CONTEXT_CSV}")
        sys.exit(1)

    ctx = pd.read_csv(MARKET_CONTEXT_CSV, parse_dates=["date"])
    ctx["date"] = ctx["date"].dt.date
    ctx = ctx[ctx["market_regime_label"] != "warmup_na"]
    ctx_lookup = ctx.set_index("date")[[
        "market_regime_label",
        "spy_return_1d", "spy_return_5d",
        "spy_range_expansion", "spy_realized_vol_20d",
    ]].to_dict("index")
    print(f"Phase_r1 market context: {len(ctx)} usable dates "
          f"({ctx['date'].min()} to {ctx['date'].max()})")

    # -- Iterate tickers ------------------------------------------------------

    print(f"\nExtracting gap events from {len(universe_df)} tickers ...")

    all_events = []
    n_no_cache = 0
    n_processed = 0

    for i, row in enumerate(universe_df.itertuples(), 1):
        ticker       = row.ticker
        price_bucket = row.price_bucket
        adv_bucket   = row.adv_dollar_bucket

        daily_df = _load_daily(ticker)
        if daily_df is None:
            n_no_cache += 1
            continue

        events = _extract_events(
            ticker, daily_df, args.gap_min,
            date_start, date_end,
            price_bucket, adv_bucket,
        )

        # Attach market context columns
        for ev in events:
            sig_date = datetime.date.fromisoformat(ev["signal_date"])
            ctx_row = ctx_lookup.get(sig_date, {})
            ev["market_regime_label"]    = ctx_row.get("market_regime_label", None)
            ev["spy_return_1d"]          = ctx_row.get("spy_return_1d", None)
            ev["spy_return_5d"]          = ctx_row.get("spy_return_5d", None)
            ev["spy_range_expansion"]    = ctx_row.get("spy_range_expansion", None)
            ev["spy_realized_vol_20d"]   = ctx_row.get("spy_realized_vol_20d", None)

        all_events.extend(events)
        n_processed += 1

        if i % 300 == 0:
            print(f"  Processed {i}/{len(universe_df)} tickers "
                  f"| events so far: {len(all_events):,}", flush=True)

    print(f"\nExtraction complete:")
    print(f"  Tickers processed  : {n_processed}")
    print(f"  Tickers no cache   : {n_no_cache}")
    print(f"  Total events found : {len(all_events):,}")

    if not all_events:
        print("ERROR: no events found — check gap threshold and date range.")
        sys.exit(1)

    events_df = pd.DataFrame(all_events)

    # Drop events where market context was not available (outside phase_r1 coverage)
    before = len(events_df)
    events_df = events_df.dropna(subset=["market_regime_label"])
    dropped = before - len(events_df)
    if dropped > 0:
        print(f"  Dropped {dropped} events outside phase_r1 market context coverage")

    print(f"  Events with market context: {len(events_df):,}")

    # -- Basic stats ----------------------------------------------------------

    gap_up   = (events_df["gap_direction"] == "up").sum()
    gap_down = (events_df["gap_direction"] == "down").sum()
    print(f"\nGap direction split:")
    print(f"  Gap up   : {gap_up:,}  ({gap_up / len(events_df) * 100:.1f}%)")
    print(f"  Gap down : {gap_down:,}  ({gap_down / len(events_df) * 100:.1f}%)")

    regime_counts = events_df["market_regime_label"].value_counts()
    print(f"\nMarket regime at signal creation:")
    for regime, cnt in regime_counts.items():
        print(f"  {regime:<10}: {cnt:,}  ({cnt / len(events_df) * 100:.1f}%)")

    valid = events_df.dropna(subset=["next_day_open_to_close_pct", "continuation_flag"])
    print(f"\nNext-day envelope (all events, n={len(valid):,}):")
    print(f"  Mean open->high   : {valid['next_day_open_to_high_pct'].mean() * 100:+.2f}%")
    print(f"  Mean open->low    : {valid['next_day_open_to_low_pct'].mean() * 100:+.2f}%")
    print(f"  Mean open->close  : {valid['next_day_open_to_close_pct'].mean() * 100:+.2f}%")
    print(f"  Mean daily range  : {valid['next_day_range_pct'].mean() * 100:.2f}%")
    print(f"  Continuation rate : {valid['continuation_flag'].mean() * 100:.1f}%")

    print(f"\nBy gap direction:")
    for direction in ["up", "down"]:
        sub = valid[valid["gap_direction"] == direction]
        if len(sub) == 0:
            continue
        print(f"  {direction.upper():4s} (n={len(sub):,})  "
              f"open->close={sub['next_day_open_to_close_pct'].mean()*100:+.2f}%  "
              f"continuation={sub['continuation_flag'].mean()*100:.1f}%  "
              f"range={sub['next_day_range_pct'].mean()*100:.2f}%")

    # -- Build and write summaries --------------------------------------------

    summary_df       = _build_summary(events_df)
    yearly_summary   = _build_yearly_summary(events_df)

    events_file  = os.path.join(
        OUTPUT_DIR,
        f"parent_event_rows__gap_continuation__phase_r2__{TODAY}.csv"
    )
    summary_file = os.path.join(
        OUTPUT_DIR,
        f"parent_summary__gap_continuation__phase_r2__{TODAY}.csv"
    )
    yearly_file  = os.path.join(
        OUTPUT_DIR,
        f"parent_yearly_summary__gap_continuation__phase_r2__{TODAY}.csv"
    )

    events_df.to_csv(events_file,  index=False)
    summary_df.to_csv(summary_file, index=False)
    yearly_summary.to_csv(yearly_file, index=False)

    print(f"\nOutputs written:")
    print(f"  Event rows   : {events_file}")
    print(f"                 ({len(events_df):,} rows)")
    print(f"  Summary      : {summary_file}")
    print(f"  Yearly summ  : {yearly_file}")

    print(f"\nSummary table (direction × regime):")
    print(summary_df[
        summary_df["gap_direction"].isin(["up","down","all_directions"])
        & summary_df["market_regime"].isin(["all_regimes","bullish","bearish","neutral"])
    ].to_string(index=False))

    print(f"\nYearly summary (all directions combined):")
    print(yearly_summary[yearly_summary["gap_direction"] == "all"].to_string(index=False))

    print(f"\nDone. phase_r2 parent baseline for gap_continuation complete.")


if __name__ == "__main__":
    main()
