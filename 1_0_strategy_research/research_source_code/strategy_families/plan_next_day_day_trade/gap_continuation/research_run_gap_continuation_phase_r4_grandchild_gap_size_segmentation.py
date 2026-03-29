"""
research_run_gap_continuation_phase_r4_grandchild_gap_size_segmentation.py
Side:   research -- strategy family layer
Track:  plan_next_day_day_trade
Family: gap_continuation
Phase:  phase_r4__grandchild_parameter_research

Purpose:
  First grandchild-level structural segmentation for gap_continuation.

  Segments the two surviving phase_r3 children by gap size to find whether
  meaningful behavioral structure emerges when small/medium/large gaps are
  separated. This is the primary structural hypothesis from phase_r3.

  This phase does NOT define execution templates, stops, or targets.
  It answers: does gap SIZE segmentation expose real structural improvement?

Children tested (from phase_r3):
  - gap_continuation__liquid_trend_names
  - gap_continuation__high_rvol_names

Gap size bands (primary new dimension):
  small_gap  : 0.5% <= |gap_pct| < 1.5%
  medium_gap : 1.5% <= |gap_pct| < 3.0%
  large_gap  : 3.0% <= |gap_pct| <= 30.0%  (quality cap already applied in phase_r3)

Secondary comparison cuts (reporting only; do not create permanent new grandchildren
from these alone):
  - gap direction: up vs down
  - market regime: bullish / neutral / bearish
  - price bucket: 5_to_20 / 20_to_50 / 50_to_100 / 100_plus (signal_day_close)

Grandchild names (6 defined in this batch):
  gap_continuation__liquid_trend_names__small_gap
  gap_continuation__liquid_trend_names__medium_gap
  gap_continuation__liquid_trend_names__large_gap
  gap_continuation__high_rvol_names__small_gap
  gap_continuation__high_rvol_names__medium_gap
  gap_continuation__high_rvol_names__large_gap

Inputs:
  phase_r3 child event rows CSV
  phase_r2 parent event rows CSV (for reference comparison baseline)

Outputs (research_outputs/.../gap_continuation/phase_r4_structural_validation/):
  grandchild_event_rows__gap_continuation__phase_r4__<DATE>.csv
  grandchild_summary__gap_continuation__phase_r4__<DATE>.csv
  grandchild_comparison__gap_continuation__phase_r4__<DATE>.csv
  regime_split_summary__gap_continuation__phase_r4__<DATE>.csv
  price_bucket_summary__gap_continuation__phase_r4__<DATE>.csv
  grandchild_yearly_summary__gap_continuation__phase_r4__<DATE>.csv

Usage:
  python research_run_gap_continuation_phase_r4_grandchild_gap_size_segmentation.py

Dependencies:
  pip install pandas pyarrow numpy
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

CHILD_EVENTS_CSV = os.path.join(
    REPO_ROOT,
    "1_0_strategy_research", "research_outputs",
    "family_lineages", "plan_next_day_day_trade",
    "gap_continuation", "phase_r3_child_isolation",
    "child_event_rows__gap_continuation__phase_r3__2026_03_27.csv",
)

PARENT_EVENTS_CSV = os.path.join(
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
    "gap_continuation", "phase_r4_structural_validation",
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

TODAY = datetime.date.today().strftime("%Y_%m_%d")

# ---------------------------------------------------------------------------
# Gap size band thresholds  <-- tune here if needed
# ---------------------------------------------------------------------------

# Data quality cap -- must match phase_r3 (already applied upstream)
GAP_QUALITY_CAP = 0.30   # 30%; re-applied when loading parent for reference

# Gap size band boundaries (absolute gap_pct, unitless decimals)
GAP_SMALL_MIN  = 0.005   # 0.5%  -- same as phase_r2 event detection minimum
GAP_SMALL_MAX  = 0.015   # 1.5%
GAP_MEDIUM_MIN = 0.015   # 1.5%
GAP_MEDIUM_MAX = 0.030   # 3.0%
GAP_LARGE_MIN  = 0.030   # 3.0%

# Price bucket edges for the simplified r4 reporting layer
# These map signal_day_close into 5 buckets; below_5 should rarely appear
# since phase_r0 already requires close >= $5
PRICE_BUCKET_EDGES  = [0, 5, 20, 50, 100, float("inf")]
PRICE_BUCKET_LABELS = ["below_5", "5_to_20", "20_to_50", "50_to_100", "100_plus"]

# Order in which we display grandchildren in console output
GC_ORDER = [
    "gap_continuation__liquid_trend_names__small_gap",
    "gap_continuation__liquid_trend_names__medium_gap",
    "gap_continuation__liquid_trend_names__large_gap",
    "gap_continuation__high_rvol_names__small_gap",
    "gap_continuation__high_rvol_names__medium_gap",
    "gap_continuation__high_rvol_names__large_gap",
]

# ---------------------------------------------------------------------------
# Column assignment helpers
# ---------------------------------------------------------------------------

def _assign_gap_size_band(df: pd.DataFrame) -> pd.Series:
    """Map |gap_pct| to small / medium / large band labels."""
    abs_gap = df["gap_pct"].abs()
    bands = pd.Series("other", index=df.index, dtype=str)
    bands[(abs_gap >= GAP_SMALL_MIN) & (abs_gap < GAP_SMALL_MAX)]   = "small_gap"
    bands[(abs_gap >= GAP_MEDIUM_MIN) & (abs_gap < GAP_MEDIUM_MAX)] = "medium_gap"
    bands[abs_gap >= GAP_LARGE_MIN]                                  = "large_gap"
    return bands


def _assign_price_bucket_r4(df: pd.DataFrame) -> pd.Series:
    """Simplified 5-bucket price grouping from signal_day_close."""
    return pd.cut(
        df["signal_day_close"],
        bins=PRICE_BUCKET_EDGES,
        labels=PRICE_BUCKET_LABELS,
        right=False,
    ).astype(str)


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------

_METRIC_COLS = [
    "continuation_flag",
    "next_day_open_to_close_pct",
    "next_day_open_to_high_pct",
    "next_day_open_to_low_pct",
    "next_day_range_pct",
]


def _metrics(df: pd.DataFrame) -> dict:
    """Compute standard metrics for a subset DataFrame."""
    v = df.dropna(subset=_METRIC_COLS[:2])
    n  = len(df)
    nv = len(v)
    if nv == 0:
        return {
            "n_events": n, "n_with_next_day": 0,
            "continuation_rate_pct": None,
            "mean_nd_open_to_close_pct": None,
            "mean_nd_open_to_high_pct":  None,
            "mean_nd_open_to_low_pct":   None,
            "mean_nd_range_pct":         None,
        }
    return {
        "n_events":                    n,
        "n_with_next_day":             nv,
        "continuation_rate_pct":       round(float(v["continuation_flag"].mean()) * 100, 2),
        "mean_nd_open_to_close_pct":   round(float(v["next_day_open_to_close_pct"].mean()) * 100, 3),
        "mean_nd_open_to_high_pct":    round(float(v["next_day_open_to_high_pct"].mean()) * 100, 3),
        "mean_nd_open_to_low_pct":     round(float(v["next_day_open_to_low_pct"].mean()) * 100, 3),
        "mean_nd_range_pct":           round(float(v["next_day_range_pct"].mean()) * 100, 3),
    }


# ---------------------------------------------------------------------------
# Summary table builders
# ---------------------------------------------------------------------------

def _build_grandchild_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    One row per grandchild x slice.
    Slices: all, each direction, each regime, each direction x regime combo.
    """
    rows = []
    for gc_name in GC_ORDER:
        gdf = df[df["grandchild_name"] == gc_name]
        if len(gdf) == 0:
            continue

        def _add(slice_label: str, sub: pd.DataFrame) -> None:
            row = {"grandchild_name": gc_name, "slice": slice_label}
            row.update(_metrics(sub))
            rows.append(row)

        _add("all=all", gdf)
        for d in ["up", "down"]:
            _add(f"gap_direction={d}", gdf[gdf["gap_direction"] == d])
        for r in ["bullish", "neutral", "bearish"]:
            _add(f"market_regime={r}", gdf[gdf["market_regime_label"] == r])
        for d in ["up", "down"]:
            for r in ["bullish", "neutral", "bearish"]:
                sub = gdf[(gdf["gap_direction"] == d) & (gdf["market_regime_label"] == r)]
                _add(f"gap_{d}_x_regime={r}", sub)

    return pd.DataFrame(rows)


