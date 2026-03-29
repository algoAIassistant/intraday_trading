"""
research_run_gap_directional_trap_phase_r2_parent_baseline.py
Side:   research -- strategy family layer
Track:  plan_next_day_day_trade
Family: gap_directional_trap
Phase:  phase_r2__family_discovery_and_parent_baseline

Purpose:
  Materialize the first parent baseline for the gap_directional_trap family.

  This is a NEW family -- not a child of gap_continuation.
  It tests a different behavioral mechanism: stocks where the signal-day
  close structure OPPOSES the gap direction show modestly better next-day
  continuation of the gap direction.

  Source of hypothesis:
    gap_continuation phase_r4 batch_2 (2026-03-27): cl_opposed events in
    liquid_trend__large_gap + neutral showed 54.0% continuation (vs 51.4%
    baseline; n=2,026). This counterintuitive finding motivates a separate
    family baseline to test whether the effect generalizes.

Family definition (parent level -- intentionally broad):
  A gap_directional_trap parent event is a signal day where:
    1. |gap_pct| >= GAP_MIN_PCT (0.5%)
    2. signal_day_close_location OPPOSES the gap direction:
         gap_up events:   close_location < CL_OPPOSED_MAX (stock closed near low
                          despite the next-day gap being upward)
         gap_down events: close_location >= CL_OPPOSED_MIN (stock closed near high
                          despite the next-day gap being downward)
    3. quality cap: |gap_pct| <= QUALITY_CAP_PCT (30%)

  The next-day bet (when this reaches phase_r5) would be:
    trade IN the gap direction (same direction as gap_continuation)
    but the qualifying signal is the OPPOSING close structure.

  Possible mechanism:
    Participants who positioned themselves in the prior session's close direction
    (longs who sold weak into close, shorts who covered into a strong close) may
    be trapped when the gap reverses their assumed direction. This trapped
    positioning may resolve in the gap direction during the next session.

Why this is a separate family, not a child of gap_continuation:
  gap_continuation tests whether trending/high-rvol names continue the gap
  direction. Both children produced near-random results (~49% continuation).
  gap_directional_trap tests the same gap-direction trade, but the qualifying
  signal is the OPPOSING close structure -- a different behavioral hypothesis
  that should be researched independently with its own lineage.

What this script answers (parent level only):
  - How many cl_opposed gap events exist in the working universe?
  - What is the next-day opportunity envelope for cl_opposed gap events?
  - Does the effect hold across gap directions (up vs down)?
  - Does the effect vary by market regime?
  - Is the effect stable across years?
  - Does tightening the close_location threshold (very_opposed < 0.20 vs 0.35)
    strengthen or weaken the signal?

What this script does NOT do:
  - define stop or target logic
  - define entry rules
  - split into children or grandchildren
  - apply execution simulation
  - assume any reward:risk ratio
  - revisit gap_continuation grandchildren

Inputs:
  parent event rows from gap_continuation phase_r2 (reused as the raw event
  pool; gap_directional_trap applies the cl_opposed filter on top of those rows,
  which already contain signal_day_close_location for all 808,679 events)

Outputs (research_outputs/family_lineages/plan_next_day_day_trade/gap_directional_trap/phase_r2_parent_baseline/):
  parent_event_rows__gap_directional_trap__phase_r2__<DATE>.csv
  parent_summary__gap_directional_trap__phase_r2__<DATE>.csv
  parent_yearly_summary__gap_directional_trap__phase_r2__<DATE>.csv
  parent_threshold_sensitivity__gap_directional_trap__phase_r2__<DATE>.csv

Event row columns (same schema as gap_continuation phase_r2 + cl_band):
  ticker, signal_date, next_date,
  gap_pct, gap_direction,
  signal_day_close, signal_day_open, signal_day_range_pct, signal_day_close_location,
  signal_day_volume, signal_day_dollar_volume,
  price_bucket, adv_dollar_bucket,
  next_day_open, next_day_high, next_day_low, next_day_close,
  next_day_gap_pct,
  next_day_open_to_high_pct, next_day_open_to_low_pct,
  next_day_open_to_close_pct, next_day_range_pct,
  continuation_flag,
  market_regime_label,
  spy_return_1d, spy_return_5d, spy_range_expansion, spy_realized_vol_20d,
  cl_opposed_band    (very_opposed | moderate_opposed)
  gap_size_band      (small | medium | large)

Usage:
  python research_run_gap_directional_trap_phase_r2_parent_baseline.py

Dependencies:
  pip install pandas numpy
"""

