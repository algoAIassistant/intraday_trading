"""
research_run_gap_directional_trap_phase_r3_child_isolation.py
Side:   research -- strategy family layer
Track:  plan_next_day_day_trade
Family: gap_directional_trap
Phase:  phase_r3__child_isolation

Purpose:
  Isolate three children inside the gap_directional_trap family and compare
  them against each other and against the phase_r2 parent baseline.

  This phase does NOT define grandchildren, stops, targets, or execution
  templates. It answers which child subtypes show meaningfully better
  structural quality than the broad parent.

  No daily cache enrichment is required: all columns needed for child
  filters (signal_day_close_location, gap_direction, cl_opposed_band,
  gap_size_band, market_regime_label, continuation_flag, next_day_*)
  are already present in the phase_r2 parent event rows CSV.

Children defined in this script:

  child_1: gap_directional_trap__gap_up_cl_low_020
    Thesis: gap_up events where the signal day closed in the bottom 20% of
    its range represent the most extreme trapped-positioning condition.
    The tighter cl threshold should isolate the purest form of the
    family mechanism (exhausted sellers / trapped longs forced to cover
    as the gap confirms upward movement).
    Filter (EOD-observable on signal day):
      1. gap_direction == "up"
      2. signal_day_close_location < 0.20

  child_2: gap_directional_trap__gap_up_cl_low_035
    Thesis: gap_up events where the signal day closed in the bottom 35%
    of its range. Broader comparison child — equivalent to the gap_up
    subset of the parent as defined at phase_r2.
    Filter (EOD-observable on signal day):
      1. gap_direction == "up"
      2. signal_day_close_location < 0.35
    Note: child_1 is a strict subset of child_2.

  child_3: gap_directional_trap__gap_down_cl_high_reference
    Thesis: gap_down events where the signal day closed in the top 35%+
    of its range (cl >= 0.65). Reference path to confirm whether the
    opposing-structure signal also exists for gap_down, or whether this
    direction is structurally flat and should be archived.
    Filter (EOD-observable on signal day):
      1. gap_direction == "down"
      2. signal_day_close_location >= 0.65

Inputs:
  parent event rows from phase_r2 parent baseline (CSV)

Outputs (research_outputs/family_lineages/plan_next_day_day_trade/gap_directional_trap/phase_r3_child_isolation/):
  child_event_rows__gap_directional_trap__phase_r3__<DATE>.csv
    (combined rows for all children, with a 'child_name' column)
  child_summary__gap_directional_trap__phase_r3__<DATE>.csv
    (per-child aggregated metrics: overall, regime, gap_size, regime x gap_size)
  child_vs_parent_comparison__gap_directional_trap__phase_r3__<DATE>.csv
    (side-by-side: parent, child_1, child_2, child_3 on key metrics)
  child_yearly_summary__gap_directional_trap__phase_r3__<DATE>.csv
    (per-year per-child continuation and range metrics)

Usage:
  python research_run_gap_directional_trap_phase_r3_child_isolation.py

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

OUTPUT_DIR = os.path.join(
    REPO_ROOT,
    "1_0_strategy_research", "research_outputs",
    "family_lineages", "plan_next_day_day_trade",
    "gap_directional_trap", "phase_r3_child_isolation",
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

PARENT_EVENTS_CSV = os.path.join(
    REPO_ROOT,
    "1_0_strategy_research", "research_outputs",
    "family_lineages", "plan_next_day_day_trade",
    "gap_directional_trap", "phase_r2_parent_baseline",
    "parent_event_rows__gap_directional_trap__phase_r2__2026_03_27.csv",
)

TODAY = datetime.date.today().strftime("%Y_%m_%d")

# ---------------------------------------------------------------------------
# Child thresholds  <-- tune here
# ---------------------------------------------------------------------------

# Child 1: gap_up, very-opposed (tighter threshold)
CHILD1_CL_MAX   = 0.20    # signal_day_close_location < 0.20

# Child 2: gap_up, moderately-opposed (full parent gap_up definition)
CHILD2_CL_MAX   = 0.35    # signal_day_close_location < 0.35

# Child 3: gap_down reference (full parent gap_down definition)
CHILD3_CL_MIN   = 0.65    # signal_day_close_location >= 0.65

CHILD_NAMES = {
    "child_1": "gap_directional_trap__gap_up_cl_low_020",
    "child_2": "gap_directional_trap__gap_up_cl_low_035",
    "child_3": "gap_directional_trap__gap_down_cl_high_reference",
}


# ---------------------------------------------------------------------------
# Summary builders
# ---------------------------------------------------------------------------

def _metrics(df: pd.DataFrame) -> dict:
    """Compute key next-day metrics for a DataFrame slice."""
    valid = df.dropna(subset=["continuation_flag", "next_day_open_to_close_pct"])
    n  = len(df)
    nv = len(valid)
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
        "n_events":                   n,
        "n_valid":                    nv,
        "continuation_rate_pct":      round(valid["continuation_flag"].mean() * 100, 2),
        "mean_nd_open_to_close_pct":  round(valid["next_day_open_to_close_pct"].mean() * 100, 3),
        "mean_nd_open_to_high_pct":   round(valid["next_day_open_to_high_pct"].mean() * 100, 3),
        "mean_nd_open_to_low_pct":    round(valid["next_day_open_to_low_pct"].mean() * 100, 3),
        "mean_nd_range_pct":          round(valid["next_day_range_pct"].mean() * 100, 3),
    }


def _build_child_summary(child_name: str, df: pd.DataFrame) -> pd.DataFrame:
    """Per-child summary across multiple slice dimensions."""
    rows = []

    # Overall
    row = {"child_name": child_name, "slice_key": "all", "slice_val": "all"}
    row.update(_metrics(df))
    rows.append(row)

    # By regime
    for regime in ["bullish", "neutral", "bearish"]:
        sub = df[df["market_regime_label"] == regime]
        row = {"child_name": child_name, "slice_key": "regime", "slice_val": regime}
        row.update(_metrics(sub))
        rows.append(row)

    # By gap_size_band
    for size in ["small", "medium", "large"]:
        sub = df[df["gap_size_band"] == size]
        row = {"child_name": child_name, "slice_key": "gap_size_band", "slice_val": size}
        row.update(_metrics(sub))
        rows.append(row)

    # Regime x gap_size_band
    for regime in ["bullish", "neutral", "bearish"]:
        for size in ["small", "medium", "large"]:
            sub = df[(df["market_regime_label"] == regime) & (df["gap_size_band"] == size)]
            row = {
                "child_name": child_name,
                "slice_key": "regime_x_gap_size",
                "slice_val": f"{regime}__{size}",
            }
            row.update(_metrics(sub))
            rows.append(row)

    return pd.DataFrame(rows)


def _build_comparison(
    parent: pd.DataFrame,
    child1: pd.DataFrame,
    child2: pd.DataFrame,
    child3: pd.DataFrame,
) -> pd.DataFrame:
    """Side-by-side comparison across parent and children on key slices."""

    slices = [
        ("all",          lambda df: df),
        ("gap_up",       lambda df: df[df["gap_direction"] == "up"]),
        ("gap_down",     lambda df: df[df["gap_direction"] == "down"]),
        ("bullish",      lambda df: df[df["market_regime_label"] == "bullish"]),
        ("neutral",      lambda df: df[df["market_regime_label"] == "neutral"]),
        ("bearish",      lambda df: df[df["market_regime_label"] == "bearish"]),
        ("gap_up_x_bearish",  lambda df: df[(df["gap_direction"]=="up") & (df["market_regime_label"]=="bearish")]),
        ("gap_up_x_neutral",  lambda df: df[(df["gap_direction"]=="up") & (df["market_regime_label"]=="neutral")]),
        ("gap_up_x_bullish",  lambda df: df[(df["gap_direction"]=="up") & (df["market_regime_label"]=="bullish")]),
        ("large_gap",    lambda df: df[df["gap_size_band"] == "large"]),
        ("medium_gap",   lambda df: df[df["gap_size_band"] == "medium"]),
    ]

    metrics = [
        ("n_events",              lambda df: len(df)),
        ("continuation_rate_pct", lambda df: round(
            df.dropna(subset=["continuation_flag"])["continuation_flag"].mean() * 100, 2
        ) if len(df.dropna(subset=["continuation_flag"])) > 0 else None),
        ("mean_nd_open_to_close", lambda df: round(
            df.dropna(subset=["next_day_open_to_close_pct"])["next_day_open_to_close_pct"].mean() * 100, 3
        ) if len(df.dropna(subset=["next_day_open_to_close_pct"])) > 0 else None),
        ("mean_nd_range_pct",     lambda df: round(
            df.dropna(subset=["next_day_range_pct"])["next_day_range_pct"].mean() * 100, 3
        ) if len(df.dropna(subset=["next_day_range_pct"])) > 0 else None),
    ]

    datasets = [
        ("parent_all",                       parent),
        ("child_1__gap_up_cl_low_020",       child1),
        ("child_2__gap_up_cl_low_035",       child2),
        ("child_3__gap_down_cl_high_ref",    child3),
    ]

    rows = []
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


def _build_yearly_summary(children: list[tuple[str, pd.DataFrame]]) -> pd.DataFrame:
    """Year x child continuation and range metrics."""
    rows = []
    for child_name, df in children:
        df = df.copy()
        df["year"] = pd.to_datetime(df["signal_date"]).dt.year
        for yr in sorted(df["year"].unique()):
            sub = df[df["year"] == yr]
            if len(sub) < 10:
                continue
            sub_v = sub.dropna(subset=["continuation_flag", "next_day_open_to_close_pct"])
            rows.append({
                "child_name":                child_name,
                "year":                      yr,
                "n_events":                  len(sub),
                "continuation_rate_pct":     round(sub_v["continuation_flag"].mean() * 100, 2) if len(sub_v) else None,
                "mean_nd_open_to_close_pct": round(sub_v["next_day_open_to_close_pct"].mean() * 100, 3) if len(sub_v) else None,
                "mean_nd_range_pct":         round(sub_v["next_day_range_pct"].mean() * 100, 3) if len(sub_v) else None,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Console formatting
# ---------------------------------------------------------------------------

def _fmt(label: str, df: pd.DataFrame) -> None:
    """Print a single-row metrics summary to console."""
    v = df.dropna(subset=["continuation_flag", "next_day_open_to_close_pct"])
    n   = len(df)
    if len(v) == 0:
        print(f"  {label:<50}  n={n:>7,}  (no valid rows)")
        return
    cont = v["continuation_flag"].mean() * 100
    oc   = v["next_day_open_to_close_pct"].mean() * 100
    oh   = v["next_day_open_to_high_pct"].mean() * 100
    ol   = v["next_day_open_to_low_pct"].mean() * 100
    rng  = v["next_day_range_pct"].mean() * 100
    print(f"  {label:<50}  n={n:>7,}  cont={cont:>5.2f}%  o->c={oc:>+7.3f}%  "
          f"o->h={oh:>+6.3f}%  o->l={ol:>+7.3f}%  range={rng:>5.3f}%")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="phase_r3 child isolation: gap_directional_trap"
    )
    parser.add_argument("--parent-events", default=PARENT_EVENTS_CSV,
                        help="Path to parent event rows CSV from phase_r2")
    parser.add_argument("--child1-cl-max", type=float, default=CHILD1_CL_MAX,
                        metavar="F", help="Child 1 cl_max (gap_up, default 0.20)")
    parser.add_argument("--child2-cl-max", type=float, default=CHILD2_CL_MAX,
                        metavar="F", help="Child 2 cl_max (gap_up, default 0.35)")
    parser.add_argument("--child3-cl-min", type=float, default=CHILD3_CL_MIN,
                        metavar="F", help="Child 3 cl_min (gap_down, default 0.65)")
    args = parser.parse_args()

    print("=" * 75)
    print("research_run_gap_directional_trap_phase_r3_child_isolation")
    print("Track  : plan_next_day_day_trade")
    print("Family : gap_directional_trap")
    print("Phase  : phase_r3__child_isolation")
    print(f"Run date: {TODAY}")
    print("-" * 75)
    print(f"Parent events CSV : {args.parent_events}")
    print(f"Child 1 filter    : gap_up AND cl < {args.child1_cl_max}   "
          f"=> {CHILD_NAMES['child_1']}")
    print(f"Child 2 filter    : gap_up AND cl < {args.child2_cl_max}   "
          f"=> {CHILD_NAMES['child_2']}")
    print(f"Child 3 filter    : gap_down AND cl >= {args.child3_cl_min}  "
          f"=> {CHILD_NAMES['child_3']}")
    print("=" * 75)

    # -- Load parent events ---------------------------------------------------

    if not os.path.exists(args.parent_events):
        print(f"ERROR: parent events file not found:\n  {args.parent_events}")
        sys.exit(1)

    parent = pd.read_csv(args.parent_events)
    print(f"\nParent events loaded: {len(parent):,} rows")
    print(f"Date range: {parent['signal_date'].min()} to {parent['signal_date'].max()}")
    print(f"Unique tickers: {parent['ticker'].nunique():,}")

    cl = parent["signal_day_close_location"]
    gd = parent["gap_direction"]

    # -- Apply child filters --------------------------------------------------

    c1_mask = (gd == "up") & (cl < args.child1_cl_max)
    c2_mask = (gd == "up") & (cl < args.child2_cl_max)
    c3_mask = (gd == "down") & (cl >= args.child3_cl_min)

    child1 = parent[c1_mask].copy()
    child2 = parent[c2_mask].copy()
    child3 = parent[c3_mask].copy()

    child1["child_name"] = CHILD_NAMES["child_1"]
    child2["child_name"] = CHILD_NAMES["child_2"]
    child3["child_name"] = CHILD_NAMES["child_3"]

    print(f"\nChild sample sizes:")
    print(f"  Parent (all cl_opposed events)   : {len(parent):>8,}")
    print(f"  Child 1 (gap_up, cl < {args.child1_cl_max:.2f})       : {len(child1):>8,}  "
          f"({len(child1)/len(parent)*100:.1f}% of parent)")
    print(f"  Child 2 (gap_up, cl < {args.child2_cl_max:.2f})       : {len(child2):>8,}  "
          f"({len(child2)/len(parent)*100:.1f}% of parent)")
    print(f"  Child 3 (gap_down, cl >= {args.child3_cl_min:.2f})     : {len(child3):>8,}  "
          f"({len(child3)/len(parent)*100:.1f}% of parent)")
    print(f"  Child 1 is subset of child 2:     {len(child1)}/{len(child2)} "
          f"({len(child1)/len(child2)*100:.1f}% of child 2)")

    # -- Console report -------------------------------------------------------

    print(f"\n{'='*75}")
    print("KEY METRICS COMPARISON")
    print(f"{'='*75}")
    print(f"\n  {'Label':<50}  {'n':>8}  {'cont':>7}  {'o->c':>8}  "
          f"{'o->h':>7}  {'o->l':>8}  {'range':>6}")

    datasets = [
        ("Parent (all)",                                      parent),
        ("Parent (gap_up only)",                              parent[gd == "up"]),
        ("Parent (gap_down only)",                            parent[gd == "down"]),
        ("Child 1 (gap_up cl<0.20)",                          child1),
        ("Child 2 (gap_up cl<0.35)",                          child2),
        ("Child 3 (gap_down cl>=0.65)",                       child3),
    ]
    print(f"\n  -- Overall --")
    for label, df in datasets:
        _fmt(label, df)

    print(f"\n  -- Child 1 by regime (gap_up cl<0.20) --")
    for regime in ["bullish", "neutral", "bearish"]:
        _fmt(f"  C1 gap_up_cl<0.20  x  {regime}", child1[child1["market_regime_label"] == regime])

    print(f"\n  -- Child 2 by regime (gap_up cl<0.35) --")
    for regime in ["bullish", "neutral", "bearish"]:
        _fmt(f"  C2 gap_up_cl<0.35  x  {regime}", child2[child2["market_regime_label"] == regime])

    print(f"\n  -- Child 3 by regime (gap_down cl>=0.65) --")
    for regime in ["bullish", "neutral", "bearish"]:
        _fmt(f"  C3 gap_down_cl>=0.65  x  {regime}", child3[child3["market_regime_label"] == regime])

    print(f"\n  -- Child 1 by gap_size (gap_up cl<0.20) --")
    for size in ["small", "medium", "large"]:
        _fmt(f"  C1 gap_up_cl<0.20  x  {size}", child1[child1["gap_size_band"] == size])

    print(f"\n  -- Child 1 bearish regime x gap_size --")
    bearish1 = child1[child1["market_regime_label"] == "bearish"]
    for size in ["small", "medium", "large"]:
        _fmt(f"  C1 bearish  x  {size}", bearish1[bearish1["gap_size_band"] == size])

    # -- Yearly stability -----------------------------------------------------

    print(f"\n{'='*75}")
    print("YEARLY STABILITY")
    print(f"{'='*75}")

    for child_name, df in [
        ("Child 1 (gap_up cl<0.20)", child1),
        ("Child 2 (gap_up cl<0.35)", child2),
        ("Child 3 (gap_down cl>=0.65)", child3),
    ]:
        print(f"\n  {child_name}:")
        df_yr = df.copy()
        df_yr["year"] = pd.to_datetime(df_yr["signal_date"]).dt.year
        print(f"  {'year':>6}  {'n':>8}  {'cont%':>7}  {'o->c%':>8}  {'range%':>7}")
        for yr in sorted(df_yr["year"].unique()):
            sub = df_yr[df_yr["year"] == yr]
            v = sub.dropna(subset=["continuation_flag"])
            cont = v["continuation_flag"].mean() * 100 if len(v) else float("nan")
            oc   = sub.dropna(subset=["next_day_open_to_close_pct"])["next_day_open_to_close_pct"].mean() * 100 \
                   if len(sub.dropna(subset=["next_day_open_to_close_pct"])) else float("nan")
            rng  = sub.dropna(subset=["next_day_range_pct"])["next_day_range_pct"].mean() * 100 \
                   if len(sub.dropna(subset=["next_day_range_pct"])) else float("nan")
            print(f"  {yr:>6}  {len(sub):>8,}  {cont:>7.2f}  {oc:>+8.3f}  {rng:>7.3f}")

    # -- Write outputs --------------------------------------------------------

    combined_children = pd.concat([child1, child2, child3], ignore_index=True)

    summary_c1 = _build_child_summary(CHILD_NAMES["child_1"], child1)
    summary_c2 = _build_child_summary(CHILD_NAMES["child_2"], child2)
    summary_c3 = _build_child_summary(CHILD_NAMES["child_3"], child3)
    combined_summary = pd.concat([summary_c1, summary_c2, summary_c3], ignore_index=True)

    comparison_df = _build_comparison(parent, child1, child2, child3)

    yearly_df = _build_yearly_summary([
        (CHILD_NAMES["child_1"], child1),
        (CHILD_NAMES["child_2"], child2),
        (CHILD_NAMES["child_3"], child3),
    ])

    events_file     = os.path.join(OUTPUT_DIR, f"child_event_rows__gap_directional_trap__phase_r3__{TODAY}.csv")
    summary_file    = os.path.join(OUTPUT_DIR, f"child_summary__gap_directional_trap__phase_r3__{TODAY}.csv")
    comparison_file = os.path.join(OUTPUT_DIR, f"child_vs_parent_comparison__gap_directional_trap__phase_r3__{TODAY}.csv")
    yearly_file     = os.path.join(OUTPUT_DIR, f"child_yearly_summary__gap_directional_trap__phase_r3__{TODAY}.csv")

    combined_children.to_csv(events_file,  index=False)
    combined_summary.to_csv(summary_file,  index=False)
    comparison_df.to_csv(comparison_file,  index=False)
    yearly_df.to_csv(yearly_file,          index=False)

    print(f"\n{'='*75}")
    print("OUTPUTS WRITTEN")
    print(f"{'='*75}")
    print(f"  Event rows    : {events_file}")
    print(f"                  ({len(combined_children):,} combined child rows)")
    print(f"  Summary       : {summary_file}")
    print(f"  Comparison    : {comparison_file}")
    print(f"  Yearly        : {yearly_file}")
    print(f"\nDone. phase_r3 child isolation for gap_directional_trap complete.")


if __name__ == "__main__":
    main()