def _build_comparison(
    parent_q: pd.DataFrame,
    child1: pd.DataFrame,
    child2: pd.DataFrame,
    gc_dfs: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """
    Comparison table: rows = slice x metric, columns = parent + 2 children + 6 grandchildren.
    Dataset column names are shortened for readability.
    """
    slices = [
        ("all",          lambda df: df),
        ("gap_up",       lambda df: df[df["gap_direction"] == "up"]),
        ("gap_down",     lambda df: df[df["gap_direction"] == "down"]),
        ("bullish",      lambda df: df[df["market_regime_label"] == "bullish"]),
        ("neutral",      lambda df: df[df["market_regime_label"] == "neutral"]),
        ("bearish",      lambda df: df[df["market_regime_label"] == "bearish"]),
    ]

    def _safe(df: pd.DataFrame, col: str) -> float | None:
        v = df[col].dropna()
        return round(float(v.mean()) * 100, 3) if len(v) > 0 else None

    metric_fns = [
        ("n_events",              lambda df: len(df)),
        ("continuation_rate_pct", lambda df: round(df["continuation_flag"].dropna().mean() * 100, 2) if df["continuation_flag"].notna().any() else None),
        ("mean_nd_open_to_close", lambda df: _safe(df, "next_day_open_to_close_pct")),
        ("mean_nd_range_pct",     lambda df: _safe(df, "next_day_range_pct")),
        ("mean_nd_open_to_high",  lambda df: _safe(df, "next_day_open_to_high_pct")),
        ("mean_nd_open_to_low",   lambda df: _safe(df, "next_day_open_to_low_pct")),
    ]

    # Column name mapping: short readable names
    datasets = [
        ("parent_quality_filtered", parent_q),
        ("child1_liquid_trend",     child1),
        ("child2_high_rvol",        child2),
    ] + [
        (gc.replace("gap_continuation__", "").replace("_names", ""), gdf)
        for gc, gdf in gc_dfs.items()
    ]

    rows = []
    for slice_name, slice_fn in slices:
        for metric_name, metric_fn in metric_fns:
            row = {"slice": slice_name, "metric": metric_name}
            for ds_name, ds in datasets:
                sub = slice_fn(ds)
                try:
                    row[ds_name] = metric_fn(sub) if len(sub) > 0 else None
                except Exception:
                    row[ds_name] = None
            rows.append(row)

    return pd.DataFrame(rows)


def _build_regime_split(df: pd.DataFrame) -> pd.DataFrame:
    """Grandchild x regime x direction breakdown."""
    rows = []
    for gc_name in GC_ORDER:
        gdf = df[df["grandchild_name"] == gc_name]
        if len(gdf) == 0:
            continue
        for regime in ["bullish", "neutral", "bearish"]:
            for direction in ["all", "up", "down"]:
                sub = gdf[gdf["market_regime_label"] == regime]
                if direction != "all":
                    sub = sub[sub["gap_direction"] == direction]
                row = {
                    "grandchild_name": gc_name,
                    "market_regime":   regime,
                    "gap_direction":   direction,
                }
                row.update(_metrics(sub))
                rows.append(row)
    return pd.DataFrame(rows)


def _build_price_bucket_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Grandchild x price_bucket_r4 breakdown."""
    rows = []
    for gc_name in GC_ORDER:
        gdf = df[df["grandchild_name"] == gc_name]
        if len(gdf) == 0:
            continue
        for pb in ["5_to_20", "20_to_50", "50_to_100", "100_plus"]:
            sub = gdf[gdf["price_bucket_r4"] == pb]
            row = {"grandchild_name": gc_name, "price_bucket": pb}
            row.update(_metrics(sub))
            rows.append(row)
    return pd.DataFrame(rows)


def _build_yearly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Grandchild x year breakdown."""
    rows = []
    df = df.copy()
    df["year"] = df["signal_date"].str[:4].astype(int)
    for gc_name in GC_ORDER:
        gdf = df[df["grandchild_name"] == gc_name]
        if len(gdf) == 0:
            continue
        for yr in sorted(gdf["year"].unique()):
            sub = gdf[gdf["year"] == yr]
            if len(sub) < 5:
                continue
            row = {"grandchild_name": gc_name, "year": yr}
            row.update(_metrics(sub))
            rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Console print helpers
# ---------------------------------------------------------------------------

def _fmt(val, fmt_str: str = "+.3f", none_str: str = "—") -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return none_str
    try:
        return format(val, fmt_str)
    except Exception:
        return str(val)


def _print_main_summary(summary_df: pd.DataFrame) -> None:
    all_rows = summary_df[summary_df["slice"] == "all=all"]
    w = 57
    print(f"\n{'='*85}")
    print("  GRANDCHILD SUMMARY — all events (no direction or regime slice)")
    print(f"{'='*85}")
    print(f"  {'grandchild':<{w}}  {'n':>8}  {'cont%':>6}  {'o->c%':>7}  {'o->h%':>7}  {'range%':>7}")
    print(f"  {'-'*w}  {'--------':>8}  {'------':>6}  {'-------':>7}  {'-------':>7}  {'-------':>7}")
    for gc in GC_ORDER:
        r = all_rows[all_rows["grandchild_name"] == gc]
        if len(r) == 0:
            continue
        r = r.iloc[0]
        print(
            f"  {gc:<{w}}"
            f"  {int(r['n_events']):>8,}"
            f"  {_fmt(r['continuation_rate_pct'], '.1f'):>6}"
            f"  {_fmt(r['mean_nd_open_to_close_pct'], '+.3f'):>7}"
            f"  {_fmt(r['mean_nd_open_to_high_pct'], '+.3f'):>7}"
            f"  {_fmt(r['mean_nd_range_pct'], '.3f'):>7}"
        )


def _print_direction_table(summary_df: pd.DataFrame) -> None:
    w = 57
    print(f"\n{'='*85}")
    print("  DIRECTION BREAKDOWN: gap_up vs gap_down")
    print(f"{'='*85}")
    print(f"  {'grandchild':<{w}}  {'dir':>5}  {'n':>8}  {'cont%':>6}  {'o->c%':>7}")
    print(f"  {'-'*w}  {'-----':>5}  {'--------':>8}  {'------':>6}  {'-------':>7}")
    for gc in GC_ORDER:
        for direction in ["up", "down"]:
            slice_label = f"gap_direction={direction}"
            r = summary_df[(summary_df["grandchild_name"] == gc) & (summary_df["slice"] == slice_label)]
            if len(r) == 0:
                continue
            r = r.iloc[0]
            print(
                f"  {gc:<{w}}"
                f"  {direction:>5}"
                f"  {int(r['n_events']):>8,}"
                f"  {_fmt(r['continuation_rate_pct'], '.1f'):>6}"
                f"  {_fmt(r['mean_nd_open_to_close_pct'], '+.3f'):>7}"
            )


def _print_regime_table(regime_df: pd.DataFrame) -> None:
    w = 57
    all_dir = regime_df[regime_df["gap_direction"] == "all"]
    print(f"\n{'='*85}")
    print("  REGIME BREAKDOWN — continuation_rate_pct (all directions)")
    print(f"{'='*85}")
    print(f"  {'grandchild':<{w}}  {'bull n':>7}  {'bull%':>5}  {'neut n':>7}  {'neut%':>5}  {'bear n':>7}  {'bear%':>5}")
    print(f"  {'-'*w}  {'-------':>7}  {'-----':>5}  {'-------':>7}  {'-----':>5}  {'-------':>7}  {'-----':>5}")
    for gc in GC_ORDER:
        sub = all_dir[all_dir["grandchild_name"] == gc]
        vals = {}
        ns   = {}
        for regime in ["bullish", "neutral", "bearish"]:
            rr = sub[sub["market_regime"] == regime]
            vals[regime] = _fmt(rr.iloc[0]["continuation_rate_pct"], ".1f") if len(rr) > 0 else "—"
            ns[regime]   = int(rr.iloc[0]["n_events"]) if len(rr) > 0 else 0
        print(
            f"  {gc:<{w}}"
            f"  {ns['bullish']:>7,}  {vals['bullish']:>5}"
            f"  {ns['neutral']:>7,}  {vals['neutral']:>5}"
            f"  {ns['bearish']:>7,}  {vals['bearish']:>5}"
        )


def _print_yearly(yearly_df: pd.DataFrame, gc_name: str) -> None:
    sub = yearly_df[yearly_df["grandchild_name"] == gc_name]
    if len(sub) == 0:
        return
    print(f"\n  Yearly — {gc_name}")
    print(f"  {'year':>4}  {'n':>7}  {'cont%':>6}  {'o->c%':>7}  {'range%':>7}")
    for _, r in sub.sort_values("year").iterrows():
        print(
            f"  {int(r['year']):>4}"
            f"  {int(r['n_events']):>7,}"
            f"  {_fmt(r['continuation_rate_pct'], '.1f'):>6}"
            f"  {_fmt(r['mean_nd_open_to_close_pct'], '+.3f'):>7}"
            f"  {_fmt(r['mean_nd_range_pct'], '.3f'):>7}"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 85)
    print("research_run_gap_continuation_phase_r4_grandchild_gap_size_segmentation")
    print("Track  : plan_next_day_day_trade")
    print("Family : gap_continuation")
    print("Phase  : phase_r4__grandchild_parameter_research")
    print(f"Run date: {TODAY}")
    print("-" * 85)
    print("Gap size bands:")
    print(f"  small_gap  : {GAP_SMALL_MIN*100:.1f}% <= |gap_pct| < {GAP_SMALL_MAX*100:.1f}%")
    print(f"  medium_gap : {GAP_MEDIUM_MIN*100:.1f}% <= |gap_pct| < {GAP_MEDIUM_MAX*100:.1f}%")
    print(f"  large_gap  : |gap_pct| >= {GAP_LARGE_MIN*100:.1f}%")
    print("=" * 85)

    # -- Load parent events (reference baseline) ----------------------------

    print(f"\n[1] Loading parent events from phase_r2 (reference baseline) ...")
    if not os.path.exists(PARENT_EVENTS_CSV):
        print(f"  ERROR: not found: {PARENT_EVENTS_CSV}")
        sys.exit(1)
    parent = pd.read_csv(PARENT_EVENTS_CSV)
    parent_q = parent[parent["gap_pct"].abs() <= GAP_QUALITY_CAP].copy()
    parent_q["gap_size_band"]   = _assign_gap_size_band(parent_q)
    parent_q["price_bucket_r4"] = _assign_price_bucket_r4(parent_q)
    print(f"  Parent (quality-filtered): {len(parent_q):,} events")

    # -- Load child events from phase_r3 -----------------------------------

    print(f"\n[2] Loading child events from phase_r3 ...")
    if not os.path.exists(CHILD_EVENTS_CSV):
        print(f"  ERROR: not found: {CHILD_EVENTS_CSV}")
        sys.exit(1)
    children = pd.read_csv(CHILD_EVENTS_CSV)
    print(f"  Combined children loaded: {len(children):,} rows")

    child1_name = "gap_continuation__liquid_trend_names"
    child2_name = "gap_continuation__high_rvol_names"

    child1 = children[children["child_name"] == child1_name].copy()
    child2 = children[children["child_name"] == child2_name].copy()
    print(f"  child1 (liquid_trend_names): {len(child1):,}")
    print(f"  child2 (high_rvol_names):    {len(child2):,}")

    # -- Assign gap size bands and grandchild names -------------------------

    print(f"\n[3] Assigning gap_size_band and grandchild_name columns ...")
    for df in [children, child1, child2]:
        df["gap_size_band"]    = _assign_gap_size_band(df)
        df["price_bucket_r4"]  = _assign_price_bucket_r4(df)

    children["grandchild_name"] = children["child_name"] + "__" + children["gap_size_band"]

    # All events should fall into valid bands (no "other") since phase_r3
    # already applied the 0.5% minimum (= GAP_SMALL_MIN) and 30% quality cap.
    valid_bands = {"small_gap", "medium_gap", "large_gap"}
    n_other = (children["gap_size_band"] == "other").sum()
    if n_other > 0:
        print(f"  WARNING: {n_other:,} events in 'other' band — excluded")
    children_gc = children[children["gap_size_band"].isin(valid_bands)].copy()
    print(f"  Events assigned to valid bands: {len(children_gc):,}")

    # Band distribution
    print(f"\n  Gap size band distribution:")
    for child_name in [child1_name, child2_name]:
        sub = children_gc[children_gc["child_name"] == child_name]
        for band in ["small_gap", "medium_gap", "large_gap"]:
            n = (sub["gap_size_band"] == band).sum()
            pct = n / len(sub) * 100 if len(sub) > 0 else 0
            print(f"    {child_name:<45}  {band:<12}  {n:>8,}  ({pct:.1f}%)")

    # -- Build all summary tables -------------------------------------------

    print(f"\n[4] Building summary tables ...")

    gc_dfs = {gc: children_gc[children_gc["grandchild_name"] == gc] for gc in GC_ORDER}

    summary_df     = _build_grandchild_summary(children_gc)
    comparison_df  = _build_comparison(parent_q, child1, child2, gc_dfs)
    regime_df      = _build_regime_split(children_gc)
    price_bkt_df   = _build_price_bucket_summary(children_gc)
    yearly_df      = _build_yearly_summary(children_gc)

    # -- Console output ------------------------------------------------------

    _print_main_summary(summary_df)
    _print_direction_table(summary_df)
    _print_regime_table(regime_df)

    # Yearly for the two large_gap grandchildren (most likely to show structure)
    print(f"\n{'='*85}")
    print("  YEARLY STABILITY — large_gap grandchildren")
    print(f"{'='*85}")
    _print_yearly(yearly_df, "gap_continuation__liquid_trend_names__large_gap")
    _print_yearly(yearly_df, "gap_continuation__high_rvol_names__large_gap")

    # Yearly for medium_gap as secondary reference
    print(f"\n{'='*85}")
    print("  YEARLY STABILITY — medium_gap grandchildren")
    print(f"{'='*85}")
    _print_yearly(yearly_df, "gap_continuation__liquid_trend_names__medium_gap")
    _print_yearly(yearly_df, "gap_continuation__high_rvol_names__medium_gap")

    # Price bucket breakdown (compact — just n and continuation)
    print(f"\n{'='*85}")
    print("  PRICE BUCKET BREAKDOWN — continuation_rate_pct by grandchild")
    print(f"{'='*85}")
    w = 57
    print(f"  {'grandchild':<{w}}  {'bucket':<12}  {'n':>7}  {'cont%':>6}  {'range%':>7}")
    print(f"  {'-'*w}  {'------------':<12}  {'-------':>7}  {'------':>6}  {'-------':>7}")
    for gc in GC_ORDER:
        sub = price_bkt_df[price_bkt_df["grandchild_name"] == gc]
        for pb in ["5_to_20", "20_to_50", "50_to_100", "100_plus"]:
            r = sub[sub["price_bucket"] == pb]
            if len(r) == 0 or r.iloc[0]["n_events"] == 0:
                continue
            r = r.iloc[0]
            print(
                f"  {gc:<{w}}  {pb:<12}"
                f"  {int(r['n_events']):>7,}"
                f"  {_fmt(r['continuation_rate_pct'], '.1f'):>6}"
                f"  {_fmt(r['mean_nd_range_pct'], '.3f'):>7}"
            )

    # -- Write outputs -------------------------------------------------------

    events_file     = os.path.join(OUTPUT_DIR, f"grandchild_event_rows__gap_continuation__phase_r4__{TODAY}.csv")
    summary_file    = os.path.join(OUTPUT_DIR, f"grandchild_summary__gap_continuation__phase_r4__{TODAY}.csv")
    comparison_file = os.path.join(OUTPUT_DIR, f"grandchild_comparison__gap_continuation__phase_r4__{TODAY}.csv")
    regime_file     = os.path.join(OUTPUT_DIR, f"regime_split_summary__gap_continuation__phase_r4__{TODAY}.csv")
    price_file      = os.path.join(OUTPUT_DIR, f"price_bucket_summary__gap_continuation__phase_r4__{TODAY}.csv")
    yearly_file     = os.path.join(OUTPUT_DIR, f"grandchild_yearly_summary__gap_continuation__phase_r4__{TODAY}.csv")

    children_gc.to_csv(events_file,     index=False)
    summary_df.to_csv(summary_file,     index=False)
    comparison_df.to_csv(comparison_file, index=False)
    regime_df.to_csv(regime_file,       index=False)
    price_bkt_df.to_csv(price_file,     index=False)
    yearly_df.to_csv(yearly_file,       index=False)

    print(f"\n{'='*85}")
    print("OUTPUTS WRITTEN")
    print(f"{'='*85}")
    print(f"  grandchild_event_rows    : {events_file}")
    print(f"                             ({len(children_gc):,} rows)")
    print(f"  grandchild_summary       : {summary_file}")
    print(f"  grandchild_comparison    : {comparison_file}")
    print(f"  regime_split_summary     : {regime_file}")
    print(f"  price_bucket_summary     : {price_file}")
    print(f"  grandchild_yearly_summary: {yearly_file}")

    print(f"\nDone. phase_r4 grandchild gap-size segmentation for gap_continuation complete.")


if __name__ == "__main__":
    main()