import os
import sys
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

# Input: reuse gap_continuation parent event rows (contains all needed columns)
INPUT_CSV = os.path.join(
    REPO_ROOT,
    "1_0_strategy_research", "research_outputs",
    "family_lineages", "plan_next_day_day_trade",
    "gap_continuation", "phase_r2_parent_baseline",
    "parent_event_rows__gap_continuation__phase_r2__2026_03_27.csv",
)

OUTPUT_DIR = os.path.join(
    REPO_ROOT,
    "1_0_strategy_research", "research_outputs",
    "family_lineages", "plan_next_day_day_trade",
    "gap_directional_trap", "phase_r2_parent_baseline",
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

TODAY = datetime.date.today().strftime("%Y_%m_%d")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GAP_MIN_PCT      = 0.005   # 0.5% — same as gap_continuation parent
QUALITY_CAP_PCT  = 0.30    # |gap_pct| <= 30% (inherited quality cap)

# Broad parent threshold (default)
CL_OPPOSED_MAX   = 0.35    # gap_up events: close_location must be < this
CL_OPPOSED_MIN   = 0.65    # gap_down events: close_location must be >= this

# Within cl_opposed events: further band split
# gap_up:   very_opposed < 0.20,  moderate_opposed 0.20-0.35
# gap_down: very_opposed >= 0.80, moderate_opposed 0.65-0.80
CL_VERY_OPPOSED_UP   = 0.20
CL_VERY_OPPOSED_DOWN = 0.80

# Gap size bands (same as gap_continuation batch_1)
GAP_SMALL_MAX    = 0.015   # 0.5% to 1.5%
GAP_MEDIUM_MAX   = 0.030   # 1.5% to 3.0%
# large = >= 3.0%

# Threshold sensitivity test values
# For gap_up events: close_location < threshold (lower = stricter)
# For gap_down events: close_location >= (1 - threshold) (higher = stricter)
SENSITIVITY_THRESHOLDS = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45]

# ---------------------------------------------------------------------------
# Metric columns
# ---------------------------------------------------------------------------

_METRIC_COLS = [
    "next_day_open_to_high_pct",
    "next_day_open_to_low_pct",
    "next_day_open_to_close_pct",
    "next_day_range_pct",
    "continuation_flag",
]


def _metrics(sub: pd.DataFrame) -> dict:
    """Compute standard next-day metrics for a subset."""
    sv = sub.dropna(subset=_METRIC_COLS)
    n  = len(sub)
    nv = len(sv)
    if nv == 0:
        return {
            "n_events": n, "n_valid": 0,
            "continuation_rate_pct": None,
            "mean_nd_open_to_close_pct": None,
            "mean_nd_open_to_high_pct": None,
            "mean_nd_open_to_low_pct": None,
            "mean_nd_range_pct": None,
        }
    return {
        "n_events": n,
        "n_valid": nv,
        "continuation_rate_pct":   round(sv["continuation_flag"].mean() * 100, 2),
        "mean_nd_open_to_close_pct": round(sv["next_day_open_to_close_pct"].mean() * 100, 3),
        "mean_nd_open_to_high_pct":  round(sv["next_day_open_to_high_pct"].mean() * 100, 3),
        "mean_nd_open_to_low_pct":   round(sv["next_day_open_to_low_pct"].mean() * 100, 3),
        "mean_nd_range_pct":         round(sv["next_day_range_pct"].mean() * 100, 3),
    }


# ---------------------------------------------------------------------------
# cl_opposed filter
# ---------------------------------------------------------------------------

