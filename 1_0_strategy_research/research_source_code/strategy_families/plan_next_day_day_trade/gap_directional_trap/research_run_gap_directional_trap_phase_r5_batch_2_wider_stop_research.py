"""
research_run_gap_directional_trap_phase_r5_batch_2_wider_stop_research.py
Side:   research -- strategy family layer
Track:  plan_next_day_day_trade
Family: gap_directional_trap
Phase:  phase_r5__execution_template_research  (batch_2)

Purpose:
  Batch_1 finding: the directional signal is real (51.5% MFE>2R, mean MFE +3.54R)
  but the stop at signal_day_low is too tight (~0.7% of price) for this family.
  Mean adverse excursion = -3.02R (structural stop) / -1.64R (buffered stop).
  The stock routinely dips into the stop before the directional move develops.

  Batch_2 tests whether wider stops rescue expectancy.
  Entry logic is unchanged: E_close_band is confirmed as the only viable entry.
  E_prior_high is not retested (closed in batch_1).

  Stop logic tested:
    S_fixed_1_5pct      : stop = fill * (1 - 0.015)  -- narrow control; 2x batch_1
    S_fixed_2_0pct      : stop = fill * (1 - 0.020)  -- primary test: ~3x batch_1
    S_fixed_2_5pct      : stop = fill * (1 - 0.025)
    S_fixed_3_0pct      : stop = fill * (1 - 0.030)  -- widest fixed
    S_range_proxy_75pct : stop = fill - 0.75 * signal_day_range_dollar
                          (ATR proxy; risk proportional to prior-day volatility)

  Target logic tested:
    T_fixed_1_5r   : target = fill + 1.5 * risk
    T_fixed_2_0r   : target = fill + 2.0 * risk
    T_fixed_3_0r   : target = fill + 3.0 * risk
    T_range_50pct  : target = fill + 0.50 * signal_day_range_dollar
    T_range_75pct  : target = fill + 0.75 * signal_day_range_dollar

  Cancel logic tested:
    Fixed-% stops  : no cancel (risk is pre-defined; no cancel needed)
    Range-proxy    : no cancel (baseline) AND cancel_if_risk_gt_5pct
                     (skip event if 0.75 * range_dollar / fill > 0.05,
                      i.e., signal_day_range_pct > ~6.67%)

  Total templates: 17 (11 fixed-pct, 4 range-proxy, 2 range-proxy-cancel)

SIMULATION BASIS (same as batch_1):
  Daily-bar OHLCV only -- intraday 1m not available for full universe.
  Conservative rule: both stop and target hit same daily bar => treated as LOSS.
  All templates remain TOS-compatible (buy stop conditional orders, price-defined
  the night before; no live monitoring required).

KEY DIFFERENCE FROM BATCH_1 — STOP MECHANICS:
  In batch_1, stops used the signal_day_low (a structural level).
  In batch_2, fixed-% stops use the FILL PRICE as the anchor:
    stop_price = fill_price * (1 - stop_pct)
  This means:
  - For gap-fill events (fill = next_day_open), stop tracks the actual fill
  - Risk_dollar = fill_price * stop_pct (always positive; no invalid_risk events
    for fixed-% stops unless fill_price = 0, which cannot occur in practice)
  For TOS: the bracket stop would be set at entry_price * (1 - stop_pct) using the
  plan entry price (a slight approximation if the stock gaps above entry).

  For range-proxy stop:
    stop_price = fill_price - 0.75 * signal_day_range_dollar
    Risk varies per event. Cancel condition removes events with risk > 5% of fill.

RANGE-PROXY TARGET P&L:
  For T_range_50pct / T_range_75pct, the win P&L is reported in implied_R units:
    implied_R = (target_price - fill_price) / risk_dollar
  This varies per event. Mean implied_R for winners is reported in metrics.

Derivation of signal_day_range_dollar:
  signal_day_range_pct = (high - low) / close  (decimal fraction; stored in cache)
  range_dollar = signal_day_close * signal_day_range_pct
  signal_day_low  = signal_day_close - close_location * range_dollar
  signal_day_high = signal_day_low + range_dollar

Input:
  grandchild_event_rows__gap_directional_trap__phase_r4__2026_03_27.csv

Slices:
  PRIMARY   : gap_directional_trap__gap_up_cl_low_020__bearish__medium   (n=6,320)
  SECONDARY : gap_directional_trap__gap_up_cl_low_020__bearish__medium_plus_large (n=9,865)

Outputs (phase_r5_execution_template_research/):
  batch_2_template_event_rows__gap_directional_trap__phase_r5__<DATE>.csv
    Primary slice event rows with derived signal prices and plan stop prices
  batch_2_template_summary__gap_directional_trap__phase_r5__<DATE>.csv
    All 17 templates x 2 slices = 34 rows with full metrics
  batch_2_template_comparison__gap_directional_trap__phase_r5__<DATE>.csv
    All 17 templates on primary slice (head-to-head)
  batch_2_yearly_template_summary__gap_directional_trap__phase_r5__<DATE>.csv
    Top templates x primary slice x years (6 years)

Usage:
  python research_run_gap_directional_trap_phase_r5_batch_2_wider_stop_research.py

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

ENTRY_CLOSE_BUFFER = 0.002   # 0.2% — buy stop just above prior close (same as batch_1)
CANCEL_RISK_PCT    = 0.05    # 5.0% — cancel if risk > 5% of fill (range-proxy stop only)

# Template list: (entry_id, stop_id, target_id, use_risk_cancel)
TEMPLATES_B2 = [
    # -----------------------------------------------------------------------
    # Fixed-% stops (risk is pre-defined; no cancel needed)
    # -----------------------------------------------------------------------
    # S_fixed_1_5pct: narrow control — just above batch_1 S_prior_low_buffer (~0.7%)
    ("E_close_band", "S_fixed_1_5pct",      "T_fixed_2_0r",  False),
    ("E_close_band", "S_fixed_1_5pct",      "T_fixed_3_0r",  False),
    # S_fixed_2_0pct: primary batch_2 test — ~3x batch_1 structural stop width
    # also tests range-proxy targets with this stop
    ("E_close_band", "S_fixed_2_0pct",      "T_fixed_1_5r",  False),
    ("E_close_band", "S_fixed_2_0pct",      "T_fixed_2_0r",  False),
    ("E_close_band", "S_fixed_2_0pct",      "T_fixed_3_0r",  False),
    ("E_close_band", "S_fixed_2_0pct",      "T_range_50pct", False),
    ("E_close_band", "S_fixed_2_0pct",      "T_range_75pct", False),
    # S_fixed_2_5pct
    ("E_close_band", "S_fixed_2_5pct",      "T_fixed_2_0r",  False),
    ("E_close_band", "S_fixed_2_5pct",      "T_fixed_3_0r",  False),
    # S_fixed_3_0pct: widest fixed stop; high per-loss cost offset by low stop-out rate
    ("E_close_band", "S_fixed_3_0pct",      "T_fixed_2_0r",  False),
    ("E_close_band", "S_fixed_3_0pct",      "T_fixed_3_0r",  False),
    # -----------------------------------------------------------------------
    # Range-proxy stop: 75% of prior-day range below fill (ATR proxy)
    # Risk proportional to signal-day volatility
    # -----------------------------------------------------------------------
    ("E_close_band", "S_range_proxy_75pct", "T_fixed_2_0r",  False),
    ("E_close_band", "S_range_proxy_75pct", "T_fixed_3_0r",  False),
    ("E_close_band", "S_range_proxy_75pct", "T_range_50pct", False),
    ("E_close_band", "S_range_proxy_75pct", "T_range_75pct", False),
    # Range-proxy stop with cancel: skip events where risk > 5% of fill price
    # (filters out extreme high-range events; range_pct > ~6.67%)
    ("E_close_band", "S_range_proxy_75pct", "T_fixed_2_0r",  True),
    ("E_close_band", "S_range_proxy_75pct", "T_fixed_3_0r",  True),
]


def _template_id(entry_id: str, stop_id: str, target_id: str, use_risk_cancel: bool) -> str:
    cancel_suffix = "__cancel_risk_gt_5pct" if use_risk_cancel else ""
    return f"{entry_id}__{stop_id}__{target_id}{cancel_suffix}"


# ---------------------------------------------------------------------------
# Signal day price derivation
# ---------------------------------------------------------------------------

def _derive_signal_prices(df: pd.DataFrame):
    """
    Derive signal_day_low, signal_day_high, and range_dollar from available columns.

    signal_day_range_pct = (high - low) / close  (decimal fraction)
    range_dollar = close * range_pct
    low  = close - close_location * range_dollar
    high = low + range_dollar

    Returns (signal_low, signal_high, range_dollar) as Series indexed by df.index.
    """
    range_dollar = df["signal_day_close"] * df["signal_day_range_pct"]
    low  = df["signal_day_close"] - df["signal_day_close_location"] * range_dollar
    high = low + range_dollar
    return low, high, range_dollar


# ---------------------------------------------------------------------------
# Core simulation
# ---------------------------------------------------------------------------

def _simulate_template(
    df: pd.DataFrame,
    entry_id: str,
    stop_id: str,
    target_id: str,
    use_risk_cancel: bool,
    range_dollar: pd.Series,
) -> pd.DataFrame:
    """
    Simulate one execution template for all rows in df.

    Entry:
      E_close_band: buy stop at signal_day_close * (1 + ENTRY_CLOSE_BUFFER)

    Stop (anchored to fill_price for fixed-pct; to range_dollar for range-proxy):
      S_fixed_1_5pct      : fill * (1 - 0.015)
      S_fixed_2_0pct      : fill * (1 - 0.020)
      S_fixed_2_5pct      : fill * (1 - 0.025)
      S_fixed_3_0pct      : fill * (1 - 0.030)
      S_range_proxy_75pct : fill - 0.75 * range_dollar

    Cancel (range-proxy only):
      use_risk_cancel=True: skip event if risk / fill > CANCEL_RISK_PCT

    Target:
      T_fixed_1_5r  : fill + 1.5 * risk
      T_fixed_2_0r  : fill + 2.0 * risk
      T_fixed_3_0r  : fill + 3.0 * risk
      T_range_50pct : fill + 0.50 * range_dollar
      T_range_75pct : fill + 0.75 * range_dollar

    Outcome (conservative daily-bar):
      clean_win  : high >= target AND low > stop
      stop_loss  : low <= stop AND high < target
      both_hit   : high >= target AND low <= stop  --> treated as LOSS
      time_exit  : neither hit; exit at next_day_close

    P&L in R (relative to risk_dollar for this template):
      clean_win  : +R_target (fixed) or implied_R (range-proxy targets, varies per row)
      stop_loss  : -1.0
      both_hit   : -1.0 (conservative)
      time_exit  : (close - fill) / risk, clipped [-3.0, 10.0]

    Returns DataFrame indexed same as df.
    """
    idx = df.index
    rd  = range_dollar.reindex(idx)

    # -- Entry price ----------------------------------------------------------
    entry_price = df["signal_day_close"] * (1.0 + ENTRY_CLOSE_BUFFER)

    # -- Trigger --------------------------------------------------------------
    gap_fill_trigger = df["next_day_open"] > entry_price
    intraday_trigger = df["next_day_high"] >= entry_price
    triggered = gap_fill_trigger | intraday_trigger

    # -- Fill price -----------------------------------------------------------
    fill_price = pd.Series(
        np.where(gap_fill_trigger.values, df["next_day_open"].values, entry_price.values),
        index=idx,
    )

    # -- Stop price -----------------------------------------------------------
    if stop_id == "S_fixed_1_5pct":
        stop_price = fill_price * (1.0 - 0.015)
    elif stop_id == "S_fixed_2_0pct":
        stop_price = fill_price * (1.0 - 0.020)
    elif stop_id == "S_fixed_2_5pct":
        stop_price = fill_price * (1.0 - 0.025)
    elif stop_id == "S_fixed_3_0pct":
        stop_price = fill_price * (1.0 - 0.030)
    elif stop_id == "S_range_proxy_75pct":
        stop_price = fill_price - 0.75 * rd
    else:
        raise ValueError(f"Unknown stop_id: {stop_id}")

    # -- Risk validation ------------------------------------------------------
    risk = fill_price - stop_price
    valid_setup = triggered & (risk > 0.0)

    # -- Risk cancel (range-proxy stop only) ----------------------------------
    cancel_mask = pd.Series(False, index=idx)
    if use_risk_cancel:
        risk_pct_series = risk / fill_price.replace(0.0, np.nan)
        cancel_mask = triggered & valid_setup & (risk_pct_series > CANCEL_RISK_PCT)
        triggered   = triggered   & ~cancel_mask
        valid_setup = valid_setup & ~cancel_mask

    # -- Target price ---------------------------------------------------------
    if target_id == "T_fixed_1_5r":
        target_price = fill_price + 1.5 * risk
    elif target_id == "T_fixed_2_0r":
        target_price = fill_price + 2.0 * risk
    elif target_id == "T_fixed_3_0r":
        target_price = fill_price + 3.0 * risk
    elif target_id == "T_range_50pct":
        target_price = fill_price + 0.50 * rd
    elif target_id == "T_range_75pct":
        target_price = fill_price + 0.75 * rd
    else:
        raise ValueError(f"Unknown target_id: {target_id}")

    # -- Outcome (conservative daily-bar rules) -------------------------------
    hit_target = df["next_day_high"] >= target_price
    hit_stop   = df["next_day_low"]  <= stop_price

    outcome = pd.Series("not_triggered", index=idx, dtype=object)
    outcome[triggered & ~valid_setup] = "invalid_risk"
    out_valid = valid_setup
    outcome[out_valid & hit_target & ~hit_stop] = "clean_win"
    outcome[out_valid & ~hit_target & hit_stop] = "stop_loss"
    outcome[out_valid & hit_target  & hit_stop] = "both_hit"   # -> treated as LOSS
    outcome[out_valid & ~hit_target & ~hit_stop] = "time_exit"

    # -- P&L in R (risk-normalized) ------------------------------------------
    pnl_r = pd.Series(np.nan, index=idx)

    win_mask  = out_valid & (outcome == "clean_win")
    loss_mask = out_valid & ((outcome == "stop_loss") | (outcome == "both_hit"))
    time_mask = out_valid & (outcome == "time_exit")

    # Win P&L
    if target_id in ("T_fixed_1_5r", "T_fixed_2_0r", "T_fixed_3_0r"):
        r_val = {"T_fixed_1_5r": 1.5, "T_fixed_2_0r": 2.0, "T_fixed_3_0r": 3.0}[target_id]
        pnl_r[win_mask] = r_val
    else:
        # Range-proxy target: implied R = (target - fill) / risk; varies per row
        safe_risk  = risk.replace(0.0, np.nan)
        implied_r  = ((target_price - fill_price) / safe_risk).clip(0.1, 20.0)
        pnl_r[win_mask] = implied_r[win_mask]

    # Loss P&L
    pnl_r[loss_mask] = -1.0

    # Time-exit P&L
    safe_risk = risk.replace(0.0, np.nan)
    pnl_r[time_mask] = (
        (df["next_day_close"] - fill_price) / safe_risk
    )[time_mask].clip(-3.0, 10.0)

    gap_fill_used = triggered & gap_fill_trigger

    return pd.DataFrame({
        "entry_price":      entry_price,
        "stop_price":       stop_price,
        "fill_price":       fill_price.where(triggered),
        "target_price":     target_price.where(valid_setup),
        "risk_dollar":      risk.where(valid_setup),
        "triggered":        triggered.astype(int),
        "gap_fill_trigger": gap_fill_used.astype(int),
        "cancelled":        cancel_mask.astype(int),
        "valid_setup":      valid_setup.astype(int),
        "outcome":          outcome,
        "pnl_r":            pnl_r,
    }, index=idx)


# ---------------------------------------------------------------------------
# Metrics aggregator
# ---------------------------------------------------------------------------

def _template_metrics(df: pd.DataFrame, outcomes: pd.DataFrame) -> dict:
    """Aggregate simulation outcomes into summary metrics."""
    n_total   = len(df)
    trig      = outcomes["triggered"].astype(bool)
    valid     = outcomes["valid_setup"].astype(bool)
    gap_fill  = outcomes["gap_fill_trigger"].astype(bool)
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

    pnl   = outcomes.loc[valid, "pnl_r"].dropna()
    n_pnl = len(pnl)

    win_rate   = round(n_win  / n_valid * 100, 2) if n_valid else None
    loss_rate  = round(n_loss / n_valid * 100, 2) if n_valid else None
    time_rate  = round(n_time / n_valid * 100, 2) if n_valid else None
    mean_pnl   = round(float(pnl.mean()),   3) if n_pnl else None
    median_pnl = round(float(pnl.median()), 3) if n_pnl else None

    # MAE/MFE proxies in R (relative to this template's actual risk_dollar)
    if n_valid:
        fp  = outcomes.loc[valid, "fill_price"]
        rd  = outcomes.loc[valid, "risk_dollar"]
        adv = ((df.loc[valid, "next_day_low"]  - fp) / rd).dropna()
        fav = ((df.loc[valid, "next_day_high"] - fp) / rd).dropna()
        mean_mae_proxy   = round(float(adv.mean()), 3)               if len(adv) else None
        mean_mfe_proxy   = round(float(fav.mean()), 3)               if len(fav) else None
        pct_mfe_above_2r = round(float((fav >= 2.0).mean() * 100), 2) if len(fav) else None
        mean_risk_pct    = round(float((rd / fp * 100).mean()), 3)   if len(rd)  else None
    else:
        mean_mae_proxy = mean_mfe_proxy = pct_mfe_above_2r = mean_risk_pct = None

    # Mean win P&L (= fixed R for fixed-R targets, or mean implied_R for range targets)
    win_valid = valid & (outcomes["outcome"] == "clean_win")
    if win_valid.any():
        win_pnl    = outcomes.loc[win_valid, "pnl_r"].dropna()
        mean_win_r = round(float(win_pnl.mean()), 3) if len(win_pnl) else None
    else:
        mean_win_r = None

    return {
        "n_events":             n_total,
        "n_triggered":          n_triggered,
        "trigger_rate_pct":     round(n_triggered / n_total * 100, 2) if n_total else None,
        "n_gap_fill_triggered": n_gap_fill,
        "gap_fill_rate_pct":    round(n_gap_fill / n_triggered * 100, 2) if n_triggered else None,
        "n_cancelled":          n_cancelled,
        "n_valid_triggered":    n_valid,
        "n_win":                n_win,
        "n_loss_total":         n_loss,
        "n_both_hit":           n_both,
        "n_time_exit":          n_time,
        "win_rate_pct":         win_rate,
        "loss_rate_pct":        loss_rate,
        "time_exit_rate_pct":   time_rate,
        "mean_pnl_r":           mean_pnl,
        "median_pnl_r":         median_pnl,
        "expectancy_r":         mean_pnl,
        "mean_win_r":           mean_win_r,
        "mean_risk_pct":        mean_risk_pct,
        "mean_mae_proxy_r":     mean_mae_proxy,
        "mean_mfe_proxy_r":     mean_mfe_proxy,
        "pct_mfe_above_2r":     pct_mfe_above_2r,
    }


# ---------------------------------------------------------------------------
# Summary builders
# ---------------------------------------------------------------------------

def _build_template_summary(
    primary_df: pd.DataFrame,
    secondary_df: pd.DataFrame,
    range_dollar_all: pd.Series,
) -> pd.DataFrame:
    """All 17 templates x 2 slices = 34 rows."""
    rows = []
    slices = [
        (GC_PRIMARY,   primary_df),
        (GC_SECONDARY, secondary_df),
    ]
    for slice_name, sdf in slices:
        rd_s = range_dollar_all.reindex(sdf.index)
        for entry_id, stop_id, target_id, use_risk_cancel in TEMPLATES_B2:
            tid = _template_id(entry_id, stop_id, target_id, use_risk_cancel)
            outcomes = _simulate_template(sdf, entry_id, stop_id, target_id,
                                          use_risk_cancel, rd_s)
            m = _template_metrics(sdf, outcomes)
            row = {
                "slice":           slice_name,
                "template_id":     tid,
                "entry_id":        entry_id,
                "stop_id":         stop_id,
                "target_id":       target_id,
                "use_risk_cancel": use_risk_cancel,
            }
            row.update(m)
            rows.append(row)
    return pd.DataFrame(rows)


def _build_comparison(
    primary_df: pd.DataFrame,
    range_dollar_all: pd.Series,
) -> pd.DataFrame:
    """All 17 templates on primary slice (head-to-head comparison)."""
    rows = []
    rd_s = range_dollar_all.reindex(primary_df.index)
    for entry_id, stop_id, target_id, use_risk_cancel in TEMPLATES_B2:
        tid = _template_id(entry_id, stop_id, target_id, use_risk_cancel)
        outcomes = _simulate_template(primary_df, entry_id, stop_id, target_id,
                                      use_risk_cancel, rd_s)
        m = _template_metrics(primary_df, outcomes)
        row = {
            "template_id":     tid,
            "entry_id":        entry_id,
            "stop_id":         stop_id,
            "target_id":       target_id,
            "use_risk_cancel": use_risk_cancel,
        }
        row.update(m)
        rows.append(row)
    return pd.DataFrame(rows)


def _build_yearly_summary(
    primary_df: pd.DataFrame,
    range_dollar_all: pd.Series,
    top_templates: list,
) -> pd.DataFrame:
    """Year x template for selected top templates (primary slice)."""
    pdf = primary_df.copy()
    pdf["year"] = pd.to_datetime(pdf["signal_date"]).dt.year
    rd_s = range_dollar_all.reindex(pdf.index)
    rows = []
    for entry_id, stop_id, target_id, use_risk_cancel in top_templates:
        tid = _template_id(entry_id, stop_id, target_id, use_risk_cancel)
        outcomes = _simulate_template(pdf, entry_id, stop_id, target_id,
                                      use_risk_cancel, rd_s)
        for yr in sorted(pdf["year"].unique()):
            yr_mask = pdf["year"] == yr
            yr_df   = pdf[yr_mask]
            yr_out  = outcomes[yr_mask]
            if yr_df.empty:
                continue
            m = _template_metrics(yr_df, yr_out)
            rows.append({
                "template_id":       tid,
                "year":              yr,
                "n_events":          m["n_events"],
                "n_triggered":       m["n_triggered"],
                "trigger_rate_pct":  m["trigger_rate_pct"],
                "n_valid_triggered": m["n_valid_triggered"],
                "win_rate_pct":      m["win_rate_pct"],
                "loss_rate_pct":     m["loss_rate_pct"],
                "time_exit_rate_pct": m["time_exit_rate_pct"],
                "mean_pnl_r":        m["mean_pnl_r"],
                "expectancy_r":      m["expectancy_r"],
                "mean_win_r":        m["mean_win_r"],
                "mean_risk_pct":     m["mean_risk_pct"],
                "n_win":             m["n_win"],
                "n_loss_total":      m["n_loss_total"],
                "n_time_exit":       m["n_time_exit"],
                "mean_mae_proxy_r":  m["mean_mae_proxy_r"],
                "mean_mfe_proxy_r":  m["mean_mfe_proxy_r"],
            })
    return pd.DataFrame(rows)


def _build_event_rows_output(
    primary_df: pd.DataFrame,
    signal_low_all: pd.Series,
    signal_high_all: pd.Series,
    range_dollar_all: pd.Series,
) -> pd.DataFrame:
    """
    Primary slice event rows with derived signal prices and night-before plan prices.
    Useful for manual inspection of what the TOS orders would look like.
    Plan stop prices use entry_price as anchor (a pre-execution approximation;
    actual execution stop uses fill_price which may differ if stock gaps up).
    """
    df = primary_df.copy()
    idx = df.index
    rd  = range_dollar_all.reindex(idx)
    sl  = signal_low_all.reindex(idx)
    sh  = signal_high_all.reindex(idx)

    entry_price = df["signal_day_close"] * (1.0 + ENTRY_CLOSE_BUFFER)

    df["derived_signal_day_low"]  = sl.values
    df["derived_signal_day_high"] = sh.values
    df["derived_range_dollar"]    = rd.values
    df["plan_entry_close_band"]   = entry_price.values

    # Plan stop prices (based on plan entry; what user puts in TOS the night before)
    df["plan_stop_fixed_1_5pct"]        = (entry_price * (1.0 - 0.015)).values
    df["plan_stop_fixed_2_0pct"]        = (entry_price * (1.0 - 0.020)).values
    df["plan_stop_fixed_2_5pct"]        = (entry_price * (1.0 - 0.025)).values
    df["plan_stop_fixed_3_0pct"]        = (entry_price * (1.0 - 0.030)).values
    df["plan_stop_range_proxy_75pct"]   = (entry_price - 0.75 * rd).values

    # Plan risk as % of entry price (shows trade cost at a glance)
    df["plan_risk_pct_fixed_1_5pct"]      = 1.5
    df["plan_risk_pct_fixed_2_0pct"]      = 2.0
    df["plan_risk_pct_fixed_2_5pct"]      = 2.5
    df["plan_risk_pct_fixed_3_0pct"]      = 3.0
    df["plan_risk_pct_range_proxy_75pct"] = (0.75 * rd / entry_price * 100).round(3).values

    return df


# ---------------------------------------------------------------------------
# Console formatting helpers
# ---------------------------------------------------------------------------

def _fmt(label: str, m: dict) -> None:
    n_ev   = m.get("n_events", 0)
    n_val  = m.get("n_valid_triggered", 0)
    tr_pct = m.get("trigger_rate_pct") or 0.0
    wr     = m.get("win_rate_pct")     or float("nan")
    lr     = m.get("loss_rate_pct")    or float("nan")
    ep     = m.get("expectancy_r")     or float("nan")
    rp     = m.get("mean_risk_pct")    or float("nan")
    mfep   = m.get("pct_mfe_above_2r") or float("nan")
    mwr    = m.get("mean_win_r")       or float("nan")
    print(
        f"  {label:<60}  n_valid={n_val:>5,}  trig={tr_pct:>5.1f}%  "
        f"wr={wr:>5.1f}%  lr={lr:>5.1f}%  E={ep:>+7.3f}R  "
        f"risk%={rp:>4.1f}%  mfe>2R={mfep:>5.1f}%  mean_win_R={mwr:>4.2f}"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="phase_r5 batch_2 execution template research: gap_directional_trap"
    )
    parser.add_argument(
        "--phase-r4-events", default=PHASE_R4_EVENTS_CSV,
        help="Path to phase_r4 grandchild event rows CSV"
    )
    args = parser.parse_args()

    print("=" * 100)
    print("research_run_gap_directional_trap_phase_r5_batch_2_wider_stop_research")
    print("Track  : plan_next_day_day_trade")
    print("Family : gap_directional_trap")
    print("Phase  : phase_r5__execution_template_research (batch_2)")
    print(f"Run date: {TODAY}")
    print("-" * 100)
    print("SIMULATION BASIS: daily-bar OHLCV (intraday 1m not available for full universe)")
    print("CONSERVATIVE RULE: both stop and target hit same bar => treated as LOSS")
    print("KEY CHANGE FROM BATCH_1: stop is now fixed-% of fill price or range-proxy,")
    print("  NOT the structural signal_day_low. Risk scales with stop percentage.")
    print("-" * 100)
    print(f"Input : {args.phase_r4_events}")
    print("=" * 100)

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

    print(f"\nSlice sizes:")
    print(f"  PRIMARY   {GC_PRIMARY:<55}  n={len(primary_df):>6,}")
    print(f"  SECONDARY {GC_SECONDARY:<55}  n={len(secondary_df):>6,}")

    # -- Derive signal prices for all events ---------------------------------

    signal_low_all, signal_high_all, range_dollar_all = _derive_signal_prices(all_events)
    signal_low_all.index    = all_events.index
    signal_high_all.index   = all_events.index
    range_dollar_all.index  = all_events.index

    # Spot check
    row0 = all_events.iloc[0]
    rd   = row0["signal_day_close"] * row0["signal_day_range_pct"]
    sl   = row0["signal_day_close"] - row0["signal_day_close_location"] * rd
    cl_chk = (row0["signal_day_close"] - sl) / rd if rd > 0 else float("nan")
    print(f"\nDerivation spot check (row 0: {row0['ticker']} {row0['signal_date']}):")
    print(f"  signal_day_close    : {row0['signal_day_close']:.4f}")
    print(f"  signal_day_range_pct: {row0['signal_day_range_pct']:.6f}")
    print(f"  signal_day_close_loc: {row0['signal_day_close_location']:.4f}")
    print(f"  derived low         : {sl:.4f}  |  range_dollar: {rd:.4f}")
    print(f"  cl_check (matches close_loc): {cl_chk:.4f}")

    # Mean range dollar on primary slice (useful context)
    prd = range_dollar_all.reindex(primary_df.index)
    print(f"\nPrimary slice range_dollar summary:")
    print(f"  mean  : {prd.mean():.4f}")
    print(f"  median: {prd.median():.4f}")
    print(f"  mean range_pct: {primary_df['signal_day_range_pct'].mean()*100:.3f}%")
    print(f"  mean_risk if S_range_proxy_75pct: {(prd * 0.75 / primary_df['signal_day_close'] * 100).mean():.3f}%")

    # -- Template overview ---------------------------------------------------

    print(f"\n{'='*100}")
    print("BATCH_2 TEMPLATE OVERVIEW")
    print(f"{'='*100}")
    print(f"  Entry  : E_close_band only (signal_close * {1+ENTRY_CLOSE_BUFFER:.4f})")
    print(f"  Stops  : S_fixed_1_5pct | S_fixed_2_0pct | S_fixed_2_5pct | S_fixed_3_0pct")
    print(f"           S_range_proxy_75pct (fill - 0.75 * prior_day_range_dollar)")
    print(f"  Targets: T_fixed_1_5r | T_fixed_2_0r | T_fixed_3_0r")
    print(f"           T_range_50pct (fill + 0.50 * range_dollar)")
    print(f"           T_range_75pct (fill + 0.75 * range_dollar)")
    print(f"  Cancel : no_cancel (fixed-% stops) | cancel_if_risk_gt_{int(CANCEL_RISK_PCT*100)}pct (range-proxy)")
    print(f"  Total  : {len(TEMPLATES_B2)} templates on 2 slices")

    # =========================================================================
    # PRIMARY SLICE
    # =========================================================================

    print(f"\n{'='*100}")
    print(f"PRIMARY SLICE: {GC_PRIMARY}  (n={len(primary_df):,})")
    print(f"{'='*100}")

    rd_primary = range_dollar_all.reindex(primary_df.index)

    print("\n  -- Fixed-% stops --")
    for entry_id, stop_id, target_id, use_risk_cancel in TEMPLATES_B2:
        if "fixed" not in stop_id:
            continue
        tid = _template_id(entry_id, stop_id, target_id, use_risk_cancel)
        oc  = _simulate_template(primary_df, entry_id, stop_id, target_id,
                                 use_risk_cancel, rd_primary)
        m   = _template_metrics(primary_df, oc)
        _fmt(tid, m)

    print("\n  -- Range-proxy stop (S_range_proxy_75pct) --")
    for entry_id, stop_id, target_id, use_risk_cancel in TEMPLATES_B2:
        if "range_proxy" not in stop_id:
            continue
        tid = _template_id(entry_id, stop_id, target_id, use_risk_cancel)
        oc  = _simulate_template(primary_df, entry_id, stop_id, target_id,
                                 use_risk_cancel, rd_primary)
        m   = _template_metrics(primary_df, oc)
        _fmt(tid, m)

    # =========================================================================
    # SECONDARY SLICE — key templates only
    # =========================================================================

    print(f"\n{'='*100}")
    print(f"SECONDARY SLICE: {GC_SECONDARY}  (n={len(secondary_df):,})")
    print(f"  (key templates only: best per stop family)")
    print(f"{'='*100}")

    rd_secondary = range_dollar_all.reindex(secondary_df.index)

    key_templates = [
        ("E_close_band", "S_fixed_1_5pct",      "T_fixed_3_0r",  False),
        ("E_close_band", "S_fixed_2_0pct",       "T_fixed_3_0r",  False),
        ("E_close_band", "S_fixed_2_0pct",       "T_range_50pct", False),
        ("E_close_band", "S_fixed_2_0pct",       "T_range_75pct", False),
        ("E_close_band", "S_fixed_2_5pct",       "T_fixed_3_0r",  False),
        ("E_close_band", "S_fixed_3_0pct",       "T_fixed_3_0r",  False),
        ("E_close_band", "S_range_proxy_75pct",  "T_fixed_3_0r",  False),
        ("E_close_band", "S_range_proxy_75pct",  "T_range_75pct", False),
        ("E_close_band", "S_range_proxy_75pct",  "T_fixed_3_0r",  True),
    ]
    for entry_id, stop_id, target_id, use_risk_cancel in key_templates:
        tid = _template_id(entry_id, stop_id, target_id, use_risk_cancel)
        oc  = _simulate_template(secondary_df, entry_id, stop_id, target_id,
                                 use_risk_cancel, rd_secondary)
        m   = _template_metrics(secondary_df, oc)
        _fmt(tid, m)

    # =========================================================================
    # Build full summary + comparison + yearly tables
    # =========================================================================

    print(f"\n{'='*100}")
    print("BUILDING OUTPUT FILES...")
    print(f"{'='*100}")

    summary_df    = _build_template_summary(primary_df, secondary_df, range_dollar_all)
    comparison_df = _build_comparison(primary_df, range_dollar_all)

    # Select top templates for yearly summary (top 6 by primary slice expectancy)
    comp_sorted   = comparison_df.sort_values("expectancy_r", ascending=False)
    top_tuples    = [
        (r["entry_id"], r["stop_id"], r["target_id"], r["use_risk_cancel"])
        for _, r in comp_sorted.head(6).iterrows()
    ]
    yearly_df     = _build_yearly_summary(primary_df, range_dollar_all, top_tuples)

    event_rows_df = _build_event_rows_output(
        primary_df, signal_low_all, signal_high_all, range_dollar_all
    )

    # -- Save outputs --------------------------------------------------------

    DATE_STR = TODAY
    BATCH    = "batch_2"

    comparison_path  = os.path.join(OUTPUT_DIR,
        f"{BATCH}_template_comparison__gap_directional_trap__phase_r5__{DATE_STR}.csv")
    summary_path     = os.path.join(OUTPUT_DIR,
        f"{BATCH}_template_summary__gap_directional_trap__phase_r5__{DATE_STR}.csv")
    yearly_path      = os.path.join(OUTPUT_DIR,
        f"{BATCH}_yearly_template_summary__gap_directional_trap__phase_r5__{DATE_STR}.csv")
    event_rows_path  = os.path.join(OUTPUT_DIR,
        f"{BATCH}_template_event_rows__gap_directional_trap__phase_r5__{DATE_STR}.csv")

    comparison_df.to_csv(comparison_path,  index=False)
    summary_df.to_csv(summary_path,        index=False)
    yearly_df.to_csv(yearly_path,          index=False)
    event_rows_df.to_csv(event_rows_path,  index=False)

    print(f"\nFiles written:")
    print(f"  {event_rows_path}")
    print(f"  {summary_path}")
    print(f"  {comparison_path}")
    print(f"  {yearly_path}")

    # =========================================================================
    # RANKED COMPARISON — primary slice sorted by expectancy
    # =========================================================================

    print(f"\n{'='*100}")
    print("TEMPLATE RANKING (primary slice, sorted by expectancy_r desc)")
    print(f"{'='*100}")
    print(f"  {'RANK':<4} {'template_id':<70} {'n_valid':>7} {'wr%':>6} {'lr%':>6} {'E':>8} {'risk%':>6} {'mfe>2R':>8}")
    for rank, (_, row) in enumerate(comp_sorted.iterrows(), 1):
        tid  = row["template_id"]
        nv   = int(row["n_valid_triggered"])
        wr   = row["win_rate_pct"]   or float("nan")
        lr   = row["loss_rate_pct"]  or float("nan")
        ep   = row["expectancy_r"]   or float("nan")
        rp   = row["mean_risk_pct"]  or float("nan")
        mfep = row["pct_mfe_above_2r"] or float("nan")
        print(
            f"  {rank:<4} {tid:<70} {nv:>7,} {wr:>6.1f}% {lr:>6.1f}% {ep:>+8.3f}R {rp:>5.1f}% {mfep:>7.1f}%"
        )

    # =========================================================================
    # YEARLY BREAKDOWN — top 4 templates
    # =========================================================================

    print(f"\n{'='*100}")
    print("YEARLY BREAKDOWN — top 4 templates (primary slice)")
    print(f"{'='*100}")

    yearly_top4_tuples = top_tuples[:4]
    for entry_id, stop_id, target_id, use_risk_cancel in yearly_top4_tuples:
        tid  = _template_id(entry_id, stop_id, target_id, use_risk_cancel)
        yr_d = yearly_df[yearly_df["template_id"] == tid]
        print(f"\n  {tid}")
        print(f"  {'year':<6} {'n_ev':>6} {'n_val':>6} {'wr%':>6} {'lr%':>6} {'te%':>6} {'E':>8} {'risk%':>6}")
        for _, yr_row in yr_d.iterrows():
            yr   = int(yr_row["year"])
            nev  = int(yr_row["n_events"])
            nv   = int(yr_row["n_valid_triggered"])
            wr   = yr_row["win_rate_pct"]   or float("nan")
            lr   = yr_row["loss_rate_pct"]  or float("nan")
            te   = yr_row["time_exit_rate_pct"] or float("nan")
            ep   = yr_row["expectancy_r"]   or float("nan")
            rp   = yr_row["mean_risk_pct"]  or float("nan")
            print(f"  {yr:<6} {nev:>6} {nv:>6} {wr:>6.1f}% {lr:>6.1f}% {te:>6.1f}% {ep:>+8.3f}R {rp:>5.1f}%")

    # =========================================================================
    # BATCH_2 SUMMARY FINDINGS
    # =========================================================================

    best_row  = comp_sorted.iloc[0]
    worst_row = comp_sorted.iloc[-1]

    print(f"\n{'='*100}")
    print("BATCH_2 SUMMARY")
    print(f"{'='*100}")
    print(f"  Best template (primary slice): {best_row['template_id']}")
    print(f"    win_rate={best_row['win_rate_pct']:.1f}%  "
          f"loss_rate={best_row['loss_rate_pct']:.1f}%  "
          f"expectancy={best_row['expectancy_r']:+.3f}R  "
          f"risk%={best_row['mean_risk_pct']:.1f}%  "
          f"mfe>2R={best_row['pct_mfe_above_2r']:.1f}%")
    print(f"  Worst template (primary slice): {worst_row['template_id']}")
    print(f"    win_rate={worst_row['win_rate_pct']:.1f}%  "
          f"expectancy={worst_row['expectancy_r']:+.3f}R")

    # 2022 spotlight for best template
    yr2022 = yearly_df[(yearly_df["template_id"] == best_row["template_id"]) &
                       (yearly_df["year"] == 2022)]
    if not yr2022.empty:
        r22 = yr2022.iloc[0]
        print(f"\n  2022 spotlight for best template:")
        print(f"    win_rate={r22['win_rate_pct']:.1f}%  "
              f"loss_rate={r22['loss_rate_pct']:.1f}%  "
              f"expectancy={r22['expectancy_r']:+.3f}R  "
              f"n_valid={int(r22['n_valid_triggered']):,}")

    print(f"\n{'='*100}")
    print("Done.")
    print(f"{'='*100}")


if __name__ == "__main__":
    main()
