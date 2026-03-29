"""
research_run_gap_continuation_phase_r4_directional_sharpening.py
Side:   research -- strategy family layer
Track:  plan_next_day_day_trade
Family: gap_continuation
Phase:  phase_r4__grandchild_parameter_research (batch_2)

Purpose:
  Directional sharpening pass for the most promising phase_r4 batch_1 grandchildren.

  Batch_1 found:
  - Gap size is a valid range/envelope organizer
  - Gap size alone does NOT create a directional edge (all grandchildren ~47-49% cont)
  - Neutral regime shows modest consistent lift for liquid_trend names (~51-52%)
  - Primary research target: liquid_trend__large_gap + neutral regime

  This batch tests two EOD-observable structural modifiers:

  Modifier 1: close_location
    signal_day_close_location = (close - low) / (high - low)
    Already computed and present in batch_1 event rows.
    Bands:
      cl_low  : cl < CL_LOW_MAX        (close in lower portion of signal day range)
      cl_mid  : CL_LOW_MAX <= cl < CL_HIGH_MIN
      cl_high : cl >= CL_HIGH_MIN      (close in upper portion of signal day range)
    Directional alignment flag:
      For gap_up events:   cl_aligned = (cl >= CL_HIGH_MIN)  -- closed strong before gapping up
                           cl_opposed = (cl < CL_LOW_MAX)    -- closed weak before gapping up
      For gap_down events: cl_aligned = (cl <= CL_LOW_MAX)   -- closed weak before gapping down
                           cl_opposed = (cl >= CL_HIGH_MIN)  -- closed strong before gapping down

  Modifier 2: gap_to_range_ratio
    ratio = abs(gap_pct) / signal_day_range_pct
    Measures how large the gap is relative to the signal day's own price range.
    A ratio near 1.0 means the gap is comparable to the full day's range.
    signal_day_range_pct is already in the batch_1 event rows.
    Bands:
      ratio_minor    : ratio < RATIO_MODERATE_MIN  (gap is small fraction of day range)
      ratio_moderate : RATIO_MODERATE_MIN <= ratio < RATIO_DOMINANT_MIN
      ratio_dominant : ratio >= RATIO_DOMINANT_MIN (gap dominates the day range)

  Combined filter:
    cl_aligned AND ratio_dominant -- both structural signals point the same way

Primary focus:
  liquid_trend__large_gap + neutral regime (6,148 events; 3,004 up / 3,144 down)

Secondary comparison:
  liquid_trend__medium_gap + neutral regime (15,347 events)
  liquid_trend__large_gap + all regimes     (37,040 events)

High_rvol reference:
  high_rvol__large_gap + neutral regime     (4,853 events)
  Kept as structural reference only -- NOT treated as a direction candidate.

Inputs:
  batch_1 grandchild event rows CSV (already has signal_day_close_location,
  signal_day_range_pct, gap_pct, gap_direction, grandchild_name, market_regime_label)

Outputs (research_outputs/.../gap_continuation/phase_r4_structural_validation/):
  batch_2_event_rows__gap_continuation__phase_r4__<DATE>.csv
  batch_2_modifier_summary__gap_continuation__phase_r4__<DATE>.csv
  batch_2_comparison__gap_continuation__phase_r4__<DATE>.csv
  batch_2_yearly__gap_continuation__phase_r4__<DATE>.csv

Usage:
  python research_run_gap_continuation_phase_r4_directional_sharpening.py

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
REPO_ROOT   = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", "..", "..", ".."))

BATCH1_EVENTS_CSV = os.path.join(
    REPO_ROOT,
    "1_0_strategy_research", "research_outputs",
    "family_lineages", "plan_next_day_day_trade",
    "gap_continuation", "phase_r4_structural_validation",
    "grandchild_event_rows__gap_continuation__phase_r4__2026_03_27.csv",
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
# Modifier thresholds  <-- tune here if needed
# ---------------------------------------------------------------------------

# close_location bands (signal_day_close_location = (close - low) / (high - low))
CL_LOW_MAX  = 0.35   # below this = cl_low
CL_HIGH_MIN = 0.65   # at or above this = cl_high
# cl_mid = [0.35, 0.65)

# gap_to_range_ratio bands (abs(gap_pct) / signal_day_range_pct)
RATIO_MODERATE_MIN = 0.25   # below this = ratio_minor
RATIO_DOMINANT_MIN = 0.50   # at or above this = ratio_dominant
# ratio_moderate = [0.25, 0.50)

# ---------------------------------------------------------------------------
# Scope definitions (grandchild + regime combinations to study)
# ---------------------------------------------------------------------------

# Each scope: (label, grandchild_name filter, regime filter or None)
SCOPE_ORDER = [
    ("liquid_trend__large_gap__neutral",     "gap_continuation__liquid_trend_names__large_gap",  "neutral"),
    ("liquid_trend__large_gap__bullish",     "gap_continuation__liquid_trend_names__large_gap",  "bullish"),
    ("liquid_trend__large_gap__bearish",     "gap_continuation__liquid_trend_names__large_gap",  "bearish"),
    ("liquid_trend__large_gap__all_regimes", "gap_continuation__liquid_trend_names__large_gap",  None),
    ("liquid_trend__medium_gap__neutral",    "gap_continuation__liquid_trend_names__medium_gap", "neutral"),
    ("liquid_trend__medium_gap__all_regimes","gap_continuation__liquid_trend_names__medium_gap", None),
    ("high_rvol__large_gap__neutral",        "gap_continuation__high_rvol_names__large_gap",     "neutral"),
    ("high_rvol__large_gap__all_regimes",    "gap_continuation__high_rvol_names__large_gap",     None),
]

# ---------------------------------------------------------------------------
# Column assignment helpers
# ---------------------------------------------------------------------------

def _assign_modifiers(df: pd.DataFrame) -> pd.DataFrame:
    """Add close_location_band, gap_to_range_ratio, ratio_band, and cl_aligned_flag."""
    df = df.copy()

    # -- close_location_band ------------------------------------------------
    cl = df["signal_day_close_location"]
    bands = pd.Series("cl_mid", index=df.index, dtype=str)
    bands[cl < CL_LOW_MAX]  = "cl_low"
    bands[cl >= CL_HIGH_MIN] = "cl_high"
    df["close_location_band"] = bands

    # -- gap_to_range_ratio and ratio_band ----------------------------------
    ratio = df["gap_pct"].abs() / df["signal_day_range_pct"].replace(0, np.nan)
    df["gap_to_range_ratio"] = ratio.round(4)

    rbands = pd.Series("ratio_minor", index=df.index, dtype=str)
    rbands[ratio >= RATIO_MODERATE_MIN]  = "ratio_moderate"
    rbands[ratio >= RATIO_DOMINANT_MIN]  = "ratio_dominant"
    rbands[ratio.isna()]                 = "ratio_unknown"
    df["ratio_band"] = rbands

    # -- cl_aligned_flag ----------------------------------------------------
    # aligned: gap_up with cl_high OR gap_down with cl_low
    # opposed: gap_up with cl_low  OR gap_down with cl_high
    aligned = (
        ((df["gap_direction"] == "up")   & (cl >= CL_HIGH_MIN)) |
        ((df["gap_direction"] == "down") & (cl < CL_LOW_MAX))
    )
    opposed = (
        ((df["gap_direction"] == "up")   & (cl < CL_LOW_MAX)) |
        ((df["gap_direction"] == "down") & (cl >= CL_HIGH_MIN))
    )
    flag = pd.Series("cl_neutral", index=df.index, dtype=str)
    flag[aligned] = "cl_aligned"
    flag[opposed] = "cl_opposed"
    df["cl_aligned_flag"] = flag

    # -- combined_flag: cl_aligned AND ratio_dominant -----------------------
    df["combined_flag"] = (
        (df["cl_aligned_flag"] == "cl_aligned") &
        (df["ratio_band"] == "ratio_dominant")
    )

    return df


# ---------------------------------------------------------------------------
# Metrics helper
# ---------------------------------------------------------------------------

_METRIC_COLS = [
    "continuation_flag",
    "next_day_open_to_close_pct",
    "next_day_open_to_high_pct",
    "next_day_open_to_low_pct",
    "next_day_range_pct",
]


def _metrics(df: pd.DataFrame) -> dict:
    v  = df.dropna(subset=_METRIC_COLS[:2])
    n  = len(df)
    nv = len(v)
    if nv == 0:
        return {
            "n_events": n, "n_with_next_day": 0,
            "continuation_rate_pct":     None,
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
# Summary builder — modifier breakdown table
# ---------------------------------------------------------------------------

def _build_modifier_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each scope (grandchild+regime combo), produce rows sliced by:
      - unmodified baseline (all events in scope)
      - close_location_band x gap_direction
      - cl_aligned_flag x gap_direction
      - ratio_band x gap_direction
      - combined_flag (True/False) x gap_direction
    """
    rows = []

    for scope_label, gc_name, regime in SCOPE_ORDER:
        # Scope filter
        sub = df[df["grandchild_name"] == gc_name]
        if regime is not None:
            sub = sub[sub["market_regime_label"] == regime]
        if len(sub) == 0:
            continue

        def _add(modifier_type: str, modifier_value: str,
                 direction: str, sdf: pd.DataFrame) -> None:
            if len(sdf) == 0:
                return
            row = {
                "scope":          scope_label,
                "modifier_type":  modifier_type,
                "modifier_value": modifier_value,
                "gap_direction":  direction,
            }
            row.update(_metrics(sdf))
            rows.append(row)

        # Directions to iterate
        directions = [("all", sub), ("up", sub[sub["gap_direction"] == "up"]),
                      ("down", sub[sub["gap_direction"] == "down"])]

        # 1. Baseline (no modifier)
        for dir_label, dir_df in directions:
            _add("baseline", "no_modifier", dir_label, dir_df)

        # 2. close_location_band
        for cl_val in ["cl_low", "cl_mid", "cl_high"]:
            for dir_label, dir_df in directions:
                _add("close_location_band", cl_val, dir_label,
                     dir_df[dir_df["close_location_band"] == cl_val])

        # 3. cl_aligned_flag
        for flag_val in ["cl_aligned", "cl_neutral", "cl_opposed"]:
            for dir_label, dir_df in directions:
                _add("cl_aligned_flag", flag_val, dir_label,
                     dir_df[dir_df["cl_aligned_flag"] == flag_val])

        # 4. ratio_band
        for rband in ["ratio_minor", "ratio_moderate", "ratio_dominant"]:
            for dir_label, dir_df in directions:
                _add("ratio_band", rband, dir_label,
                     dir_df[dir_df["ratio_band"] == rband])

        # 5. combined_flag (cl_aligned AND ratio_dominant)
        for flag_bool in [True, False]:
            label = "cl_aligned_AND_ratio_dominant" if flag_bool else "not_combined"
            for dir_label, dir_df in directions:
                _add("combined_filter", label, dir_label,
                     dir_df[dir_df["combined_flag"] == flag_bool])

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Comparison table — key slices side by side
# ---------------------------------------------------------------------------