def _apply_cl_opposed_filter(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep only events where close_location opposes gap direction.
    Adds cl_opposed_band and gap_size_band columns.
    """
    gap_up   = df["gap_direction"] == "up"
    gap_down = df["gap_direction"] == "down"
    cl = df["signal_day_close_location"]

    opposed_up   = gap_up   & (cl < CL_OPPOSED_MAX)
    opposed_down = gap_down & (cl >= CL_OPPOSED_MIN)

    df = df[opposed_up | opposed_down].copy()

    # cl_opposed_band: further split within cl_opposed
    cl_band = pd.Series("moderate_opposed", index=df.index, dtype=str)
    gap_up_mask   = df["gap_direction"] == "up"
    gap_down_mask = df["gap_direction"] == "down"
    cl2 = df["signal_day_close_location"]
    cl_band[gap_up_mask   & (cl2 < CL_VERY_OPPOSED_UP)]   = "very_opposed"
    cl_band[gap_down_mask & (cl2 >= CL_VERY_OPPOSED_DOWN)] = "very_opposed"
    df["cl_opposed_band"] = cl_band

    # gap_size_band
    abs_gap = df["gap_pct"].abs()
    size_band = pd.Series("large", index=df.index, dtype=str)
    size_band[abs_gap < GAP_MEDIUM_MAX] = "medium"
    size_band[abs_gap < GAP_SMALL_MAX]  = "small"
    df["gap_size_band"] = size_band

    return df


# ---------------------------------------------------------------------------
# Summary builders
# ---------------------------------------------------------------------------

def _build_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate parent-level metrics by:
      - overall (all directions, all regimes)
      - gap direction
      - regime
      - direction × regime
      - cl_opposed_band
      - gap_size_band
      - cl_opposed_band × gap_direction
      - gap_size_band × gap_direction
    """
    rows = []

    def _add(label: str, sub: pd.DataFrame) -> None:
        if len(sub) == 0:
            return
        row = {"slice_label": label}
        row.update(_metrics(sub))
        rows.append(row)

    # Overall
    _add("all__all_regimes", df)

    # By gap direction
    for d in ["up", "down"]:
        _add(f"{d}__all_regimes", df[df["gap_direction"] == d])

    # By regime
    for r in ["bullish", "neutral", "bearish"]:
        _add(f"all_directions__{r}", df[df["market_regime_label"] == r])

    # Direction × regime
    for d in ["up", "down"]:
        for r in ["bullish", "neutral", "bearish"]:
            sub = df[(df["gap_direction"] == d) & (df["market_regime_label"] == r)]
            _add(f"{d}__{r}", sub)

    # By cl_opposed_band
    for band in ["very_opposed", "moderate_opposed"]:
        _add(f"all_directions__{band}", df[df["cl_opposed_band"] == band])

    # cl_opposed_band × gap_direction
    for band in ["very_opposed", "moderate_opposed"]:
        for d in ["up", "down"]:
            sub = df[(df["cl_opposed_band"] == band) & (df["gap_direction"] == d)]
            _add(f"{d}__{band}", sub)

    # By gap_size_band
    for gs in ["small", "medium", "large"]:
        _add(f"all_directions__{gs}_gap", df[df["gap_size_band"] == gs])
        for d in ["up", "down"]:
            sub = df[(df["gap_size_band"] == gs) & (df["gap_direction"] == d)]
            _add(f"{d}__{gs}_gap", sub)

    return pd.DataFrame(rows)


def _build_yearly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Year × gap_direction × basic metrics."""
    df = df.copy()
    df["year"] = df["signal_date"].str[:4].astype(int)
    rows = []
    for yr in sorted(df["year"].unique()):
        for d in ["up", "down", "all"]:
            if d == "all":
                sub = df[df["year"] == yr]
            else:
                sub = df[(df["year"] == yr) & (df["gap_direction"] == d)]
            if len(sub) == 0:
                continue
            sv = sub.dropna(subset=_METRIC_COLS)
            rows.append({
                "year":                       yr,
                "gap_direction":              d,
                "n_events":                   len(sub),
                "continuation_rate_pct":      round(sv["continuation_flag"].mean() * 100, 2) if len(sv) else None,
                "mean_nd_open_to_close_pct":  round(sv["next_day_open_to_close_pct"].mean() * 100, 3) if len(sv) else None,
                "mean_nd_range_pct":          round(sv["next_day_range_pct"].mean() * 100, 3) if len(sv) else None,
            })
    return pd.DataFrame(rows)


def _build_threshold_sensitivity(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    For each threshold in SENSITIVITY_THRESHOLDS, apply the cl_opposed filter at that
    threshold and report continuation rate + sample size (all regimes, direction split).

    gap_up events:   close_location < threshold  (lower = stricter)
    gap_down events: close_location >= (1 - threshold)
    """
    rows = []
    for thresh in SENSITIVITY_THRESHOLDS:
        gap_up_mask   = raw_df["gap_direction"] == "up"
        gap_down_mask = raw_df["gap_direction"] == "down"
        cl = raw_df["signal_day_close_location"]

        for d, mask in [("up", gap_up_mask), ("down", gap_down_mask)]:
            if d == "up":
                sub = raw_df[mask & (cl < thresh)]
            else:
                sub = raw_df[mask & (cl >= (1.0 - thresh))]

            sv = sub.dropna(subset=_METRIC_COLS)
            rows.append({
                "cl_threshold":               thresh,
                "gap_direction":              d,
                "n_events":                   len(sub),
                "n_valid":                    len(sv),
                "continuation_rate_pct":      round(sv["continuation_flag"].mean() * 100, 2) if len(sv) else None,
                "mean_nd_open_to_close_pct":  round(sv["next_day_open_to_close_pct"].mean() * 100, 3) if len(sv) else None,
                "mean_nd_range_pct":          round(sv["next_day_range_pct"].mean() * 100, 3) if len(sv) else None,
            })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Console helpers
# ---------------------------------------------------------------------------

def _fmt(label: str, row: dict) -> str:
    """Format one summary row for console output."""
    n   = row.get("n_events", 0)
    cr  = row.get("continuation_rate_pct")
    oc  = row.get("mean_nd_open_to_close_pct")
    rng = row.get("mean_nd_range_pct")
    cr_s  = f"{cr:.1f}%" if cr is not None else "  n/a"
    oc_s  = f"{oc:+.3f}%" if oc is not None else "   n/a"
    rng_s = f"{rng:.3f}%" if rng is not None else "  n/a"
    return f"  {label:<45}  n={n:>7,}  cont={cr_s}  o->c={oc_s}  range={rng_s}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 80)
    print("research_run_gap_directional_trap_phase_r2_parent_baseline")
    print("Track  : plan_next_day_day_trade")
    print("Family : gap_directional_trap  [NEW — not a child of gap_continuation]")
    print("Phase  : phase_r2__family_discovery_and_parent_baseline")
    print(f"Run date: {TODAY}")
    print("-" * 80)
    print(f"Parent definition:")
    print(f"  |gap_pct| >= {GAP_MIN_PCT * 100:.1f}%  AND  |gap_pct| <= {QUALITY_CAP_PCT * 100:.0f}%")
    print(f"  gap_up:   close_location < {CL_OPPOSED_MAX}  (closed near low; gap is up)")
    print(f"  gap_down: close_location >= {CL_OPPOSED_MIN}  (closed near high; gap is down)")
    print("=" * 80)

    # -- Load gap_continuation parent event rows (reused as raw input pool) --

    if not os.path.exists(INPUT_CSV):
        print(f"\nERROR: input CSV not found:\n  {INPUT_CSV}")
        print("Run research_run_gap_continuation_phase_r2_parent_baseline.py first.")
        sys.exit(1)

    print(f"\nLoading gap_continuation parent event rows ...")
    raw = pd.read_csv(INPUT_CSV, low_memory=False)
    print(f"  Loaded: {len(raw):,} rows")

    # Verify required columns
    required_cols = {
        "gap_pct", "gap_direction", "signal_day_close_location",
        "signal_day_range_pct", "market_regime_label",
        "next_day_open_to_high_pct", "next_day_open_to_low_pct",
        "next_day_open_to_close_pct", "next_day_range_pct",
        "continuation_flag", "signal_date",
    }
    missing = required_cols - set(raw.columns)
    if missing:
        print(f"\nERROR: missing columns in input CSV: {missing}")
        sys.exit(1)

    # Apply quality cap
    before = len(raw)
    raw = raw[raw["gap_pct"].abs() <= QUALITY_CAP_PCT].copy()
    dropped_qc = before - len(raw)
    print(f"  After quality cap (|gap_pct| <= {QUALITY_CAP_PCT * 100:.0f}%): {len(raw):,} rows "
          f"(removed {dropped_qc:,} data-error events)")

    # Drop rows without market context (already clean in the parent rows but be safe)
    raw = raw.dropna(subset=["market_regime_label"])
    raw = raw[raw["market_regime_label"] != "warmup_na"]
    print(f"  After market context filter: {len(raw):,} rows")

    # Drop rows with no close_location (zero-range candles)
    raw = raw.dropna(subset=["signal_day_close_location"])
    print(f"  After close_location filter (remove zero-range candles): {len(raw):,} rows")

    print(f"\nThis is the full gap_continuation parent pool before cl_opposed filter.")

    # -- Apply cl_opposed filter to get gap_directional_trap parent events ---

    df = _apply_cl_opposed_filter(raw)
    n_trap = len(df)
    pct_of_parent = n_trap / len(raw) * 100

    print(f"\ngap_directional_trap parent events (cl_opposed filter applied):")
    print(f"  Total              : {n_trap:,} ({pct_of_parent:.1f}% of quality-filtered parent pool)")

    gap_up   = (df["gap_direction"] == "up").sum()
    gap_down = (df["gap_direction"] == "down").sum()
    print(f"  Gap up (cl_low)    : {gap_up:,}  ({gap_up / n_trap * 100:.1f}%)")
    print(f"  Gap down (cl_high) : {gap_down:,}  ({gap_down / n_trap * 100:.1f}%)")

    # cl_opposed_band split
    very   = (df["cl_opposed_band"] == "very_opposed").sum()
    mod    = (df["cl_opposed_band"] == "moderate_opposed").sum()
    print(f"\n  cl_opposed_band split:")
    print(f"    very_opposed     : {very:,}  ({very / n_trap * 100:.1f}%)  "
          f"[gap_up cl<{CL_VERY_OPPOSED_UP}, gap_down cl>={CL_VERY_OPPOSED_DOWN}]")
    print(f"    moderate_opposed : {mod:,}  ({mod / n_trap * 100:.1f}%)")

    # Gap size split
    for gs in ["small", "medium", "large"]:
        cnt = (df["gap_size_band"] == gs).sum()
        print(f"  {gs}_gap              : {cnt:,}  ({cnt / n_trap * 100:.1f}%)")

    # Regime split
    regime_counts = df["market_regime_label"].value_counts()
    print(f"\n  Market regime split:")
    for r, cnt in regime_counts.items():
        print(f"    {r:<10}: {cnt:,}  ({cnt / n_trap * 100:.1f}%)")

    # Date coverage
    dates = pd.to_datetime(df["signal_date"])
    print(f"\n  Date coverage:")
    print(f"    {dates.min().date()} to {dates.max().date()}")
    n_tickers = df["ticker"].nunique()
    print(f"  Unique tickers: {n_tickers:,}")

    # -- Summary metrics ------------------------------------------------------

    valid = df.dropna(subset=_METRIC_COLS)
    print(f"\nNext-day envelope — gap_directional_trap parent (all, n={len(valid):,}):")
    print(f"  Continuation rate  : {valid['continuation_flag'].mean() * 100:.2f}%")
    print(f"  Mean open->close   : {valid['next_day_open_to_close_pct'].mean() * 100:+.3f}%")
    print(f"  Mean open->high    : {valid['next_day_open_to_high_pct'].mean() * 100:+.3f}%")
    print(f"  Mean open->low     : {valid['next_day_open_to_low_pct'].mean() * 100:+.3f}%")
    print(f"  Mean daily range   : {valid['next_day_range_pct'].mean() * 100:.3f}%")

    print(f"\nFor comparison — full parent pool (before cl_opposed):")
    raw_v = raw.dropna(subset=_METRIC_COLS)
    print(f"  Continuation rate  : {raw_v['continuation_flag'].mean() * 100:.2f}%")
    print(f"  Mean open->close   : {raw_v['next_day_open_to_close_pct'].mean() * 100:+.3f}%")
    print(f"  Mean daily range   : {raw_v['next_day_range_pct'].mean() * 100:.3f}%")
    print(f"  (n={len(raw_v):,})")

    # -- Build and write summaries --------------------------------------------

    summary_df   = _build_summary(df)
    yearly_df    = _build_yearly_summary(df)
    threshold_df = _build_threshold_sensitivity(raw)

    events_file    = os.path.join(OUTPUT_DIR,
        f"parent_event_rows__gap_directional_trap__phase_r2__{TODAY}.csv")
    summary_file   = os.path.join(OUTPUT_DIR,
        f"parent_summary__gap_directional_trap__phase_r2__{TODAY}.csv")
    yearly_file    = os.path.join(OUTPUT_DIR,
        f"parent_yearly_summary__gap_directional_trap__phase_r2__{TODAY}.csv")
    threshold_file = os.path.join(OUTPUT_DIR,
        f"parent_threshold_sensitivity__gap_directional_trap__phase_r2__{TODAY}.csv")

    df.to_csv(events_file,    index=False)
    summary_df.to_csv(summary_file,   index=False)
    yearly_df.to_csv(yearly_file,     index=False)
    threshold_df.to_csv(threshold_file, index=False)

    print(f"\nOutputs written:")
    print(f"  Event rows          : {events_file}")
    print(f"                        ({len(df):,} rows)")
    print(f"  Summary             : {summary_file}")
    print(f"  Yearly summary      : {yearly_file}")
    print(f"  Threshold sensitivity: {threshold_file}")

    # -- Print key slices -----------------------------------------------------

    print(f"\n{'=' * 80}")
    print(f"KEY SUMMARY SLICES")
    print(f"{'=' * 80}")

    summary_lookup = summary_df.set_index("slice_label").to_dict("index")

    print(f"\n--- OVERALL vs DIRECTION SPLIT ---")
    for lbl in ["all__all_regimes", "up__all_regimes", "down__all_regimes"]:
        if lbl in summary_lookup:
            print(_fmt(lbl, summary_lookup[lbl]))

    print(f"\n--- BY REGIME (all directions) ---")
    for r in ["bullish", "neutral", "bearish"]:
        lbl = f"all_directions__{r}"
        if lbl in summary_lookup:
            print(_fmt(lbl, summary_lookup[lbl]))

    print(f"\n--- DIRECTION x REGIME ---")
    for d in ["up", "down"]:
        for r in ["bullish", "neutral", "bearish"]:
            lbl = f"{d}__{r}"
            if lbl in summary_lookup:
                print(_fmt(lbl, summary_lookup[lbl]))

    print(f"\n--- cl_opposed_band (within cl_opposed events) ---")
    for band in ["very_opposed", "moderate_opposed"]:
        lbl = f"all_directions__{band}"
        if lbl in summary_lookup:
            print(_fmt(lbl, summary_lookup[lbl]))
    for band in ["very_opposed", "moderate_opposed"]:
        for d in ["up", "down"]:
            lbl = f"{d}__{band}"
            if lbl in summary_lookup:
                print(_fmt(lbl, summary_lookup[lbl]))

    print(f"\n--- GAP SIZE (within cl_opposed events) ---")
    for gs in ["small", "medium", "large"]:
        lbl = f"all_directions__{gs}_gap"
        if lbl in summary_lookup:
            print(_fmt(lbl, summary_lookup[lbl]))
        for d in ["up", "down"]:
            lbl = f"{d}__{gs}_gap"
            if lbl in summary_lookup:
                print(_fmt(lbl, summary_lookup[lbl]))

    print(f"\n--- YEARLY STABILITY (all directions combined) ---")
    yearly_all = yearly_df[yearly_df["gap_direction"] == "all"]
    for _, row in yearly_all.iterrows():
        cr = row["continuation_rate_pct"]
        oc = row["mean_nd_open_to_close_pct"]
        rng = row["mean_nd_range_pct"]
        print(f"  {int(row['year'])}  n={int(row['n_events']):>7,}  "
              f"cont={cr:.1f}%  o->c={oc:+.3f}%  range={rng:.3f}%")

    print(f"\n--- THRESHOLD SENSITIVITY (all regimes) ---")
    print(f"  {'thresh':<8}  {'direction':<6}  {'n':>8}  {'cont%':>7}  {'o->c%':>8}  {'range%':>8}")
    for _, row in threshold_df.iterrows():
        cr  = f"{row['continuation_rate_pct']:.1f}" if pd.notna(row['continuation_rate_pct']) else "  n/a"
        oc  = f"{row['mean_nd_open_to_close_pct']:+.3f}" if pd.notna(row['mean_nd_open_to_close_pct']) else "   n/a"
        rng = f"{row['mean_nd_range_pct']:.3f}" if pd.notna(row['mean_nd_range_pct']) else "  n/a"
        print(f"  {row['cl_threshold']:<8.2f}  {row['gap_direction']:<6}  "
              f"{int(row['n_events']):>8,}  {cr:>7}  {oc:>8}  {rng:>8}")

    print(f"\n{'=' * 80}")
    print(f"phase_r2 parent baseline for gap_directional_trap complete.")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
