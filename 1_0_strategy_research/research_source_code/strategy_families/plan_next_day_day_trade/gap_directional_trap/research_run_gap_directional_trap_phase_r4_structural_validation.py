"""
research_run_gap_directional_trap_phase_r4_structural_validation.py
Side:   research -- strategy family layer
Track:  plan_next_day_day_trade
Family: gap_directional_trap
Phase:  phase_r4__grandchild_parameter_research (structural validation)

Purpose:
  Run phase_r4 structural validation on the sole promoted child from phase_r3:
  gap_directional_trap__gap_up_cl_low_020

  This phase tests the regime x gap_size structural grid inside child_1:
    - market_regime: bullish / neutral / bearish
    - gap_size_band: small (0.5-1.5%) / medium (1.5-3.0%) / large (>=3.0%)
    => 9 grandchild cells + aggregated regime/gap_size slices + combined cells

  The main validation gate is yearly stability.
  The primary research question: do bearish x medium_gap and bearish x large_gap
  survive yearly inspection with adequate sample and structural consistency?

  This phase does NOT define stops, targets, or execution templates.
  It only validates whether structural slices are stable enough to justify
  further formalization at phase_r5.

Grandchildren defined:
  9 primary cells:  gap_directional_trap__gap_up_cl_low_020__{regime}__{gap_size}
  Combined cells:   bearish__medium_plus_large, neutral__medium_plus_large
  Regime-only:      bearish__all, neutral__all, bullish__all
  Gap-size-only:    all__small, all__medium, all__large

Input:
  parent event rows from phase_r2 parent baseline (CSV)
  Apply child_1 filter: gap_direction == "up" AND signal_day_close_location < 0.20

Outputs (research_outputs/family_lineages/plan_next_day_day_trade/gap_directional_trap/phase_r4_structural_validation/):
  grandchild_event_rows__gap_directional_trap__phase_r4__<DATE>.csv
    (child_1 rows with grandchild_name column = regime x gap_size)
  grandchild_summary__gap_directional_trap__phase_r4__<DATE>.csv
    (all grandchild slices with full metrics)
  grandchild_comparison__gap_directional_trap__phase_r4__<DATE>.csv
    (key slices side by side for interpretation)
  grandchild_yearly_summary__gap_directional_trap__phase_r4__<DATE>.csv
    (year x grandchild for primary and secondary cells)
  regime_gap_grid_summary__gap_directional_trap__phase_r4__<DATE>.csv
    (heat-map style regime x gap_size grid)

Usage:
  python research_run_gap_directional_trap_phase_r4_structural_validation.py

Dependencies:
  pip install pandas numpy
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
    "gap_directional_trap", "phase_r4_structural_validation",
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
# Child_1 identity and filter thresholds
# ---------------------------------------------------------------------------

CHILD1_NAME   = "gap_directional_trap__gap_up_cl_low_020"
CHILD1_CL_MAX = 0.20   # signal_day_close_location < 0.20

REGIMES   = ["bullish", "neutral", "bearish"]
GAP_SIZES = ["small", "medium", "large"]


def _gc_name(regime: str, gap_size: str) -> str:
    """Canonical grandchild name for a regime x gap_size cell."""
    return f"{CHILD1_NAME}__{regime}__{gap_size}"


# ---------------------------------------------------------------------------
# Metrics helper
# ---------------------------------------------------------------------------

def _metrics(df: pd.DataFrame) -> dict:
    """Compute key next-day metrics for a DataFrame slice."""
    valid = df.dropna(subset=["continuation_flag", "next_day_open_to_close_pct"])
    n  = len(df)
    nv = len(valid)
    if nv == 0:
        return {
            "n_events": n, "n_valid": 0,
            "continuation_rate_pct":     None,
            "mean_nd_open_to_close_pct": None,
            "mean_nd_open_to_high_pct":  None,
            "mean_nd_open_to_low_pct":   None,
            "mean_nd_range_pct":         None,
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


# ---------------------------------------------------------------------------
# Summary builders
# ---------------------------------------------------------------------------

def _build_grandchild_summary(child1: pd.DataFrame) -> pd.DataFrame:
    """Build a summary table for all grandchild slices inside child_1."""
    rows = []

    # Child_1 overall (baseline reference)
    row = {"grandchild_name": CHILD1_NAME + "__overall", "regime": "all", "gap_size": "all"}
    row.update(_metrics(child1))
    rows.append(row)

    # Regime-only slices
    for regime in REGIMES:
        sub = child1[child1["market_regime_label"] == regime]
        row = {"grandchild_name": f"{CHILD1_NAME}__{regime}__all", "regime": regime, "gap_size": "all"}
        row.update(_metrics(sub))
        rows.append(row)

    # Gap-size-only slices
    for gs in GAP_SIZES:
        sub = child1[child1["gap_size_band"] == gs]
        row = {"grandchild_name": f"{CHILD1_NAME}__all__{gs}", "regime": "all", "gap_size": gs}
        row.update(_metrics(sub))
        rows.append(row)

    # Primary: 9 regime x gap_size cells
    for regime in REGIMES:
        for gs in GAP_SIZES:
            sub = child1[(child1["market_regime_label"] == regime) & (child1["gap_size_band"] == gs)]
            row = {"grandchild_name": _gc_name(regime, gs), "regime": regime, "gap_size": gs}
            row.update(_metrics(sub))
            rows.append(row)

    # Combined key cells
    for regime in ("bearish", "neutral"):
        sub = child1[
            (child1["market_regime_label"] == regime) &
            (child1["gap_size_band"].isin(["medium", "large"]))
        ]
        row = {
            "grandchild_name": f"{CHILD1_NAME}__{regime}__medium_plus_large",
            "regime": regime,
            "gap_size": "medium_plus_large",
        }
        row.update(_metrics(sub))
        rows.append(row)

    return pd.DataFrame(rows)


def _build_regime_gap_grid(child1: pd.DataFrame) -> pd.DataFrame:
    """Build the regime x gap_size heat-map grid table (all 4x4 combinations)."""
    rows = []
    for regime in REGIMES + ["all"]:
        for gs in GAP_SIZES + ["all"]:
            if regime == "all" and gs == "all":
                sub = child1
            elif regime == "all":
                sub = child1[child1["gap_size_band"] == gs]
            elif gs == "all":
                sub = child1[child1["market_regime_label"] == regime]
            else:
                sub = child1[
                    (child1["market_regime_label"] == regime) &
                    (child1["gap_size_band"] == gs)
                ]
            row = {"regime": regime, "gap_size": gs}
            row.update(_metrics(sub))
            rows.append(row)
    return pd.DataFrame(rows)


def _build_comparison(child1: pd.DataFrame) -> pd.DataFrame:
    """Side-by-side comparison of key grandchild slices."""
    slices = [
        (CHILD1_NAME + "__overall",
         child1),
        (f"{CHILD1_NAME}__bearish__all",
         child1[child1["market_regime_label"] == "bearish"]),
        (f"{CHILD1_NAME}__neutral__all",
         child1[child1["market_regime_label"] == "neutral"]),
        (f"{CHILD1_NAME}__bullish__all",
         child1[child1["market_regime_label"] == "bullish"]),
        (f"{CHILD1_NAME}__bearish__large",
         child1[(child1["market_regime_label"] == "bearish") & (child1["gap_size_band"] == "large")]),
        (f"{CHILD1_NAME}__bearish__medium",
         child1[(child1["market_regime_label"] == "bearish") & (child1["gap_size_band"] == "medium")]),
        (f"{CHILD1_NAME}__bearish__small",
         child1[(child1["market_regime_label"] == "bearish") & (child1["gap_size_band"] == "small")]),
        (f"{CHILD1_NAME}__bearish__medium_plus_large",
         child1[(child1["market_regime_label"] == "bearish") & (child1["gap_size_band"].isin(["medium", "large"]))]),
        (f"{CHILD1_NAME}__neutral__large",
         child1[(child1["market_regime_label"] == "neutral") & (child1["gap_size_band"] == "large")]),
        (f"{CHILD1_NAME}__neutral__medium",
         child1[(child1["market_regime_label"] == "neutral") & (child1["gap_size_band"] == "medium")]),
        (f"{CHILD1_NAME}__neutral__medium_plus_large",
         child1[(child1["market_regime_label"] == "neutral") & (child1["gap_size_band"].isin(["medium", "large"]))]),
        (f"{CHILD1_NAME}__bullish__large",
         child1[(child1["market_regime_label"] == "bullish") & (child1["gap_size_band"] == "large")]),
        (f"{CHILD1_NAME}__bullish__medium",
         child1[(child1["market_regime_label"] == "bullish") & (child1["gap_size_band"] == "medium")]),
    ]

    metric_keys = [
        "n_events", "continuation_rate_pct", "mean_nd_open_to_close_pct",
        "mean_nd_open_to_high_pct", "mean_nd_open_to_low_pct", "mean_nd_range_pct",
    ]

    rows = []
    for gc_name, df in slices:
        m = _metrics(df)
        row = {"grandchild_name": gc_name}
        for k in metric_keys:
            row[k] = m.get(k)
        rows.append(row)
    return pd.DataFrame(rows)


def _build_yearly_summary(slices: list) -> pd.DataFrame:
    """Year x grandchild continuation and range metrics for key slices."""
    rows = []
    for gc_name, df in slices:
        df = df.copy()
        df["year"] = pd.to_datetime(df["signal_date"]).dt.year
        for yr in sorted(df["year"].unique()):
            sub = df[df["year"] == yr]
            if len(sub) < 10:
                continue
            sub_v = sub.dropna(subset=["continuation_flag", "next_day_open_to_close_pct"])
            rows.append({
                "grandchild_name":            gc_name,
                "year":                       yr,
                "n_events":                   len(sub),
                "continuation_rate_pct":      round(sub_v["continuation_flag"].mean() * 100, 2) if len(sub_v) else None,
                "mean_nd_open_to_close_pct":  round(sub_v["next_day_open_to_close_pct"].mean() * 100, 3) if len(sub_v) else None,
                "mean_nd_range_pct":          round(sub_v["next_day_range_pct"].mean() * 100, 3) if len(sub_v) else None,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Console formatting
# ---------------------------------------------------------------------------

def _fmt(label: str, df: pd.DataFrame) -> None:
    """Print a single-row metrics summary to console."""
    v = df.dropna(subset=["continuation_flag", "next_day_open_to_close_pct"])
    n = len(df)
    if len(v) == 0:
        print(f"  {label:<62}  n={n:>7,}  (no valid rows)")
        return
    cont = v["continuation_flag"].mean() * 100
    oc   = v["next_day_open_to_close_pct"].mean() * 100
    oh   = v["next_day_open_to_high_pct"].mean() * 100
    ol   = v["next_day_open_to_low_pct"].mean() * 100
    rng  = v["next_day_range_pct"].mean() * 100
    print(f"  {label:<62}  n={n:>7,}  cont={cont:>5.2f}%  o->c={oc:>+7.3f}%  "
          f"o->h={oh:>+6.3f}%  o->l={ol:>+7.3f}%  range={rng:>5.3f}%")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="phase_r4 structural validation: gap_directional_trap__gap_up_cl_low_020"
    )
    parser.add_argument("--parent-events", default=PARENT_EVENTS_CSV,
                        help="Path to parent event rows CSV from phase_r2")
    parser.add_argument("--child1-cl-max", type=float, default=CHILD1_CL_MAX,
                        metavar="F", help="Child_1 cl_max threshold (default 0.20)")
    args = parser.parse_args()

    print("=" * 80)
    print("research_run_gap_directional_trap_phase_r4_structural_validation")
    print("Track  : plan_next_day_day_trade")
    print("Family : gap_directional_trap")
    print("Child  : gap_directional_trap__gap_up_cl_low_020")
    print("Phase  : phase_r4__grandchild_parameter_research (structural validation)")
    print(f"Run date: {TODAY}")
    print("-" * 80)
    print(f"Parent events CSV : {args.parent_events}")
    print(f"Child filter      : gap_up AND signal_day_close_location < {args.child1_cl_max}")
    print(f"Structural grid   : market_regime (bullish/neutral/bearish) x gap_size (small/medium/large)")
    print(f"Primary focus     : bearish x medium_gap  |  bearish x large_gap")
    print(f"Main gate         : yearly stability")
    print("=" * 80)

    # -- Load parent events ---------------------------------------------------

    if not os.path.exists(args.parent_events):
        print(f"ERROR: parent events file not found:\n  {args.parent_events}")
        sys.exit(1)

    parent = pd.read_csv(args.parent_events)
    print(f"\nParent events loaded : {len(parent):,} rows")
    print(f"Date range           : {parent['signal_date'].min()} to {parent['signal_date'].max()}")
    print(f"Unique tickers       : {parent['ticker'].nunique():,}")

    # -- Apply child_1 filter -------------------------------------------------

    c1_mask = (parent["gap_direction"] == "up") & (parent["signal_day_close_location"] < args.child1_cl_max)
    child1 = parent[c1_mask].copy()
    child1["child_name"] = CHILD1_NAME

    print(f"\nChild_1 filter: gap_up AND close_location < {args.child1_cl_max}")
    print(f"  Parent rows  : {len(parent):>8,}")
    print(f"  Child_1 rows : {len(child1):>8,}  ({len(child1)/len(parent)*100:.1f}% of parent)")
    print(f"  Tickers      : {child1['ticker'].nunique():>8,}")

    # Add canonical grandchild_name (regime x gap_size for each row)
    child1["grandchild_name"] = (
        CHILD1_NAME + "__" +
        child1["market_regime_label"] + "__" +
        child1["gap_size_band"]
    )

    # -- Sample-size diagnostics by regime and gap_size -----------------------

    print(f"\n{'='*80}")
    print("SAMPLE SIZE DIAGNOSTICS")
    print(f"{'='*80}")
    print(f"\n  {'Cell':<48}  {'n':>8}  {'pct_of_child1':>14}")
    n_child = len(child1)
    for regime in REGIMES + ["[total]"]:
        if regime == "[total]":
            _sub = child1
            label = "child_1 total"
            print(f"\n  {label:<48}  {n_child:>8,}  {'100.0%':>14}")
            continue
        sub_r = child1[child1["market_regime_label"] == regime]
        print(f"  {regime:<48}  {len(sub_r):>8,}  {len(sub_r)/n_child*100:>13.1f}%")
        for gs in GAP_SIZES:
            sub = sub_r[sub_r["gap_size_band"] == gs]
            label = f"  {regime} x {gs}"
            print(f"  {label:<48}  {len(sub):>8,}  {len(sub)/n_child*100:>13.1f}%")

    # -- Full regime x gap_size grid ------------------------------------------

    print(f"\n{'='*80}")
    print("REGIME x GAP_SIZE GRID — KEY METRICS")
    print(f"{'='*80}")
    print(f"\n  {'Label':<62}  {'n':>8}  {'cont':>7}  {'o->c':>8}  "
          f"{'o->h':>7}  {'o->l':>8}  {'range':>6}")
    print()

    _fmt("child_1 overall [baseline]", child1)
    print()

    for regime in REGIMES:
        sub_r = child1[child1["market_regime_label"] == regime]
        _fmt(f"  {regime} (all gap sizes)", sub_r)
        for gs in GAP_SIZES:
            sub = sub_r[sub_r["gap_size_band"] == gs]
            _fmt(f"    {regime} x {gs}", sub)
        if regime in ("bearish", "neutral"):
            sub_ml = sub_r[sub_r["gap_size_band"].isin(["medium", "large"])]
            _fmt(f"    {regime} x medium+large [combined]", sub_ml)
        print()

    # -- Yearly stability for primary cells -----------------------------------

    print(f"\n{'='*80}")
    print("YEARLY STABILITY — PRIMARY AND KEY SECONDARY CELLS")
    print(f"{'='*80}")

    yearly_slices = [
        (CHILD1_NAME + "__overall",
         child1),
        (_gc_name("bearish", "large"),
         child1[(child1["market_regime_label"] == "bearish") & (child1["gap_size_band"] == "large")]),
        (_gc_name("bearish", "medium"),
         child1[(child1["market_regime_label"] == "bearish") & (child1["gap_size_band"] == "medium")]),
        (f"{CHILD1_NAME}__bearish__medium_plus_large",
         child1[(child1["market_regime_label"] == "bearish") & (child1["gap_size_band"].isin(["medium", "large"]))]),
        (_gc_name("bearish", "small"),
         child1[(child1["market_regime_label"] == "bearish") & (child1["gap_size_band"] == "small")]),
        (_gc_name("neutral", "medium"),
         child1[(child1["market_regime_label"] == "neutral") & (child1["gap_size_band"] == "medium")]),
        (_gc_name("neutral", "large"),
         child1[(child1["market_regime_label"] == "neutral") & (child1["gap_size_band"] == "large")]),
        (f"{CHILD1_NAME}__neutral__medium_plus_large",
         child1[(child1["market_regime_label"] == "neutral") & (child1["gap_size_band"].isin(["medium", "large"]))]),
    ]

    for gc_name, df in yearly_slices:
        print(f"\n  {gc_name}:")
        df_yr = df.copy()
        df_yr["year"] = pd.to_datetime(df_yr["signal_date"]).dt.year
        print(f"  {'year':>6}  {'n':>6}  {'cont%':>7}  {'o->c%':>8}  {'range%':>7}")
        for yr in sorted(df_yr["year"].unique()):
            sub = df_yr[df_yr["year"] == yr]
            sub_v = sub.dropna(subset=["continuation_flag"])
            cont = sub_v["continuation_flag"].mean() * 100 if len(sub_v) else float("nan")
            sub_oc = sub.dropna(subset=["next_day_open_to_close_pct"])
            oc   = sub_oc["next_day_open_to_close_pct"].mean() * 100 if len(sub_oc) else float("nan")
            sub_rng = sub.dropna(subset=["next_day_range_pct"])
            rng  = sub_rng["next_day_range_pct"].mean() * 100 if len(sub_rng) else float("nan")
            print(f"  {yr:>6}  {len(sub):>6,}  {cont:>7.2f}  {oc:>+8.3f}  {rng:>7.3f}")

    # -- Write outputs --------------------------------------------------------

    summary_df    = _build_grandchild_summary(child1)
    grid_df       = _build_regime_gap_grid(child1)
    comparison_df = _build_comparison(child1)
    yearly_df     = _build_yearly_summary(yearly_slices)

    events_file     = os.path.join(OUTPUT_DIR, f"grandchild_event_rows__gap_directional_trap__phase_r4__{TODAY}.csv")
    summary_file    = os.path.join(OUTPUT_DIR, f"grandchild_summary__gap_directional_trap__phase_r4__{TODAY}.csv")
    comparison_file = os.path.join(OUTPUT_DIR, f"grandchild_comparison__gap_directional_trap__phase_r4__{TODAY}.csv")
    yearly_file     = os.path.join(OUTPUT_DIR, f"grandchild_yearly_summary__gap_directional_trap__phase_r4__{TODAY}.csv")
    grid_file       = os.path.join(OUTPUT_DIR, f"regime_gap_grid_summary__gap_directional_trap__phase_r4__{TODAY}.csv")

    child1.to_csv(events_file,        index=False)
    summary_df.to_csv(summary_file,   index=False)
    comparison_df.to_csv(comparison_file, index=False)
    yearly_df.to_csv(yearly_file,     index=False)
    grid_df.to_csv(grid_file,         index=False)

    print(f"\n{'='*80}")
    print("OUTPUTS WRITTEN")
    print(f"{'='*80}")
    print(f"  Event rows  : {events_file}")
    print(f"               ({len(child1):,} rows)")
    print(f"  Summary     : {summary_file}")
    print(f"  Comparison  : {comparison_file}")
    print(f"  Yearly      : {yearly_file}")
    print(f"  Grid        : {grid_file}")
    print(f"\nDone. phase_r4 structural validation for gap_directional_trap__gap_up_cl_low_020 complete.")


if __name__ == "__main__":
    main()