def _build_comparison(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compact comparison table: one row per key named slice,
    showing the standard metric set. Focus on the most useful combinations.
    """
    rows = []

    def _add(label: str, sdf: pd.DataFrame) -> None:
        if len(sdf) == 0:
            return
        row = {"slice_label": label}
        row.update(_metrics(sdf))
        rows.append(row)

    # -- liquid_trend__large_gap, all regimes (context) --------------------
    lt_lg = df[df["grandchild_name"] == "gap_continuation__liquid_trend_names__large_gap"]
    _add("lt_large_gap__all__no_modifier",           lt_lg)
    _add("lt_large_gap__all__cl_aligned",            lt_lg[lt_lg["cl_aligned_flag"] == "cl_aligned"])
    _add("lt_large_gap__all__cl_opposed",            lt_lg[lt_lg["cl_aligned_flag"] == "cl_opposed"])
    _add("lt_large_gap__all__ratio_dominant",        lt_lg[lt_lg["ratio_band"] == "ratio_dominant"])
    _add("lt_large_gap__all__combined",              lt_lg[lt_lg["combined_flag"]])

    # -- gap_up arm --------------------------------------------------------
    lt_lg_up = lt_lg[lt_lg["gap_direction"] == "up"]
    _add("lt_large_gap__gap_up__no_modifier",        lt_lg_up)
    _add("lt_large_gap__gap_up__cl_high",            lt_lg_up[lt_lg_up["close_location_band"] == "cl_high"])
    _add("lt_large_gap__gap_up__cl_mid",             lt_lg_up[lt_lg_up["close_location_band"] == "cl_mid"])
    _add("lt_large_gap__gap_up__cl_low",             lt_lg_up[lt_lg_up["close_location_band"] == "cl_low"])
    _add("lt_large_gap__gap_up__ratio_dominant",     lt_lg_up[lt_lg_up["ratio_band"] == "ratio_dominant"])
    _add("lt_large_gap__gap_up__combined",           lt_lg_up[lt_lg_up["combined_flag"]])

    # -- gap_down arm ------------------------------------------------------
    lt_lg_dn = lt_lg[lt_lg["gap_direction"] == "down"]
    _add("lt_large_gap__gap_down__no_modifier",      lt_lg_dn)
    _add("lt_large_gap__gap_down__cl_low",           lt_lg_dn[lt_lg_dn["close_location_band"] == "cl_low"])
    _add("lt_large_gap__gap_down__cl_mid",           lt_lg_dn[lt_lg_dn["close_location_band"] == "cl_mid"])
    _add("lt_large_gap__gap_down__cl_high",          lt_lg_dn[lt_lg_dn["close_location_band"] == "cl_high"])
    _add("lt_large_gap__gap_down__ratio_dominant",   lt_lg_dn[lt_lg_dn["ratio_band"] == "ratio_dominant"])
    _add("lt_large_gap__gap_down__combined",         lt_lg_dn[lt_lg_dn["combined_flag"]])

    # -- neutral regime focus ----------------------------------------------
    lt_lg_n = lt_lg[lt_lg["market_regime_label"] == "neutral"]
    _add("lt_large_gap__neutral__no_modifier",       lt_lg_n)
    _add("lt_large_gap__neutral__cl_aligned",        lt_lg_n[lt_lg_n["cl_aligned_flag"] == "cl_aligned"])
    _add("lt_large_gap__neutral__cl_opposed",        lt_lg_n[lt_lg_n["cl_aligned_flag"] == "cl_opposed"])
    _add("lt_large_gap__neutral__ratio_dominant",    lt_lg_n[lt_lg_n["ratio_band"] == "ratio_dominant"])
    _add("lt_large_gap__neutral__combined",          lt_lg_n[lt_lg_n["combined_flag"]])

    lt_lg_n_up = lt_lg_n[lt_lg_n["gap_direction"] == "up"]
    _add("lt_large_gap__neutral_up__no_modifier",    lt_lg_n_up)
    _add("lt_large_gap__neutral_up__cl_high",        lt_lg_n_up[lt_lg_n_up["close_location_band"] == "cl_high"])
    _add("lt_large_gap__neutral_up__combined",       lt_lg_n_up[lt_lg_n_up["combined_flag"]])

    lt_lg_n_dn = lt_lg_n[lt_lg_n["gap_direction"] == "down"]
    _add("lt_large_gap__neutral_down__no_modifier",  lt_lg_n_dn)
    _add("lt_large_gap__neutral_down__cl_low",       lt_lg_n_dn[lt_lg_n_dn["close_location_band"] == "cl_low"])
    _add("lt_large_gap__neutral_down__combined",     lt_lg_n_dn[lt_lg_n_dn["combined_flag"]])

    # -- secondary: liquid_trend__medium_gap + neutral ---------------------
    lt_mg = df[df["grandchild_name"] == "gap_continuation__liquid_trend_names__medium_gap"]
    lt_mg_n = lt_mg[lt_mg["market_regime_label"] == "neutral"]
    _add("lt_medium_gap__neutral__no_modifier",      lt_mg_n)
    _add("lt_medium_gap__neutral__cl_aligned",       lt_mg_n[lt_mg_n["cl_aligned_flag"] == "cl_aligned"])
    _add("lt_medium_gap__neutral__ratio_dominant",   lt_mg_n[lt_mg_n["ratio_band"] == "ratio_dominant"])
    _add("lt_medium_gap__neutral__combined",         lt_mg_n[lt_mg_n["combined_flag"]])

    # -- reference: high_rvol__large_gap + neutral -------------------------
    hr_lg = df[df["grandchild_name"] == "gap_continuation__high_rvol_names__large_gap"]
    hr_lg_n = hr_lg[hr_lg["market_regime_label"] == "neutral"]
    _add("high_rvol__large_gap__neutral__no_modifier", hr_lg_n)
    _add("high_rvol__large_gap__neutral__cl_aligned",  hr_lg_n[hr_lg_n["cl_aligned_flag"] == "cl_aligned"])
    _add("high_rvol__large_gap__neutral__combined",    hr_lg_n[hr_lg_n["combined_flag"]])

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Yearly stability builder — for the most interesting modifier slices
# ---------------------------------------------------------------------------

def _build_yearly(df: pd.DataFrame) -> pd.DataFrame:
    """Yearly breakdown for the primary slices that show best modifier results."""
    df = df.copy()
    df["year"] = df["signal_date"].str[:4].astype(int)

    rows = []

    def _add_yearly(label: str, sdf: pd.DataFrame) -> None:
        sdf = sdf.copy()
        for yr in sorted(sdf["year"].unique()):
            ydf = sdf[sdf["year"] == yr]
            if len(ydf) < 10:
                continue
            row = {"slice_label": label, "year": yr}
            row.update(_metrics(ydf))
            rows.append(row)

    lt_lg = df[df["grandchild_name"] == "gap_continuation__liquid_trend_names__large_gap"]
    lt_lg_n = lt_lg[lt_lg["market_regime_label"] == "neutral"]
    lt_mg_n = df[
        (df["grandchild_name"] == "gap_continuation__liquid_trend_names__medium_gap") &
        (df["market_regime_label"] == "neutral")
    ]

    # Baseline references
    _add_yearly("lt_large_gap__all__no_modifier",       lt_lg)
    _add_yearly("lt_large_gap__neutral__no_modifier",   lt_lg_n)

    # Modifier slices on large_gap
    _add_yearly("lt_large_gap__all__cl_aligned",        lt_lg[lt_lg["cl_aligned_flag"] == "cl_aligned"])
    _add_yearly("lt_large_gap__all__ratio_dominant",    lt_lg[lt_lg["ratio_band"] == "ratio_dominant"])
    _add_yearly("lt_large_gap__all__combined",          lt_lg[lt_lg["combined_flag"]])

    # Same but filtered to neutral
    _add_yearly("lt_large_gap__neutral__cl_aligned",    lt_lg_n[lt_lg_n["cl_aligned_flag"] == "cl_aligned"])
    _add_yearly("lt_large_gap__neutral__ratio_dominant",lt_lg_n[lt_lg_n["ratio_band"] == "ratio_dominant"])
    _add_yearly("lt_large_gap__neutral__combined",      lt_lg_n[lt_lg_n["combined_flag"]])

    # Secondary
    _add_yearly("lt_medium_gap__neutral__no_modifier",  lt_mg_n)
    _add_yearly("lt_medium_gap__neutral__cl_aligned",   lt_mg_n[lt_mg_n["cl_aligned_flag"] == "cl_aligned"])
    _add_yearly("lt_medium_gap__neutral__combined",     lt_mg_n[lt_mg_n["combined_flag"]])

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


def _print_modifier_block(mod_df: pd.DataFrame, scope_label: str) -> None:
    """Print one scope block from the modifier summary."""
    sub = mod_df[mod_df["scope"] == scope_label]
    if len(sub) == 0:
        return

    print(f"\n  --- Scope: {scope_label} ---")
    print(f"  {'modifier':<42}  {'dir':<5}  {'n':>7}  {'cont%':>6}  {'o->c%':>7}  {'range%':>7}")
    print(f"  {'-'*42}  {'-----':<5}  {'-------':>7}  {'------':>6}  {'-------':>7}  {'-------':>7}")

    # Show: baseline, cl_aligned, cl_opposed, ratio_dominant, combined
    priority = {
        ("baseline", "no_modifier"):              0,
        ("cl_aligned_flag", "cl_aligned"):        1,
        ("cl_aligned_flag", "cl_opposed"):        2,
        ("ratio_band", "ratio_dominant"):         3,
        ("combined_filter", "cl_aligned_AND_ratio_dominant"): 4,
    }

    shown_keys = set(priority.keys())

    for dir_label in ["all", "up", "down"]:
        dir_sub = sub[sub["gap_direction"] == dir_label]
        for (mod_type, mod_val), _ in sorted(priority.items(), key=lambda x: x[1]):
            row = dir_sub[(dir_sub["modifier_type"] == mod_type) &
                          (dir_sub["modifier_value"] == mod_val)]
            if len(row) == 0 or row.iloc[0]["n_events"] == 0:
                continue
            r = row.iloc[0]
            tag = f"{mod_type}={mod_val}"[:42]
            print(
                f"  {tag:<42}  {dir_label:<5}"
                f"  {int(r['n_events']):>7,}"
                f"  {_fmt(r['continuation_rate_pct'], '.1f'):>6}"
                f"  {_fmt(r['mean_nd_open_to_close_pct'], '+.3f'):>7}"
                f"  {_fmt(r['mean_nd_range_pct'], '.3f'):>7}"
            )


def _print_close_location_distribution(df: pd.DataFrame) -> None:
    """Show the close_location_band distribution for key grandchildren."""
    print(f"\n{'='*85}")
    print("  CLOSE LOCATION BAND DISTRIBUTION by grandchild")
    print(f"{'='*85}")
    gcs = [
        "gap_continuation__liquid_trend_names__large_gap",
        "gap_continuation__liquid_trend_names__medium_gap",
        "gap_continuation__high_rvol_names__large_gap",
    ]
    for gc in gcs:
        sub = df[df["grandchild_name"] == gc]
        n_total = len(sub)
        if n_total == 0:
            continue
        short = gc.replace("gap_continuation__", "").replace("_names", "")
        for band in ["cl_low", "cl_mid", "cl_high"]:
            n = (sub["close_location_band"] == band).sum()
            pct = n / n_total * 100
            print(f"  {short:<45}  {band:<8}  {n:>7,}  ({pct:.1f}%)")


def _print_ratio_distribution(df: pd.DataFrame) -> None:
    """Show the gap_to_range_ratio_band distribution for key grandchildren."""
    print(f"\n{'='*85}")
    print("  GAP-TO-RANGE RATIO BAND DISTRIBUTION by grandchild")
    print(f"{'='*85}")
    print(f"  ratio = abs(gap_pct) / signal_day_range_pct")
    print(f"  ratio_minor < {RATIO_MODERATE_MIN} | ratio_moderate [{RATIO_MODERATE_MIN},{RATIO_DOMINANT_MIN}) | ratio_dominant >= {RATIO_DOMINANT_MIN}")
    gcs = [
        "gap_continuation__liquid_trend_names__large_gap",
        "gap_continuation__liquid_trend_names__medium_gap",
        "gap_continuation__high_rvol_names__large_gap",
    ]
    for gc in gcs:
        sub = df[df["grandchild_name"] == gc]
        n_total = len(sub)
        if n_total == 0:
            continue
        short = gc.replace("gap_continuation__", "").replace("_names", "")
        for band in ["ratio_minor", "ratio_moderate", "ratio_dominant"]:
            n = (sub["ratio_band"] == band).sum()
            pct = n / n_total * 100
            avg_ratio = sub[sub["ratio_band"] == band]["gap_to_range_ratio"].mean()
            print(f"  {short:<45}  {band:<17}  {n:>7,}  ({pct:.1f}%)  avg_ratio={avg_ratio:.3f}")


def _print_comparison_table(comp_df: pd.DataFrame) -> None:
    """Print the compact comparison table."""
    print(f"\n{'='*85}")
    print("  COMPARISON TABLE — key modifier slices vs baseline")
    print(f"{'='*85}")
    w = 50
    print(f"  {'slice_label':<{w}}  {'n':>7}  {'cont%':>6}  {'o->c%':>7}  {'o->h%':>7}  {'range%':>7}")
    print(f"  {'-'*w}  {'-------':>7}  {'------':>6}  {'-------':>7}  {'-------':>7}  {'-------':>7}")
    for _, r in comp_df.iterrows():
        if r["n_events"] == 0:
            continue
        print(
            f"  {str(r['slice_label']):<{w}}"
            f"  {int(r['n_events']):>7,}"
            f"  {_fmt(r['continuation_rate_pct'], '.1f'):>6}"
            f"  {_fmt(r['mean_nd_open_to_close_pct'], '+.3f'):>7}"
            f"  {_fmt(r['mean_nd_open_to_high_pct'], '+.3f'):>7}"
            f"  {_fmt(r['mean_nd_range_pct'], '.3f'):>7}"
        )


def _print_yearly_table(yearly_df: pd.DataFrame, slice_labels: list) -> None:
    """Print yearly stability for a list of slice labels."""
    for label in slice_labels:
        sub = yearly_df[yearly_df["slice_label"] == label]
        if len(sub) == 0:
            continue
        print(f"\n  Yearly — {label}")
        print(f"  {'year':>4}  {'n':>7}  {'cont%':>6}  {'o->c%':>7}  {'range%':>7}")
        for _, r in sub.sort_values("year").iterrows():
            if r["n_events"] < 10:
                continue
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
    print("research_run_gap_continuation_phase_r4_directional_sharpening")
    print("Track  : plan_next_day_day_trade")
    print("Family : gap_continuation")
    print("Phase  : phase_r4__grandchild_parameter_research (batch_2)")
    print(f"Run date: {TODAY}")
    print("-" * 85)
    print("Modifier thresholds:")
    print(f"  close_location : cl_low < {CL_LOW_MAX} | cl_mid [{CL_LOW_MAX},{CL_HIGH_MIN}) | cl_high >= {CL_HIGH_MIN}")
    print(f"  ratio          : ratio_minor < {RATIO_MODERATE_MIN} | ratio_moderate [{RATIO_MODERATE_MIN},{RATIO_DOMINANT_MIN}) | ratio_dominant >= {RATIO_DOMINANT_MIN}")
    print("Primary focus: liquid_trend__large_gap + neutral regime")
    print("=" * 85)

    # -- Load batch_1 event rows -------------------------------------------
    print(f"\n[1] Loading batch_1 grandchild event rows ...")
    if not os.path.exists(BATCH1_EVENTS_CSV):
        print(f"  ERROR: batch_1 event rows not found: {BATCH1_EVENTS_CSV}")
        sys.exit(1)

    df_all = pd.read_csv(BATCH1_EVENTS_CSV)
    print(f"  Loaded: {len(df_all):,} rows")
    print(f"  Grandchildren present: {df_all['grandchild_name'].unique().tolist()}")

    # Verify required columns exist
    required_cols = [
        "signal_day_close_location", "signal_day_range_pct",
        "gap_pct", "gap_direction", "grandchild_name",
        "market_regime_label", "signal_date",
        "continuation_flag", "next_day_open_to_close_pct",
        "next_day_open_to_high_pct", "next_day_open_to_low_pct",
        "next_day_range_pct",
    ]
    missing = [c for c in required_cols if c not in df_all.columns]
    if missing:
        print(f"  ERROR: missing columns: {missing}")
        sys.exit(1)
    print(f"  Required columns: OK")

    # -- Focus on large_gap + medium_gap grandchildren only ----------------
    focus_gcs = [
        "gap_continuation__liquid_trend_names__large_gap",
        "gap_continuation__liquid_trend_names__medium_gap",
        "gap_continuation__high_rvol_names__large_gap",
    ]
    df = df_all[df_all["grandchild_name"].isin(focus_gcs)].copy()
    print(f"\n  Rows after filtering to focus grandchildren: {len(df):,}")
    for gc in focus_gcs:
        n = (df["grandchild_name"] == gc).sum()
        short = gc.replace("gap_continuation__", "").replace("_names", "")
        print(f"    {short}: {n:,}")

    # -- Assign modifier columns -------------------------------------------
    print(f"\n[2] Computing modifier columns ...")
    df = _assign_modifiers(df)
    print(f"  close_location_band  : {df['close_location_band'].value_counts().to_dict()}")
    print(f"  ratio_band           : {df['ratio_band'].value_counts().to_dict()}")
    print(f"  cl_aligned_flag      : {df['cl_aligned_flag'].value_counts().to_dict()}")
    print(f"  combined_flag (True) : {df['combined_flag'].sum():,}")

    # -- Distribution summaries -------------------------------------------
    _print_close_location_distribution(df)
    _print_ratio_distribution(df)

    # -- Build summary tables -----------------------------------------------
    print(f"\n[3] Building modifier summary ...")
    modifier_df = _build_modifier_summary(df)
    print(f"  Modifier summary rows: {len(modifier_df):,}")

    comparison_df = _build_comparison(df)
    print(f"  Comparison rows: {len(comparison_df):,}")

    yearly_df = _build_yearly(df)
    print(f"  Yearly rows: {len(yearly_df):,}")

    # -- Console output: modifier blocks for priority scopes ---------------
    print(f"\n{'='*85}")
    print("  MODIFIER SUMMARY — key scope + direction combinations")
    print(f"{'='*85}")
    for scope_label, _, _ in SCOPE_ORDER:
        _print_modifier_block(modifier_df, scope_label)

    # -- Comparison table --------------------------------------------------
    _print_comparison_table(comparison_df)

    # -- Yearly stability --------------------------------------------------
    print(f"\n{'='*85}")
    print("  YEARLY STABILITY — modifier slices on liquid_trend__large_gap")
    print(f"{'='*85}")
    yearly_labels_lg = [
        "lt_large_gap__all__no_modifier",
        "lt_large_gap__all__cl_aligned",
        "lt_large_gap__all__ratio_dominant",
        "lt_large_gap__all__combined",
        "lt_large_gap__neutral__no_modifier",
        "lt_large_gap__neutral__cl_aligned",
        "lt_large_gap__neutral__ratio_dominant",
        "lt_large_gap__neutral__combined",
    ]
    _print_yearly_table(yearly_df, yearly_labels_lg)

    print(f"\n{'='*85}")
    print("  YEARLY STABILITY — modifier slices on liquid_trend__medium_gap neutral")
    print(f"{'='*85}")
    yearly_labels_mg = [
        "lt_medium_gap__neutral__no_modifier",
        "lt_medium_gap__neutral__cl_aligned",
        "lt_medium_gap__neutral__combined",
    ]
    _print_yearly_table(yearly_df, yearly_labels_mg)

    # -- Write outputs -----------------------------------------------------
    events_out     = os.path.join(OUTPUT_DIR, f"batch_2_event_rows__gap_continuation__phase_r4__{TODAY}.csv")
    modifier_out   = os.path.join(OUTPUT_DIR, f"batch_2_modifier_summary__gap_continuation__phase_r4__{TODAY}.csv")
    comparison_out = os.path.join(OUTPUT_DIR, f"batch_2_comparison__gap_continuation__phase_r4__{TODAY}.csv")
    yearly_out     = os.path.join(OUTPUT_DIR, f"batch_2_yearly__gap_continuation__phase_r4__{TODAY}.csv")

    df.to_csv(events_out,           index=False)
    modifier_df.to_csv(modifier_out,     index=False)
    comparison_df.to_csv(comparison_out, index=False)
    yearly_df.to_csv(yearly_out,         index=False)

    print(f"\n{'='*85}")
    print("OUTPUTS WRITTEN")
    print(f"{'='*85}")
    print(f"  batch_2_event_rows      : {events_out}")
    print(f"                            ({len(df):,} rows — large_gap + medium_gap grandchildren)")
    print(f"  batch_2_modifier_summary: {modifier_out}")
    print(f"                            ({len(modifier_df):,} rows)")
    print(f"  batch_2_comparison      : {comparison_out}")
    print(f"                            ({len(comparison_df):,} rows)")
    print(f"  batch_2_yearly          : {yearly_out}")
    print(f"                            ({len(yearly_df):,} rows)")

    print(f"\nDone. phase_r4 batch_2 directional sharpening for gap_continuation complete.")


if __name__ == "__main__":
    main()
