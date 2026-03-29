"""
research_run_gap_directional_trap_phase_r5_execution_template_research.py
Side:   research -- strategy family layer
Track:  plan_next_day_day_trade
Family: gap_directional_trap
Phase:  phase_r5__execution_template_research

Purpose:
  Test a small, disciplined set of execution templates for the two promoted
  grandchildren from phase_r4:
    PRIMARY:   gap_directional_trap__gap_up_cl_low_020__bearish__medium
    SECONDARY: gap_directional_trap__gap_up_cl_low_020__bearish__medium_plus_large

  Each template specifies: entry formula, stop formula, target (R multiple),
  and a cancel condition modifier.

  Phase_r5 answers the question:
    Can the validated structural slice be translated into a realistic night-before
    conditional-order plan? And if so, which entry/stop/target combination
    produces the strongest and most stable result?

IMPORTANT — DAILY-BAR SIMULATION LIMITATION:
  The repo's intraday_1m cache contains only 3 tickers (AAPL, MSFT, NVDA).
  Full universe intraday data is not available. This phase_r5 simulation uses
  DAILY BAR OHLCV (next_day_open, next_day_high, next_day_low, next_day_close)
  from the phase_r4 event rows. This is a daily-bar proxy for execution testing,
  not an intraday-sequence simulation.

  Conservative assumption: if both stop and target are within the same daily bar
  (next_day_high >= target AND next_day_low <= stop), outcome is treated as a LOSS
  (worst-case sequence assumed). This understates performance relative to intraday
  path reality, which is the correct bias for this phase.

  All templates are TOS-compatible (buy stop conditional orders, fully price-defined
  the night before). No live monitoring required.

Template set (12 combinations):
  Entry:
    E_close_band  : entry = signal_day_close * (1 + ENTRY_CLOSE_BUFFER)
                    buy stop just above prior day's weak close
                    TOS: place buy stop limit at this level night before
    E_prior_high  : entry = signal_day_high
                    buy stop at prior day's high (full range reclaim trigger)
                    TOS: place buy stop at this level night before
                    Note: signal_day_high is the gap-up open level for these stocks;
                    this is an aggressive trigger with a low expected trigger rate

  Stop:
    S_prior_low        : stop = signal_day_low
                         below the structural low of the trap day
    S_prior_low_buffer : stop = signal_day_low * (1 - STOP_LOW_BUFFER)
                         0.5% cushion below signal day low (reduces noise stops)

  Target (R multiple):
    T_1_5r : target = entry + 1.5 * (entry - stop_used)
    T_2_0r : target = entry + 2.0 * (entry - stop_used)
    T_3_0r : target = entry + 3.0 * (entry - stop_used)

  Cancel modifier (tested on all 12 base templates):
    no_cancel        : baseline
    cancel_gap_exceed: skip trade if fill_price > entry * (1 + CANCEL_GAP_EXCEED)
                       handles excessive gap-slippage (e.g. stock opens 2%+ above entry)

Derivation of signal_day_high and signal_day_low:
  signal_day_range_pct is stored as (high - low) / close (decimal fraction).
  signal_day_range_dollar = signal_day_close * signal_day_range_pct
  signal_day_low  = signal_day_close - signal_day_close_location * signal_day_range_dollar
  signal_day_high = signal_day_low + signal_day_range_dollar

  Verification: for a stock with close=9.80, range_pct=0.044, close_location=0.045:
    range_dollar = 9.80 * 0.044 = 0.4312
    low  = 9.80 - 0.045 * 0.4312 = 9.780
    high = 9.780 + 0.4312 = 10.211

Simulation mechanics:
  1. Trigger check:
     triggered = (next_day_open > entry_price) OR (next_day_high >= entry_price)
  2. Fill price (if triggered):
     fill_price = next_day_open  if next_day_open > entry_price (gap fill = slippage risk)
     fill_price = entry_price    otherwise (clean intraday fill at buy stop level)
  3. Risk validation:
     risk = fill_price - stop_price; if risk <= 0, event is invalid (excluded)
  4. Cancel check (if cancel variant):
     cancel if fill_price > entry_price * (1 + CANCEL_GAP_EXCEED)
  5. Target:
     target_price = fill_price + R_target * risk
  6. Outcome (conservative daily-bar rules):
     clean_win   : next_day_high >= target AND next_day_low > stop
     stop_loss   : next_day_low <= stop AND next_day_high < target
     both_hit    : next_day_high >= target AND next_day_low <= stop → treated as LOSS
     time_exit   : neither target nor stop hit; exit at next_day_close
  7. P&L in R:
     clean_win  : +R_target
     stop_loss  : -1.0
     both_hit   : -1.0 (conservative)
     time_exit  : (next_day_close - fill_price) / risk, clipped to [-3.0, R_target * 3]

Input:
  grandchild_event_rows__gap_directional_trap__phase_r4__2026_03_27.csv
  (98,876 rows; child_1 = gap_up AND close_location < 0.20)

Outputs (phase_r5_execution_template_research/):
  template_event_rows__gap_directional_trap__phase_r5__<DATE>.csv
    Primary slice event rows with derived signal_day_high/low and best-template outcome columns
  template_summary__gap_directional_trap__phase_r5__<DATE>.csv
    All 12 templates × 2 slices × 2 cancel variants = 48 rows with full metrics
  template_comparison__gap_directional_trap__phase_r5__<DATE>.csv
    Primary slice best templates head-to-head (12 base templates)
  template_yearly_summary__gap_directional_trap__phase_r5__<DATE>.csv
    Top 4 templates × primary slice × years

Usage:
  python research_run_gap_directional_trap_phase_r5_execution_template_research.py

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

PHASE_R4_EVENTS_CSV = os.path.join(
    REPO_ROOT,
    "1_0_strategy_research", "research_outputs",
    "family_lineages", "plan_next_day_day_trade",
    "gap_directional_trap", "phase_r4_structural_validation",
    "grandchild_event_rows__gap_directional_trap__phase_r4__2026_03_27.csv",
)

OUTPUT_DIR = os.path.join(
    REPO_ROOT,
    "1_0_strategy_research", "research_outputs",
    "family_lineages", "plan_next_day_day_trade",
    "gap_directional_trap", "phase_r5_execution_template_research",
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

TODAY = datetime.date.today().strftime("%Y_%m_%d")

# ---------------------------------------------------------------------------
# Identity constants
# ---------------------------------------------------------------------------

CHILD1_NAME  = "gap_directional_trap__gap_up_cl_low_020"
GC_PRIMARY   = f"{CHILD1_NAME}__bearish__medium"
GC_SECONDARY = f"{CHILD1_NAME}__bearish__medium_plus_large"

# ---------------------------------------------------------------------------
# Template parameters
# ---------------------------------------------------------------------------

ENTRY_CLOSE_BUFFER = 0.002   # 0.2%  — buy stop just above prior close
STOP_LOW_BUFFER    = 0.005   # 0.5%  — below signal day low (buffer stop)
CANCEL_GAP_EXCEED  = 0.02    # 2.0%  — cancel if fill_price > entry * 1.02

R_TARGETS = [1.5, 2.0, 3.0]

# All 12 base templates (entry_id, stop_id, r_target)
TEMPLATES = []
for _entry in ("E_close_band", "E_prior_high"):
    for _stop in ("S_prior_low", "S_prior_low_buffer"):
        for _r in R_TARGETS:
            TEMPLATES.append((_entry, _stop, _r))


def _template_id(entry_id: str, stop_id: str, r_target: float) -> str:
    r_str = str(r_target).replace(".", "_")
    return f"{entry_id}__{stop_id}__T_{r_str}r"


# ---------------------------------------------------------------------------
# Signal day price derivation
# ---------------------------------------------------------------------------

def _derive_signal_prices(df: pd.DataFrame):
    """
    Derive signal_day_low and signal_day_high from available columns.

    signal_day_range_pct = (high - low) / close  (decimal fraction)
    range_dollar = close * range_pct
    low  = close - close_location * range_dollar
    high = low + range_dollar

    Returns (low_series, high_series) as pandas Series aligned to df.index.
    """
    range_dollar = df["signal_day_close"] * df["signal_day_range_pct"]
    low  = df["signal_day_close"] - df["signal_day_close_location"] * range_dollar
    high = low + range_dollar
    return low, high


# ---------------------------------------------------------------------------
# Core simulation
# ---------------------------------------------------------------------------

def _simulate_template(
    df: pd.DataFrame,
    entry_id: str,
    stop_id: str,
    r_target: float,
    use_cancel: bool,
    signal_low: pd.Series,
    signal_high: pd.Series,
) -> pd.DataFrame:
    """
    Simulate one execution template for all rows in df.
    Returns a DataFrame indexed the same as df with outcome columns.
    """
    idx = df.index

    # -- Entry price ----------------------------------------------------------
    if entry_id == "E_close_band":
        entry_price = df["signal_day_close"] * (1.0 + ENTRY_CLOSE_BUFFER)
    else:  # E_prior_high
        entry_price = signal_high.reindex(idx)

    # -- Stop price -----------------------------------------------------------
    if stop_id == "S_prior_low":
        stop_price = signal_low.reindex(idx)
    else:  # S_prior_low_buffer
        stop_price = signal_low.reindex(idx) * (1.0 - STOP_LOW_BUFFER)

    # -- Trigger --------------------------------------------------------------
    gap_fill_trigger   = df["next_day_open"] > entry_price
    intraday_trigger   = df["next_day_high"] >= entry_price
    triggered = gap_fill_trigger | intraday_trigger

    # -- Fill price (if triggered) -------------------------------------------
    fill_price = np.where(gap_fill_trigger, df["next_day_open"], entry_price)
    fill_price = pd.Series(fill_price, index=idx)

    # -- Cancel modifier -----------------------------------------------------
    if use_cancel:
        cancel_mask = triggered & (fill_price > entry_price * (1.0 + CANCEL_GAP_EXCEED))
        triggered = triggered & ~cancel_mask
    else:
        cancel_mask = pd.Series(False, index=idx)

    # -- Risk validation ------------------------------------------------------
    risk = fill_price - stop_price
    valid_setup = triggered & (risk > 0.0)

    # -- Target price --------------------------------------------------------
    target_price = fill_price + r_target * risk

    # -- Outcome (conservative daily-bar rules) ------------------------------
    hit_target = df["next_day_high"] >= target_price
    hit_stop   = df["next_day_low"]  <= stop_price

    outcome = pd.Series("not_triggered", index=idx, dtype=object)
    outcome[triggered & ~valid_setup] = "invalid_risk"

    out_valid = valid_setup
    outcome[out_valid & hit_target & ~hit_stop]  = "clean_win"
    outcome[out_valid & ~hit_target & hit_stop]  = "stop_loss"
    outcome[out_valid & hit_target  &  hit_stop] = "both_hit"    # → treated as loss
    outcome[out_valid & ~hit_target & ~hit_stop] = "time_exit"

    # -- P&L in R ------------------------------------------------------------
    pnl_r = pd.Series(np.nan, index=idx)
    pnl_r[out_valid & (outcome == "clean_win")]  = r_target
    pnl_r[out_valid & (outcome == "stop_loss")]  = -1.0
    pnl_r[out_valid & (outcome == "both_hit")]   = -1.0
    time_exit_mask = out_valid & (outcome == "time_exit")
    pnl_r[time_exit_mask] = (
        (df["next_day_close"] - fill_price) / risk
    )[time_exit_mask].clip(-3.0, r_target * 3.0)

    # -- gap_fill flag -------------------------------------------------------
    gap_fill_used = triggered & gap_fill_trigger

    return pd.DataFrame({
        "entry_price":    entry_price,
        "stop_price":     stop_price,
        "fill_price":     fill_price.where(triggered),
        "target_price":   target_price.where(valid_setup),
        "risk_dollar":    risk.where(valid_setup),
        "triggered":      triggered.astype(int),
        "gap_fill_trigger": gap_fill_used.astype(int),
        "cancelled":      cancel_mask.astype(int),
        "valid_setup":    valid_setup.astype(int),
        "outcome":        outcome,
        "pnl_r":          pnl_r,
    }, index=idx)


# ---------------------------------------------------------------------------
# Metrics aggregator
# ---------------------------------------------------------------------------

def _template_metrics(df: pd.DataFrame, outcomes: pd.DataFrame) -> dict:
    """Aggregate simulation outcomes into summary metrics."""
    n_total = len(df)
    trig     = outcomes["triggered"].astype(bool)
    valid    = outcomes["valid_setup"].astype(bool)
    gap_fill = outcomes["gap_fill_trigger"].astype(bool)
    cancelled = outcomes["cancelled"].astype(bool)

    n_triggered = int(trig.sum())
    n_gap_fill  = int(gap_fill.sum())
    n_cancelled = int(cancelled.sum())
    n_valid     = int(valid.sum())

    oc_valid = outcomes.loc[valid, "outcome"]
    n_win    = int((oc_valid == "clean_win").sum())
    n_loss   = int(((oc_valid == "stop_loss") | (oc_valid == "both_hit")).sum())
    n_both   = int((oc_valid == "both_hit").sum())
    n_time   = int((oc_valid == "time_exit").sum())

    pnl      = outcomes.loc[valid, "pnl_r"].dropna()
    n_pnl    = len(pnl)

    win_rate   = round(n_win  / n_valid * 100, 2) if n_valid else None
    loss_rate  = round(n_loss / n_valid * 100, 2) if n_valid else None
    time_rate  = round(n_time / n_valid * 100, 2) if n_valid else None
    mean_pnl   = round(float(pnl.mean()), 3)   if n_pnl else None
    median_pnl = round(float(pnl.median()), 3) if n_pnl else None

    # Max adverse / favorable excursion proxies (daily bar only)
    if n_valid:
        adv_proxy = (
            (df.loc[valid, "next_day_low"] - outcomes.loc[valid, "fill_price"])
            / outcomes.loc[valid, "risk_dollar"]
        ).dropna()
        fav_proxy = (
            (df.loc[valid, "next_day_high"] - outcomes.loc[valid, "fill_price"])
            / outcomes.loc[valid, "risk_dollar"]
        ).dropna()
        mean_mae_proxy = round(float(adv_proxy.mean()), 3)   if len(adv_proxy) else None
        mean_mfe_proxy = round(float(fav_proxy.mean()), 3)   if len(fav_proxy) else None
        pct_mfe_above_2r = round(float((fav_proxy >= 2.0).mean() * 100), 2) if len(fav_proxy) else None
    else:
        mean_mae_proxy  = None
        mean_mfe_proxy  = None
        pct_mfe_above_2r = None

    return {
        "n_events":               n_total,
        "n_triggered":            n_triggered,
        "trigger_rate_pct":       round(n_triggered / n_total * 100, 2) if n_total else None,
        "n_gap_fill_triggered":   n_gap_fill,
        "gap_fill_rate_pct":      round(n_gap_fill / n_triggered * 100, 2) if n_triggered else None,
        "n_cancelled":            n_cancelled,
        "n_valid_triggered":      n_valid,
        "n_win":                  n_win,
        "n_loss_total":           n_loss,
        "n_both_hit":             n_both,
        "n_time_exit":            n_time,
        "win_rate_pct":           win_rate,
        "loss_rate_pct":          loss_rate,
        "time_exit_rate_pct":     time_rate,
        "mean_pnl_r":             mean_pnl,
        "median_pnl_r":           median_pnl,
        "expectancy_r":           mean_pnl,
        "mean_mae_proxy_r":       mean_mae_proxy,
        "mean_mfe_proxy_r":       mean_mfe_proxy,
        "pct_mfe_above_2r":       pct_mfe_above_2r,
    }


# ---------------------------------------------------------------------------
# Summary builders
# ---------------------------------------------------------------------------

def _build_template_summary(
    primary_df: pd.DataFrame,
    secondary_df: pd.DataFrame,
    signal_low: pd.Series,
    signal_high: pd.Series,
) -> pd.DataFrame:
    """
    Run all 12 templates × 2 cancel variants × 2 slices.
    Returns a summary table with one row per (slice × template × cancel_variant).
    """
    rows = []
    slices = [
        (GC_PRIMARY,   primary_df),
        (GC_SECONDARY, secondary_df),
    ]
    for slice_name, sdf in slices:
        sl_low  = signal_low.reindex(sdf.index)
        sl_high = signal_high.reindex(sdf.index)
        for entry_id, stop_id, r_target in TEMPLATES:
            for use_cancel in (False, True):
                tid = _template_id(entry_id, stop_id, r_target)
                cancel_label = "cancel_gap_exceed" if use_cancel else "no_cancel"
                outcomes = _simulate_template(
                    sdf, entry_id, stop_id, r_target, use_cancel, sl_low, sl_high
                )
                m = _template_metrics(sdf, outcomes)
                row = {
                    "slice":          slice_name,
                    "template_id":    tid,
                    "entry_id":       entry_id,
                    "stop_id":        stop_id,
                    "r_target":       r_target,
                    "cancel_variant": cancel_label,
                }
                row.update(m)
                rows.append(row)
    return pd.DataFrame(rows)


def _build_comparison(
    primary_df: pd.DataFrame,
    signal_low: pd.Series,
    signal_high: pd.Series,
) -> pd.DataFrame:
    """
    Head-to-head comparison: all 12 base templates (no_cancel) on primary slice.
    """
    rows = []
    sl_low  = signal_low.reindex(primary_df.index)
    sl_high = signal_high.reindex(primary_df.index)
    for entry_id, stop_id, r_target in TEMPLATES:
        tid = _template_id(entry_id, stop_id, r_target)
        outcomes = _simulate_template(
            primary_df, entry_id, stop_id, r_target, False, sl_low, sl_high
        )
        m = _template_metrics(primary_df, outcomes)
        row = {
            "template_id": tid,
            "entry_id":    entry_id,
            "stop_id":     stop_id,
            "r_target":    r_target,
        }
        row.update(m)
        rows.append(row)
    return pd.DataFrame(rows)


def _build_yearly_summary(
    primary_df: pd.DataFrame,
    signal_low: pd.Series,
    signal_high: pd.Series,
    top_templates: list,
) -> pd.DataFrame:
    """
    Year × template for a selected set of top templates (primary slice only).
    """
    primary_df = primary_df.copy()
    primary_df["year"] = pd.to_datetime(primary_df["signal_date"]).dt.year
    sl_low  = signal_low.reindex(primary_df.index)
    sl_high = signal_high.reindex(primary_df.index)

    rows = []
    for entry_id, stop_id, r_target in top_templates:
        tid = _template_id(entry_id, stop_id, r_target)
        outcomes = _simulate_template(
            primary_df, entry_id, stop_id, r_target, False, sl_low, sl_high
        )
        for yr in sorted(primary_df["year"].unique()):
            yr_mask = primary_df["year"] == yr
            yr_df   = primary_df[yr_mask]
            yr_out  = outcomes[yr_mask]
            if yr_df.empty:
                continue
            m = _template_metrics(yr_df, yr_out)
            rows.append({
                "template_id":        tid,
                "year":               yr,
                "n_events":           m["n_events"],
                "n_triggered":        m["n_triggered"],
                "trigger_rate_pct":   m["trigger_rate_pct"],
                "n_valid_triggered":  m["n_valid_triggered"],
                "win_rate_pct":       m["win_rate_pct"],
                "mean_pnl_r":         m["mean_pnl_r"],
                "expectancy_r":       m["expectancy_r"],
                "n_win":              m["n_win"],
                "n_loss_total":       m["n_loss_total"],
                "n_time_exit":        m["n_time_exit"],
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Console formatting helpers
# ---------------------------------------------------------------------------

def _fmt_template(label: str, m: dict) -> None:
    n_ev   = m.get("n_events", 0)
    n_tr   = m.get("n_triggered", 0)
    tr_pct = m.get("trigger_rate_pct") or 0.0
    n_val  = m.get("n_valid_triggered", 0)
    wr     = m.get("win_rate_pct") or float("nan")
    ep     = m.get("expectancy_r") or float("nan")
    mn     = m.get("mean_pnl_r") or float("nan")
    med    = m.get("median_pnl_r") or float("nan")
    print(
        f"  {label:<60}  n_ev={n_ev:>6,}  n_trig={n_tr:>5,}  trig={tr_pct:>5.1f}%  "
        f"n_valid={n_val:>5,}  wr={wr:>5.1f}%  E={ep:>+6.3f}R  "
        f"mean={mn:>+6.3f}R  med={med:>+6.3f}R"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="phase_r5 execution template research: gap_directional_trap"
    )
    parser.add_argument(
        "--phase-r4-events", default=PHASE_R4_EVENTS_CSV,
        help="Path to phase_r4 grandchild event rows CSV"
    )
    args = parser.parse_args()

    print("=" * 90)
    print("research_run_gap_directional_trap_phase_r5_execution_template_research")
    print("Track  : plan_next_day_day_trade")
    print("Family : gap_directional_trap")
    print("Phase  : phase_r5__execution_template_research")
    print(f"Run date: {TODAY}")
    print("-" * 90)
    print("SIMULATION BASIS: daily-bar OHLCV (intraday 1m not available for full universe)")
    print("CONSERVATIVE RULE: both stop and target hit same bar => treated as LOSS")
    print("-" * 90)
    print(f"Input : {args.phase_r4_events}")
    print("=" * 90)

    # -- Load phase_r4 grandchild event rows ---------------------------------

    if not os.path.exists(args.phase_r4_events):
        print(f"ERROR: phase_r4 event rows not found:\n  {args.phase_r4_events}")
        sys.exit(1)

    all_events = pd.read_csv(args.phase_r4_events)
    print(f"\nPhase_r4 events loaded : {len(all_events):,} rows")
    print(f"Date range             : {all_events['signal_date'].min()} to {all_events['signal_date'].max()}")
    print(f"Unique tickers         : {all_events['ticker'].nunique():,}")

    # -- Filter slices -------------------------------------------------------

    primary_df   = all_events[all_events["grandchild_name"] == GC_PRIMARY].copy()
    medium_mask  = all_events["gap_size_band"] == "medium"
    large_mask   = all_events["gap_size_band"] == "large"
    bearish_mask = all_events["market_regime_label"] == "bearish"
    secondary_df = all_events[bearish_mask & (medium_mask | large_mask)].copy()

    print(f"\nSlice filter:")
    print(f"  PRIMARY   {GC_PRIMARY:<60}  n={len(primary_df):>6,}")
    print(f"  SECONDARY {GC_SECONDARY:<60}  n={len(secondary_df):>6,}")

    # -- Derive signal_day_high and signal_day_low for all events ------------
    # Use all_events index; reindex per slice inside helpers

    signal_low_all, signal_high_all = _derive_signal_prices(all_events)
    signal_low_all.index  = all_events.index
    signal_high_all.index = all_events.index

    # Spot check derivation on first row
    row0 = all_events.iloc[0]
    rd = row0["signal_day_close"] * row0["signal_day_range_pct"]
    sl = row0["signal_day_close"] - row0["signal_day_close_location"] * rd
    sh = sl + rd
    cl_check = (row0["signal_day_close"] - sl) / rd if rd > 0 else float("nan")
    print(f"\nDerivation spot check (row 0: {row0['ticker']} {row0['signal_date']}):")
    print(f"  signal_day_close    : {row0['signal_day_close']:.4f}")
    print(f"  signal_day_range_pct: {row0['signal_day_range_pct']:.6f}")
    print(f"  signal_day_close_loc: {row0['signal_day_close_location']:.4f}")
    print(f"  derived low         : {sl:.4f}")
    print(f"  derived high        : {sh:.4f}")
    print(f"  cl_check (should match close_loc): {cl_check:.4f}")

    # -- Template overview ---------------------------------------------------

    print(f"\n{'='*90}")
    print("TEMPLATE OVERVIEW")
    print(f"{'='*90}")
    print(f"  12 base templates: 2 entries × 2 stops × 3 R-targets")
    print(f"  Cancel variants  : no_cancel | cancel_gap_exceed (fill > entry × {1+CANCEL_GAP_EXCEED:.2f})")
    print(f"  Primary slice    : {GC_PRIMARY}")
    print(f"  Entry E_close_band  : buy stop at signal_close × {1+ENTRY_CLOSE_BUFFER:.4f}")
    print(f"  Entry E_prior_high  : buy stop at signal_day_high")
    print(f"  Stop S_prior_low    : signal_day_low")
    print(f"  Stop S_prior_low_buf: signal_day_low × {1-STOP_LOW_BUFFER:.4f}")

    # =========================================================================
    # PRIMARY SLICE — ALL 12 TEMPLATES
    # =========================================================================

    print(f"\n{'='*90}")
    print(f"PRIMARY SLICE: {GC_PRIMARY}  (n={len(primary_df):,})")
    print(f"{'='*90}")

    sl_prim  = signal_low_all.reindex(primary_df.index)
    sh_prim  = signal_high_all.reindex(primary_df.index)

    header = (
        f"  {'Template':<60}  {'n_ev':>6}  {'n_trig':>6}  {'trig%':>6}  "
        f"{'n_val':>6}  {'wr%':>6}  {'E_R':>7}  {'mean_R':>7}  {'med_R':>7}"
    )
    print(f"\n  --- E_close_band entries ---")
    print(header)
    for entry_id, stop_id, r_target in TEMPLATES:
        if entry_id != "E_close_band":
            continue
        tid = _template_id(entry_id, stop_id, r_target)
        out = _simulate_template(primary_df, entry_id, stop_id, r_target, False, sl_prim, sh_prim)
        m   = _template_metrics(primary_df, out)
        _fmt_template(tid, m)

    print(f"\n  --- E_prior_high entries ---")
    print(header)
    for entry_id, stop_id, r_target in TEMPLATES:
        if entry_id != "E_prior_high":
            continue
        tid = _template_id(entry_id, stop_id, r_target)
        out = _simulate_template(primary_df, entry_id, stop_id, r_target, False, sl_prim, sh_prim)
        m   = _template_metrics(primary_df, out)
        _fmt_template(tid, m)

    # =========================================================================
    # SECONDARY SLICE
    # =========================================================================

    print(f"\n{'='*90}")
    print(f"SECONDARY SLICE: {GC_SECONDARY}  (n={len(secondary_df):,})")
    print(f"{'='*90}")

    sl_sec  = signal_low_all.reindex(secondary_df.index)
    sh_sec  = signal_high_all.reindex(secondary_df.index)

    print(f"\n  --- E_close_band entries ---")
    print(header)
    for entry_id, stop_id, r_target in TEMPLATES:
        if entry_id != "E_close_band":
            continue
        tid = _template_id(entry_id, stop_id, r_target)
        out = _simulate_template(secondary_df, entry_id, stop_id, r_target, False, sl_sec, sh_sec)
        m   = _template_metrics(secondary_df, out)
        _fmt_template(tid, m)

    # =========================================================================
    # CANCEL MODIFIER — E_close_band primary slice, best stop, all R targets
    # =========================================================================

    print(f"\n{'='*90}")
    print("CANCEL MODIFIER: E_close_band × S_prior_low — primary slice (no_cancel vs cancel_gap_exceed)")
    print(f"{'='*90}")

    print(f"\n  {'Template + cancel':<72}  {'n_ev':>6}  {'n_trig':>6}  {'cancelled':>10}  {'n_val':>6}  {'wr%':>6}  {'E_R':>7}")
    for _, stop_id, r_target in [(e, s, r) for e, s, r in TEMPLATES if e == "E_close_band"]:
        tid = _template_id("E_close_band", stop_id, r_target)
        for use_cancel in (False, True):
            out = _simulate_template(primary_df, "E_close_band", stop_id, r_target, use_cancel, sl_prim, sh_prim)
            m   = _template_metrics(primary_df, out)
            cancel_label = "cancel_gap_exceed" if use_cancel else "no_cancel        "
            print(
                f"  {tid:<55}  {cancel_label:<16}  "
                f"n_ev={m['n_events']:>6,}  n_trig={m['n_triggered']:>5,}  "
                f"cancelled={m['n_cancelled']:>5,}  n_val={m['n_valid_triggered']:>5,}  "
                f"wr={m['win_rate_pct'] or 0.0:>5.1f}%  E={m['expectancy_r'] or 0.0:>+6.3f}R"
            )

    # =========================================================================
    # YEARLY STABILITY — top templates on primary slice
    # =========================================================================

    print(f"\n{'='*90}")
    print("YEARLY STABILITY — PRIMARY SLICE")
    print(f"{'='*90}")

    top_for_yearly = [
        ("E_close_band", "S_prior_low",        1.5),
        ("E_close_band", "S_prior_low",        2.0),
        ("E_close_band", "S_prior_low",        3.0),
        ("E_close_band", "S_prior_low_buffer", 2.0),
    ]

    primary_yr = primary_df.copy()
    primary_yr["year"] = pd.to_datetime(primary_yr["signal_date"]).dt.year

    for entry_id, stop_id, r_target in top_for_yearly:
        tid = _template_id(entry_id, stop_id, r_target)
        outcomes_all = _simulate_template(primary_df, entry_id, stop_id, r_target, False, sl_prim, sh_prim)
        print(f"\n  {tid}:")
        print(f"  {'year':>5}  {'n_ev':>6}  {'n_trig':>6}  {'trig%':>6}  {'n_val':>6}  "
              f"{'wr%':>6}  {'mean_R':>8}  {'n_win':>5}  {'n_loss':>6}  {'n_time':>6}")
        for yr in sorted(primary_yr["year"].unique()):
            yr_mask = primary_yr["year"] == yr
            yr_df   = primary_df[yr_mask]
            yr_out  = outcomes_all[yr_mask]
            m = _template_metrics(yr_df, yr_out)
            wr  = m["win_rate_pct"]  if m["win_rate_pct"]  is not None else float("nan")
            mr  = m["mean_pnl_r"]   if m["mean_pnl_r"]    is not None else float("nan")
            print(
                f"  {yr:>5}  {m['n_events']:>6,}  {m['n_triggered']:>6,}  "
                f"{m['trigger_rate_pct'] or 0.0:>6.1f}  {m['n_valid_triggered']:>6,}  "
                f"{wr:>6.1f}  {mr:>+8.3f}  {m['n_win']:>5}  "
                f"{m['n_loss_total']:>6}  {m['n_time_exit']:>6}"
            )

    # =========================================================================
    # 2022 FOCUS — how bad is 2022 specifically?
    # =========================================================================

    print(f"\n{'='*90}")
    print("2022 FOCUS: primary slice in year 2022 across E_close_band templates")
    print(f"{'='*90}")

    yr2022_mask  = pd.to_datetime(primary_df["signal_date"]).dt.year == 2022
    primary_2022 = primary_df[yr2022_mask]
    sl_2022 = sl_prim[yr2022_mask]
    sh_2022 = sh_prim[yr2022_mask]
    print(f"\n  2022 events in primary slice: {len(primary_2022):,}")

    print(f"\n  {'Template':<60}  {'n_trig':>6}  {'trig%':>6}  {'n_val':>6}  {'wr%':>6}  {'E_R':>7}")
    for entry_id, stop_id, r_target in TEMPLATES:
        if entry_id != "E_close_band":
            continue
        tid = _template_id(entry_id, stop_id, r_target)
        out = _simulate_template(primary_2022, entry_id, stop_id, r_target, False, sl_2022, sh_2022)
        m   = _template_metrics(primary_2022, out)
        print(
            f"  {tid:<60}  {m['n_triggered']:>6,}  "
            f"{m['trigger_rate_pct'] or 0.0:>6.1f}  {m['n_valid_triggered']:>6,}  "
            f"{m['win_rate_pct'] or 0.0:>6.1f}  {m['expectancy_r'] or 0.0:>+7.3f}"
        )

    # =========================================================================
    # WRITE OUTPUTS
    # =========================================================================

    print(f"\n{'='*90}")
    print("WRITING OUTPUT FILES")
    print(f"{'='*90}")

    # 1. Template event rows — primary slice with derived prices + best template outcome
    primary_out = primary_df.copy()
    primary_out["signal_day_low"]  = sl_prim.values
    primary_out["signal_day_high"] = sh_prim.values

    # Best template columns (E_close_band / S_prior_low / 2.0R) for event-level inspection
    best_entry, best_stop, best_r = "E_close_band", "S_prior_low", 2.0
    best_outcomes = _simulate_template(primary_df, best_entry, best_stop, best_r, False, sl_prim, sh_prim)
    tid_best = _template_id(best_entry, best_stop, best_r)
    for col in ["entry_price", "stop_price", "fill_price", "target_price", "risk_dollar",
                "triggered", "gap_fill_trigger", "valid_setup", "outcome", "pnl_r"]:
        primary_out[f"best__{col}"] = best_outcomes[col].values

    events_file = os.path.join(OUTPUT_DIR, f"template_event_rows__gap_directional_trap__phase_r5__{TODAY}.csv")
    primary_out.to_csv(events_file, index=False)
    print(f"  Event rows  : {events_file}")
    print(f"               ({len(primary_out):,} rows; best template annotated: {tid_best})")

    # 2. Full template summary (all slices × templates × cancel variants)
    summary_df = _build_template_summary(primary_df, secondary_df, signal_low_all, signal_high_all)
    summary_file = os.path.join(OUTPUT_DIR, f"template_summary__gap_directional_trap__phase_r5__{TODAY}.csv")
    summary_df.to_csv(summary_file, index=False)
    print(f"  Summary     : {summary_file}")
    print(f"               ({len(summary_df):,} rows)")

    # 3. Comparison table (all 12 base templates × primary slice, no_cancel)
    comparison_df = _build_comparison(primary_df, signal_low_all, signal_high_all)
    comparison_file = os.path.join(OUTPUT_DIR, f"template_comparison__gap_directional_trap__phase_r5__{TODAY}.csv")
    comparison_df.to_csv(comparison_file, index=False)
    print(f"  Comparison  : {comparison_file}")
    print(f"               ({len(comparison_df):,} rows)")

    # 4. Yearly summary (top 4 templates × primary slice)
    yearly_df = _build_yearly_summary(primary_df, signal_low_all, signal_high_all, top_for_yearly)
    yearly_file = os.path.join(OUTPUT_DIR, f"template_yearly_summary__gap_directional_trap__phase_r5__{TODAY}.csv")
    yearly_df.to_csv(yearly_file, index=False)
    print(f"  Yearly      : {yearly_file}")
    print(f"               ({len(yearly_df):,} rows)")

    print(f"\nDone. phase_r5 execution template research for gap_directional_trap complete.")
    print(f"Output directory: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
