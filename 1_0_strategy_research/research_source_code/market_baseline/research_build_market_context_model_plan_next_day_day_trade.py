"""
research_build_market_context_model_plan_next_day_day_trade.py
Side:  research -- market baseline layer
Track: plan_next_day_day_trade
Phase: phase_r1__market_context_model

Purpose:
  Build a reusable daily market-context dataset for the plan_next_day_day_trade
  research track.

  This is NOT family discovery. This phase produces a join layer so later
  family / child / grandchild studies can slice behavior under different
  next-day planning environments.

  Research question:
    Under what broad market conditions are night-before next-day plans
    generally more favorable or less favorable?

Inputs (repo-native, no external API call required):
  research_data_cache/market/daily/SPY.parquet  (primary)
  research_data_cache/market/daily/QQQ.parquet  (secondary)

VIX availability:
  VIX is NOT available in this repo cache. No VIX-based columns are produced.
  If VIX is added to the market cache in a future session, the v2 of this
  script should add:
    - vix_close
    - vix_regime (low / medium / high / spike)
  as additional context dimensions.

Output columns (all represent information known at the CLOSE of the signal day):
  date
  spy_close, spy_open, spy_high, spy_low, spy_volume
  spy_sma20, spy_sma50, spy_sma200
  spy_above_sma20, spy_above_sma50, spy_above_sma200   (1 / 0)
  spy_sma20_slope_up                                    (1 / 0)
  spy_return_1d, spy_return_5d, spy_return_20d, spy_return_60d
  spy_gap_pct
  spy_range_pct, spy_range_pct_sma10, spy_range_expansion
  spy_realized_vol_20d
  qqq_close
  qqq_above_sma20, qqq_above_sma50                     (1 / 0)
  qqq_return_1d, qqq_return_5d
  qqq_realized_vol_20d
  spy_qqq_divergence_1d
  market_regime_label   ('bullish' / 'neutral' / 'bearish')

Regime label definition (transparent and reproducible):
  bullish : spy_above_sma20 AND spy_above_sma50 AND spy_sma20_slope_up
  bearish : NOT spy_above_sma20 AND NOT spy_above_sma50 AND NOT spy_sma20_slope_up
  neutral : all other combinations

  Rule: this first-version label intentionally uses a conservative three-way
  split based on structural position only. Return-speed dimensions are
  available as raw columns for downstream slicing. Do not override the label
  logic without documenting the change in the output notes.

Output files:
  research_outputs/family_lineages/plan_next_day_day_trade/
    phase_r1_market_context_model/
      market_context_model_plan_next_day_day_trade.csv     (main daily table)
      market_context_model_summary_plan_next_day_day_trade.csv (regime counts)

Usage:
  python research_build_market_context_model_plan_next_day_day_trade.py

Dependencies:
  pip install pandas pyarrow numpy
"""

import os
import sys
import datetime
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT   = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", ".."))

MARKET_DAILY_DIR = os.path.join(
    REPO_ROOT, "1_0_strategy_research", "research_data_cache", "market", "daily"
)
SPY_PARQUET = os.path.join(MARKET_DAILY_DIR, "SPY.parquet")
QQQ_PARQUET = os.path.join(MARKET_DAILY_DIR, "QQQ.parquet")

OUTPUT_DIR = os.path.join(
    REPO_ROOT,
    "1_0_strategy_research",
    "research_outputs",
    "family_lineages",
    "plan_next_day_day_trade",
    "phase_r1_market_context_model",
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

TODAY = datetime.date.today().strftime("%Y_%m_%d")

# ---------------------------------------------------------------------------
# Lookback periods  <-- tune here without touching logic below
# ---------------------------------------------------------------------------

SMA_SHORT   = 20    # short moving average (days)
SMA_MEDIUM  = 50    # medium moving average (days)
SMA_LONG    = 200   # long moving average (days)

RANGE_SMOOTH_DAYS = 10   # rolling average of range_pct for expansion comparison

REALIZED_VOL_DAYS = 20   # for realized vol computation
RETURN_PERIODS    = [1, 5, 20, 60]   # return lookback windows in trading days

# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------

def _load_daily(path: str, label: str) -> pd.DataFrame:
    """Load a daily parquet, normalize index to plain date strings."""
    if not os.path.exists(path):
        print(f"ERROR: {label} parquet not found:\n  {path}")
        sys.exit(1)

    df = pd.read_parquet(path)
    df = df.sort_index()

    # Normalize timezone-aware DatetimeIndex to plain date
    if hasattr(df.index, "tz") and df.index.tz is not None:
        df.index = df.index.tz_convert("America/New_York").normalize().tz_localize(None)
    else:
        df.index = pd.to_datetime(df.index).normalize()

    df.index = df.index.date   # convert to plain Python date objects
    df.index.name = "date"
    df = df[~df.index.duplicated(keep="last")]
    return df


# ---------------------------------------------------------------------------
# Feature construction
# ---------------------------------------------------------------------------

def _build_spy_features(spy: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame(index=spy.index)

    df["spy_close"]  = spy["close"].round(4)
    df["spy_open"]   = spy["open"].round(4)
    df["spy_high"]   = spy["high"].round(4)
    df["spy_low"]    = spy["low"].round(4)
    df["spy_volume"] = spy["volume"].round(0).astype("Int64")

    # Moving averages
    df["spy_sma20"]  = spy["close"].rolling(SMA_SHORT).mean().round(4)
    df["spy_sma50"]  = spy["close"].rolling(SMA_MEDIUM).mean().round(4)
    df["spy_sma200"] = spy["close"].rolling(SMA_LONG).mean().round(4)

    # Position flags  (1 = above, 0 = below, NaN if SMA not yet valid)
    df["spy_above_sma20"]  = (spy["close"] > df["spy_sma20"]).astype("Int8")
    df["spy_above_sma50"]  = (spy["close"] > df["spy_sma50"]).astype("Int8")
    df["spy_above_sma200"] = (spy["close"] > df["spy_sma200"]).astype("Int8")

    # SMA20 slope: 1 if today's sma20 > yesterday's sma20, else 0
    sma20_prev = df["spy_sma20"].shift(1)
    df["spy_sma20_slope_up"] = (df["spy_sma20"] > sma20_prev).astype("Int8")
    # Mark NaN where sma20 itself is NaN (first SMA_SHORT rows)
    df.loc[df["spy_sma20"].isna(), "spy_sma20_slope_up"] = pd.NA

    # Returns
    prev_close = spy["close"].shift(1)
    for n in RETURN_PERIODS:
        close_n_back = spy["close"].shift(n)
        df[f"spy_return_{n}d"] = ((spy["close"] - close_n_back) / close_n_back).round(6)

    # Gap proxy: (open_t - close_{t-1}) / close_{t-1}
    df["spy_gap_pct"] = ((spy["open"] - prev_close) / prev_close).round(6)

    # Daily range as fraction of close
    df["spy_range_pct"] = ((spy["high"] - spy["low"]) / spy["close"]).round(6)

    # Smoothed range (rolling mean for expansion baseline)
    df["spy_range_pct_sma10"] = df["spy_range_pct"].rolling(RANGE_SMOOTH_DAYS).mean().round(6)

    # Range expansion ratio  (>1 means today more volatile than recent average)
    df["spy_range_expansion"] = (
        df["spy_range_pct"] / df["spy_range_pct_sma10"]
    ).round(4)

    # Realized vol: annualized std of daily log returns over REALIZED_VOL_DAYS
    log_ret = np.log(spy["close"] / spy["close"].shift(1))
    df["spy_realized_vol_20d"] = (
        log_ret.rolling(REALIZED_VOL_DAYS).std() * np.sqrt(252)
    ).round(6)

    return df


def _build_qqq_features(qqq: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame(index=qqq.index)

    df["qqq_close"] = qqq["close"].round(4)

    sma20 = qqq["close"].rolling(SMA_SHORT).mean()
    sma50 = qqq["close"].rolling(SMA_MEDIUM).mean()

    df["qqq_above_sma20"] = (qqq["close"] > sma20).astype("Int8")
    df["qqq_above_sma50"] = (qqq["close"] > sma50).astype("Int8")

    prev_close = qqq["close"].shift(1)
    df["qqq_return_1d"] = ((qqq["close"] - prev_close) / prev_close).round(6)
    close_5_back = qqq["close"].shift(5)
    df["qqq_return_5d"] = ((qqq["close"] - close_5_back) / close_5_back).round(6)

    log_ret = np.log(qqq["close"] / qqq["close"].shift(1))
    df["qqq_realized_vol_20d"] = (
        log_ret.rolling(REALIZED_VOL_DAYS).std() * np.sqrt(252)
    ).round(6)

    return df


def _assign_regime_label(df: pd.DataFrame) -> pd.Series:
    """
    Three-bucket regime label based on SPY structural position only.

    bullish : spy_above_sma20 == 1 AND spy_above_sma50 == 1
              AND spy_sma20_slope_up == 1
    bearish : spy_above_sma20 == 0 AND spy_above_sma50 == 0
              AND spy_sma20_slope_up == 0
    neutral : all other combinations (including rows where any flag is NaN)
    """
    bullish = (
        (df["spy_above_sma20"] == 1)
        & (df["spy_above_sma50"] == 1)
        & (df["spy_sma20_slope_up"] == 1)
    )
    bearish = (
        (df["spy_above_sma20"] == 0)
        & (df["spy_above_sma50"] == 0)
        & (df["spy_sma20_slope_up"] == 0)
    )

    label = pd.Series("neutral", index=df.index, dtype=str)
    label[bullish] = "bullish"
    label[bearish] = "bearish"

    # Rows where any of the three flags is NaN (early warmup) -> mark explicitly
    missing_flags = (
        df["spy_above_sma20"].isna()
        | df["spy_above_sma50"].isna()
        | df["spy_sma20_slope_up"].isna()
    )
    label[missing_flags] = "warmup_na"

    return label


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------

def _build_summary(ctx: pd.DataFrame) -> pd.DataFrame:
    """
    Regime counts overall and by calendar year.
    """
    ctx = ctx.copy()
    ctx["year"] = [d.year for d in ctx.index]

    rows = []

    # Overall
    for regime, grp in ctx.groupby("market_regime_label"):
        rows.append({
            "period":              "all_years",
            "market_regime_label": regime,
            "trading_days":        len(grp),
            "pct_of_total":        round(len(grp) / len(ctx) * 100, 1),
        })

    # By year
    for yr, ydf in ctx.groupby("year"):
        for regime, grp in ydf.groupby("market_regime_label"):
            rows.append({
                "period":              str(yr),
                "market_regime_label": regime,
                "trading_days":        len(grp),
                "pct_of_total":        round(len(grp) / len(ydf) * 100, 1),
            })

    summary = pd.DataFrame(rows).sort_values(["period", "market_regime_label"])
    return summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("research_build_market_context_model_plan_next_day_day_trade")
    print("Track  : plan_next_day_day_trade")
    print("Phase  : phase_r1__market_context_model")
    print(f"Run date: {TODAY}")
    print("-" * 70)
    print(f"Inputs:")
    print(f"  SPY daily : {SPY_PARQUET}")
    print(f"  QQQ daily : {QQQ_PARQUET}")
    print(f"VIX         : NOT available in repo cache -- no VIX columns produced")
    print("-" * 70)
    print(f"SMA periods       : {SMA_SHORT} / {SMA_MEDIUM} / {SMA_LONG} days")
    print(f"Range smooth      : {RANGE_SMOOTH_DAYS} days")
    print(f"Realized vol      : {REALIZED_VOL_DAYS} days (annualized)")
    print(f"Return windows    : {RETURN_PERIODS} days")
    print("=" * 70)

    # -- Load -----------------------------------------------------------------

    spy = _load_daily(SPY_PARQUET, "SPY")
    qqq = _load_daily(QQQ_PARQUET, "QQQ")

    print(f"\nSPY loaded: {len(spy)} rows | "
          f"{spy.index[0]} -> {spy.index[-1]}")
    print(f"QQQ loaded: {len(qqq)} rows | "
          f"{qqq.index[0]} -> {qqq.index[-1]}")

    # -- Build feature blocks -------------------------------------------------

    spy_features = _build_spy_features(spy)
    qqq_features = _build_qqq_features(qqq)

    # -- Merge on date index --------------------------------------------------

    ctx = spy_features.join(qqq_features, how="left")

    # SPY-QQQ 1-day divergence
    ctx["spy_qqq_divergence_1d"] = (
        ctx["spy_return_1d"] - ctx["qqq_return_1d"]
    ).round(6)

    # -- Regime label ---------------------------------------------------------

    ctx["market_regime_label"] = _assign_regime_label(ctx)

    # -- Drop warmup_na rows from usable output (keep for inspection) ---------
    # We retain them in the CSV so researchers can see the warmup boundary,
    # but downstream research should filter to market_regime_label != 'warmup_na'

    total_rows    = len(ctx)
    warmup_rows   = (ctx["market_regime_label"] == "warmup_na").sum()
    usable_rows   = total_rows - warmup_rows

    print(f"\nContext table built:")
    print(f"  Total rows       : {total_rows}")
    print(f"  Warmup/NA rows   : {warmup_rows}  (market_regime_label = 'warmup_na')")
    print(f"  Usable rows      : {usable_rows}")

    # -- Regime distribution (usable rows only) -------------------------------

    usable = ctx[ctx["market_regime_label"] != "warmup_na"]
    regime_counts = usable["market_regime_label"].value_counts().sort_index()
    print(f"\nRegime distribution (usable rows, n={usable_rows}):")
    for regime, cnt in regime_counts.items():
        pct = cnt / usable_rows * 100
        print(f"  {regime:<10}: {cnt:>5} days  ({pct:.1f}%)")

    # -- Date coverage --------------------------------------------------------

    print(f"\nDate coverage:")
    print(f"  Full range   : {ctx.index[0]} -> {ctx.index[-1]}")
    usable_dates = usable.index
    print(f"  Usable range : {usable_dates[0]} -> {usable_dates[-1]}")

    # -- Write main output ----------------------------------------------------

    ctx_reset = ctx.copy()
    ctx_reset.index.name = "date"
    ctx_reset = ctx_reset.reset_index()
    ctx_reset["date"] = ctx_reset["date"].astype(str)

    main_csv = os.path.join(
        OUTPUT_DIR,
        "market_context_model_plan_next_day_day_trade.csv",
    )
    ctx_reset.to_csv(main_csv, index=False)
    print(f"\nMain output written:")
    print(f"  {main_csv}")
    print(f"  Rows: {len(ctx_reset)}  |  Columns: {len(ctx_reset.columns)}")
    print(f"  Columns: {list(ctx_reset.columns)}")

    # -- Write summary output -------------------------------------------------

    summary = _build_summary(ctx[ctx["market_regime_label"] != "warmup_na"])

    summary_csv = os.path.join(
        OUTPUT_DIR,
        "market_context_model_summary_plan_next_day_day_trade.csv",
    )
    summary.to_csv(summary_csv, index=False)
    print(f"\nSummary output written:")
    print(f"  {summary_csv}")
    print(f"\nRegime counts by period:")
    print(summary.to_string(index=False))

    print(f"\nDone. phase_r1__market_context_model output complete.")
    print(
        f"\nJoin instruction for later phases:\n"
        f"  Merge on 'date' (signal_day close date) using:\n"
        f"    market_context_model_plan_next_day_day_trade.csv\n"
        f"  Filter: market_regime_label != 'warmup_na' to exclude warmup rows."
    )


if __name__ == "__main__":
    main()
