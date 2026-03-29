"""
research_run_gap_directional_trap_phase_r6_deployable_variant_validation.py
Side:   research -- strategy family layer
Track:  plan_next_day_day_trade
Family: gap_directional_trap
Phase:  phase_r6__deployable_variant_validation

Purpose:
  Phase_r5 batch_2 promoted two candidate execution templates to phase_r6:

    CANDIDATE_1: E_close_band__S_range_proxy_75pct__T_fixed_2_0r
      entry  = buy stop at signal_close * 1.002
      stop   = fill - 0.75 * signal_day_range_dollar  (ATR proxy; avg ~4.7% risk)
      target = fill + 2.0 * risk  (fixed 2R)
      exit   = MOC (flat at next_day_close if neither stop nor target hit)
      primary E=+0.153R  |  secondary E=+0.244R  |  4/6 years positive

    CANDIDATE_2: E_close_band__S_fixed_3_0pct__T_fixed_3_0r
      entry  = buy stop at signal_close * 1.002
      stop   = fill * (1 - 0.030)  (3% fixed stop below fill)
      target = fill + 3.0 * risk  (fixed 3R)
      exit   = MOC (flat at next_day_close if neither stop nor target hit)
      primary E=+0.103R  |  secondary E=+0.166R  |  3/6 years positive

  Phase_r6 validates whether these candidates deserve deployable_variant promotion.

VALIDATION DIMENSIONS:
  A. Baseline confirmation (re-run batch_2 best templates; confirm numbers consistent)
  B. Slippage / entry perturbation sensitivity (+0.05%, +0.10%, +0.25% entry)
  C. Ticker concentration (per-ticker pnl; top-5/10 share; exclusion test)
  D. Regime-intensity veto (spy_realized_vol_20d gate to reduce 2022 exposure)
  E. Yearly stability (re-confirm from batch_2; check partial 2026 interpretation)

SLICES:
  PRIMARY   : gap_directional_trap__gap_up_cl_low_020__bearish__medium (n=6,320)
  SECONDARY : gap_directional_trap__gap_up_cl_low_020__bearish__medium_plus_large (n=9,865)

SIMULATION BASIS (same as phase_r5):
  Daily-bar OHLCV only -- intraday 1m not available for full universe.
  Conservative rule: both stop and target hit same daily bar => treated as LOSS.
  All templates remain TOS-compatible (night-before bracket + MOC exit).

SLIPPAGE MODEL:
  Additional entry buffer applied on top of ENTRY_CLOSE_BUFFER (0.2%).
  Effective entry = signal_close * (1 + ENTRY_CLOSE_BUFFER + slip_pct).
  For non-gap-fill triggers: fill_price = entry_price (includes slippage).
  For gap-fill triggers: fill_price = next_day_open (gap already absorbed).
  Slippage compresses time-exit P&L (higher fill → smaller open-to-close gain).

REGIME VETO MODEL:
  Uses spy_realized_vol_20d column already embedded in event rows.
  vol_gate_020: skip events where spy_realized_vol_20d > 0.20 (20% annualized)
  vol_gate_025: skip events where spy_realized_vol_20d > 0.25 (25% annualized)
  This is a night-before observable (computable from EOD SPY data).

Input:
  grandchild_event_rows__gap_directional_trap__phase_r4__2026_03_27.csv

Outputs (phase_r6_deployable_variant_validation/):
  variant_event_rows__gap_directional_trap__phase_r6__<DATE>.csv
    Primary slice events with CANDIDATE_1 simulation outcomes (for TOS reference)
  variant_summary__gap_directional_trap__phase_r6__<DATE>.csv
    2 candidates x 2 slices = 4 rows (baseline performance confirmation)
  variant_slippage_sensitivity__gap_directional_trap__phase_r6__<DATE>.csv
    2 candidates x 4 slippage levels x 2 slices = 16 rows
  variant_yearly_summary__gap_directional_trap__phase_r6__<DATE>.csv
    2 candidates x 2 slices x 6 years = 24 rows
  ticker_concentration_summary__gap_directional_trap__phase_r6__<DATE>.csv
    Per-ticker pnl for CANDIDATE_1, primary slice (sorted by pnl contribution)
  regime_veto_summary__gap_directional_trap__phase_r6__<DATE>.csv
    3 veto levels x 2 candidates x 2 slices = 12 rows

Usage:
  python research_run_gap_directional_trap_phase_r6_deployable_variant_validation.py

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
    "gap_directional_trap", "phase_r6_deployable_variant_validation",
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

TODAY = datetime.date.today().strftime("%Y_%m_%d")

# ---------------------------------------------------------------------------
# Identity constants
# ---------------------------------------------------------------------------

CHILD1_NAME  = "gap_directional_trap__gap_up_cl_low_020"
GC_PRIMARY   = f"{CHILD1_NAME}__bearish__medium"
GC_SECONDARY = f"{CHILD1_NAME}__bearish__medium_plus_large"   # constructed label for combined slice

# ---------------------------------------------------------------------------
# Template parameters
# ---------------------------------------------------------------------------

ENTRY_CLOSE_BUFFER = 0.002   # 0.2% -- same as phase_r5 batch_2

# Phase_r6 validated candidates (promoted from phase_r5 batch_2)
CANDIDATES = [
    {
        "id":            "candidate_1__S_range_proxy_75pct__T_fixed_2_0r",
        "label":         "CANDIDATE_1",
        "entry_id":      "E_close_band",
        "stop_id":       "S_range_proxy_75pct",
        "target_id":     "T_fixed_2_0r",
        "r_target_val":  2.0,
    },
    {
        "id":            "candidate_2__S_fixed_3_0pct__T_fixed_3_0r",
        "label":         "CANDIDATE_2",
        "entry_id":      "E_close_band",
        "stop_id":       "S_fixed_3_0pct",
        "target_id":     "T_fixed_3_0r",
        "r_target_val":  3.0,
    },
]

# Slippage sensitivity levels (applied as additional entry buffer)
SLIPPAGE_LEVELS = [
    ("slip_000pct", 0.0000),   # baseline -- no perturbation (replicates batch_2)
    ("slip_005pct", 0.0005),   # +0.05% entry perturbation
    ("slip_010pct", 0.0010),   # +0.10% entry perturbation
    ("slip_025pct", 0.0025),   # +0.25% worst-case (rough fill / wide spread stock)
]

# Regime-intensity veto levels (applied via spy_realized_vol_20d field)
VETO_LEVELS = [
    ("no_veto",      None),    # all eligible events (baseline)
    ("vol_gate_020", 0.20),    # skip events where spy_realized_vol_20d > 0.20 (annualized)
    ("vol_gate_025", 0.25),    # skip events where spy_realized_vol_20d > 0.25 (annualized)
]


# ---------------------------------------------------------------------------
# Signal day price derivation (identical to phase_r5 batch_2)
# ---------------------------------------------------------------------------

def _derive_signal_prices(df: pd.DataFrame):
    """
    Returns (signal_low, signal_high, range_dollar) as Series indexed by df.index.

    signal_day_range_pct = (high - low) / close  (decimal fraction, stored in cache)
    range_dollar = close * range_pct
    low  = close - close_location * range_dollar
    high = low + range_dollar
    """
    range_dollar = df["signal_day_close"] * df["signal_day_range_pct"]
    low  = df["signal_day_close"] - df["signal_day_close_location"] * range_dollar
    high = low + range_dollar
    return low, high, range_dollar


# ---------------------------------------------------------------------------
# Core simulation
# ---------------------------------------------------------------------------

def _simulate_candidate(
    df: pd.DataFrame,
    cand: dict,
    range_dollar: pd.Series,
    slip_pct: float = 0.0,
    veto_vol_max: float = None,
) -> pd.DataFrame:
    """
    Simulate one candidate template for all rows in df.

    Parameters
    ----------
    slip_pct      : additional entry buffer on top of ENTRY_CLOSE_BUFFER.
                    Models a worse-than-planned fill (gap above plan, wide spread, etc.)
    veto_vol_max  : if not None, events where spy_realized_vol_20d > veto_vol_max
                    are marked 'vetoed' and excluded from outcome statistics.

    Entry logic (E_close_band):
      buy stop at signal_close * (1 + ENTRY_CLOSE_BUFFER + slip_pct)
      gap_fill: open > entry_price => fill at open
      intraday: high >= entry_price => fill at entry_price

    Stop logic:
      S_range_proxy_75pct : fill - 0.75 * signal_day_range_dollar
      S_fixed_3_0pct      : fill * (1 - 0.030)

    Target logic:
      T_fixed_2_0r : fill + 2.0 * risk
      T_fixed_3_0r : fill + 3.0 * risk

    Outcome (conservative daily-bar):
      clean_win  : high >= target AND low > stop
      stop_loss  : low <= stop AND high < target
      both_hit   : high >= target AND low <= stop  --> treated as LOSS
      time_exit  : neither hit; P&L = (close - fill) / risk, clipped [-3.0, 10.0]
      not_triggered: did not reach entry
      vetoed     : excluded by regime veto
    """
    stop_id       = cand["stop_id"]
    r_target_val  = cand["r_target_val"]

    idx = df.index
    rd  = range_dollar.reindex(idx)

    # -- Regime veto ----------------------------------------------------------
    if veto_vol_max is not None:
        # Fill NaN vol with 0.0 so they pass the gate (conservative — don't lose data on NaN)
        vol_col   = df["spy_realized_vol_20d"].fillna(0.0)
        eligible  = vol_col <= veto_vol_max
    else:
        eligible  = pd.Series(True, index=idx)

    # -- Entry price (with optional slippage perturbation) --------------------
    effective_buffer = ENTRY_CLOSE_BUFFER + slip_pct
    entry_price = df["signal_day_close"] * (1.0 + effective_buffer)

    # -- Trigger (only eligible events can trigger) ---------------------------
    gap_fill_trigger = eligible & (df["next_day_open"] > entry_price)
    intraday_trigger = eligible & (df["next_day_high"] >= entry_price)
    triggered        = gap_fill_trigger | intraday_trigger

    # -- Fill price -----------------------------------------------------------
    fill_price = pd.Series(
        np.where(gap_fill_trigger.values, df["next_day_open"].values, entry_price.values),
        index=idx,
    )

    # -- Stop price -----------------------------------------------------------
    if stop_id == "S_range_proxy_75pct":
        stop_price = fill_price - 0.75 * rd
    elif stop_id == "S_fixed_3_0pct":
        stop_price = fill_price * (1.0 - 0.030)
    else:
        raise ValueError(f"Unknown stop_id: {stop_id}")

    # -- Risk validation ------------------------------------------------------
    risk        = fill_price - stop_price
    valid_setup = triggered & (risk > 0.0)

    # -- Target price ---------------------------------------------------------
    target_price = fill_price + r_target_val * risk

    # -- Outcome (conservative daily-bar rules) --------------------------------
    hit_target = df["next_day_high"] >= target_price
    hit_stop   = df["next_day_low"]  <= stop_price

    outcome = pd.Series("not_triggered", index=idx, dtype=object)
    outcome[~eligible]               = "vetoed"
    outcome[triggered & ~valid_setup] = "invalid_risk"
    out_valid = valid_setup
    outcome[out_valid & hit_target & ~hit_stop] = "clean_win"
    outcome[out_valid & ~hit_target & hit_stop] = "stop_loss"
    outcome[out_valid & hit_target  & hit_stop] = "both_hit"    # treated as LOSS
    outcome[out_valid & ~hit_target & ~hit_stop] = "time_exit"

    # -- P&L in R (risk-normalized) ------------------------------------------
    pnl_r = pd.Series(np.nan, index=idx)

    win_mask  = out_valid & (outcome == "clean_win")
    loss_mask = out_valid & ((outcome == "stop_loss") | (outcome == "both_hit"))
    time_mask = out_valid & (outcome == "time_exit")

    pnl_r[win_mask]  = r_target_val    # fixed R for both candidates
    pnl_r[loss_mask] = -1.0

    safe_risk = risk.replace(0.0, np.nan)
    pnl_r[time_mask] = (
        (df["next_day_close"] - fill_price) / safe_risk
    )[time_mask].clip(-3.0, 10.0)

    gap_fill_used = triggered & gap_fill_trigger

    return pd.DataFrame({
        "entry_price":      entry_price,
        "fill_price":       fill_price.where(triggered),
        "stop_price":       stop_price.where(valid_setup),
        "target_price":     target_price.where(valid_setup),
        "risk_dollar":      risk.where(valid_setup),
        "eligible":         eligible.astype(int),
        "triggered":        triggered.astype(int),
        "gap_fill_trigger": gap_fill_used.astype(int),
        "valid_setup":      valid_setup.astype(int),
        "outcome":          outcome,
        "pnl_r":            pnl_r,
    }, index=idx)


# ---------------------------------------------------------------------------
# Metrics aggregator
# ---------------------------------------------------------------------------

def _metrics(df: pd.DataFrame, outcomes: pd.DataFrame) -> dict:
    """Aggregate simulation outcomes into summary metrics dict."""
    n_total  = len(df)
    n_vetoed = int((outcomes["outcome"] == "vetoed").sum())
    n_eligible = n_total - n_vetoed

    trig      = outcomes["triggered"].astype(bool)
    valid     = outcomes["valid_setup"].astype(bool)
    gap_fill  = outcomes["gap_fill_trigger"].astype(bool)

    n_triggered = int(trig.sum())
    n_gap_fill  = int(gap_fill.sum())
    n_valid     = int(valid.sum())

    oc_valid = outcomes.loc[valid, "outcome"]
    n_win  = int((oc_valid == "clean_win").sum())
    n_loss = int(((oc_valid == "stop_loss") | (oc_valid == "both_hit")).sum())
    n_both = int((oc_valid == "both_hit").sum())
    n_time = int((oc_valid == "time_exit").sum())

    pnl   = outcomes.loc[valid, "pnl_r"].dropna()
    n_pnl = len(pnl)

    win_rate  = round(n_win  / n_valid * 100, 2) if n_valid else None
    loss_rate = round(n_loss / n_valid * 100, 2) if n_valid else None
    time_rate = round(n_time / n_valid * 100, 2) if n_valid else None
    mean_pnl  = round(float(pnl.mean()),   3) if n_pnl else None
    med_pnl   = round(float(pnl.median()), 3) if n_pnl else None

    mean_risk_pct = None
    mean_mae      = None
    mean_mfe      = None
    if n_valid:
        fp  = outcomes.loc[valid, "fill_price"].dropna()
        rd  = outcomes.loc[valid, "risk_dollar"].dropna()
        if len(rd) and len(fp):
            mean_risk_pct = round(float((rd / fp * 100).mean()), 3)
        adv = ((df.loc[valid, "next_day_low"]  - outcomes.loc[valid, "fill_price"]) /
               outcomes.loc[valid, "risk_dollar"].replace(0, np.nan)).dropna()
        fav = ((df.loc[valid, "next_day_high"] - outcomes.loc[valid, "fill_price"]) /
               outcomes.loc[valid, "risk_dollar"].replace(0, np.nan)).dropna()
        if len(adv):
            mean_mae = round(float(adv.mean()), 3)
        if len(fav):
            mean_mfe = round(float(fav.mean()), 3)

    return {
        "n_events":             n_total,
        "n_vetoed":             n_vetoed,
        "n_eligible":           n_eligible,
        "n_triggered":          n_triggered,
        "trigger_rate_pct":     round(n_triggered / n_eligible * 100, 2) if n_eligible else None,
        "n_gap_fill_triggered": n_gap_fill,
        "gap_fill_rate_pct":    round(n_gap_fill / n_triggered * 100, 2) if n_triggered else None,
        "n_valid_triggered":    n_valid,
        "n_win":                n_win,
        "n_loss_total":         n_loss,
        "n_both_hit":           n_both,
        "n_time_exit":          n_time,
        "win_rate_pct":         win_rate,
        "loss_rate_pct":        loss_rate,
        "time_exit_rate_pct":   time_rate,
        "expectancy_r":         mean_pnl,
        "median_pnl_r":         med_pnl,
        "mean_risk_pct":        mean_risk_pct,
        "mean_mae_proxy_r":     mean_mae,
        "mean_mfe_proxy_r":     mean_mfe,
    }


# ---------------------------------------------------------------------------
# Output builders
# ---------------------------------------------------------------------------

def _build_variant_summary(primary_df, secondary_df, rd_all):
    """Baseline: 2 candidates x 2 slices = 4 rows."""
    rows = []
    slices = [(GC_PRIMARY, primary_df), (GC_SECONDARY, secondary_df)]
    for slice_name, sdf in slices:
        rd_s = rd_all.reindex(sdf.index)
        for cand in CANDIDATES:
            oc = _simulate_candidate(sdf, cand, rd_s)
            m  = _metrics(sdf, oc)
            row = {
                "slice":        slice_name,
                "candidate_id": cand["id"],
                "label":        cand["label"],
                "stop_id":      cand["stop_id"],
                "target_id":    cand["target_id"],
            }
            row.update(m)
            rows.append(row)
    return pd.DataFrame(rows)


def _build_slippage_sensitivity(primary_df, secondary_df, rd_all):
    """2 candidates x 4 slippage levels x 2 slices = 16 rows."""
    rows = []
    slices = [(GC_PRIMARY, primary_df), (GC_SECONDARY, secondary_df)]
    for slice_name, sdf in slices:
        rd_s = rd_all.reindex(sdf.index)
        for cand in CANDIDATES:
            for slip_label, slip_pct in SLIPPAGE_LEVELS:
                oc = _simulate_candidate(sdf, cand, rd_s, slip_pct=slip_pct)
                m  = _metrics(sdf, oc)
                row = {
                    "slice":         slice_name,
                    "candidate_id":  cand["id"],
                    "label":         cand["label"],
                    "slippage_id":   slip_label,
                    "slippage_pct":  round(slip_pct * 100, 3),
                }
                row.update(m)
                rows.append(row)
    return pd.DataFrame(rows)


def _build_yearly_summary(primary_df, secondary_df, rd_all):
    """2 candidates x 2 slices x years."""
    rows = []
    slices = [(GC_PRIMARY, primary_df), (GC_SECONDARY, secondary_df)]
    for slice_name, sdf in slices:
        sdf_y = sdf.copy()
        sdf_y["year"] = pd.to_datetime(sdf_y["signal_date"]).dt.year
        rd_s = rd_all.reindex(sdf_y.index)
        for cand in CANDIDATES:
            oc = _simulate_candidate(sdf_y, cand, rd_s)
            for yr in sorted(sdf_y["year"].unique()):
                yr_mask = sdf_y["year"] == yr
                yr_df   = sdf_y[yr_mask]
                yr_oc   = oc[yr_mask]
                if yr_df.empty:
                    continue
                m = _metrics(yr_df, yr_oc)
                rows.append({
                    "slice":              slice_name,
                    "candidate_id":       cand["id"],
                    "label":              cand["label"],
                    "stop_id":            cand["stop_id"],
                    "target_id":          cand["target_id"],
                    "year":               yr,
                    "n_events":           m["n_events"],
                    "n_valid_triggered":  m["n_valid_triggered"],
                    "win_rate_pct":       m["win_rate_pct"],
                    "loss_rate_pct":      m["loss_rate_pct"],
                    "time_exit_rate_pct": m["time_exit_rate_pct"],
                    "expectancy_r":       m["expectancy_r"],
                    "n_win":              m["n_win"],
                    "n_loss_total":       m["n_loss_total"],
                    "n_time_exit":        m["n_time_exit"],
                    "mean_risk_pct":      m["mean_risk_pct"],
                    "mean_mae_proxy_r":   m["mean_mae_proxy_r"],
                    "mean_mfe_proxy_r":   m["mean_mfe_proxy_r"],
                })
    return pd.DataFrame(rows)


def _build_ticker_concentration(primary_df, rd_all):
    """
    Per-ticker pnl aggregation for CANDIDATE_1, primary slice, baseline.
    Returns (concentration_df, total_pnl, n_valid_total, valid_df_with_pnl).
    """
    cand = CANDIDATES[0]   # CANDIDATE_1: S_range_proxy_75pct + T_fixed_2_0r
    rd_s = rd_all.reindex(primary_df.index)
    oc   = _simulate_candidate(primary_df, cand, rd_s)

    valid_mask = oc["valid_setup"].astype(bool)
    combined   = primary_df.copy()
    combined["outcome"]     = oc["outcome"]
    combined["pnl_r"]       = oc["pnl_r"]
    combined["valid_setup"] = oc["valid_setup"]

    valid_df = combined[valid_mask].copy()
    total_pnl = float(valid_df["pnl_r"].dropna().sum())
    n_valid   = len(valid_df)

    agg = (
        valid_df.groupby("ticker")
        .agg(
            n_events      =("pnl_r", "count"),
            n_win         =("outcome", lambda x: (x == "clean_win").sum()),
            n_loss        =("outcome", lambda x: ((x == "stop_loss") | (x == "both_hit")).sum()),
            n_time_exit   =("outcome", lambda x: (x == "time_exit").sum()),
            pnl_r_sum     =("pnl_r", "sum"),
            pnl_r_mean    =("pnl_r", "mean"),
        )
        .reset_index()
    )
    agg["win_rate_pct"]       = (agg["n_win"]  / agg["n_events"] * 100).round(2)
    agg["loss_rate_pct"]      = (agg["n_loss"] / agg["n_events"] * 100).round(2)
    agg["pct_of_total_events"] = (agg["n_events"] / n_valid * 100).round(2)
    if total_pnl != 0:
        agg["pct_of_total_pnl"] = (agg["pnl_r_sum"] / total_pnl * 100).round(2)
    else:
        agg["pct_of_total_pnl"] = None

    agg = agg.sort_values("pnl_r_sum", ascending=False).reset_index(drop=True)
    agg["rank_by_pnl"] = agg.index + 1
    if total_pnl != 0:
        agg["cum_pct_pnl"] = (agg["pnl_r_sum"].cumsum() / total_pnl * 100).round(2)
    else:
        agg["cum_pct_pnl"] = None
    agg["pnl_r_sum"]  = agg["pnl_r_sum"].round(4)
    agg["pnl_r_mean"] = agg["pnl_r_mean"].round(5)

    return agg, total_pnl, n_valid, valid_df


def _excl_test(valid_df, n):
    """Expectancy after removing top-N tickers by pnl_r_sum contribution."""
    by_ticker = valid_df.groupby("ticker")["pnl_r"].sum().sort_values(ascending=False)
    top_n     = by_ticker.head(n).index.tolist()
    rest      = valid_df[~valid_df["ticker"].isin(top_n)]
    if rest.empty:
        return None, 0
    return round(float(rest["pnl_r"].mean()), 4), len(rest)


def _build_regime_veto_summary(primary_df, secondary_df, rd_all):
    """3 veto levels x 2 candidates x 2 slices = 12 rows; includes 2022-specific metrics."""
    rows = []
    slices = [(GC_PRIMARY, primary_df), (GC_SECONDARY, secondary_df)]
    for slice_name, sdf in slices:
        sdf_y = sdf.copy()
        sdf_y["year"] = pd.to_datetime(sdf_y["signal_date"]).dt.year
        rd_s = rd_all.reindex(sdf_y.index)
        for cand in CANDIDATES:
            for veto_label, veto_vol_max in VETO_LEVELS:
                oc = _simulate_candidate(sdf_y, cand, rd_s, veto_vol_max=veto_vol_max)
                m  = _metrics(sdf_y, oc)

                # 2022-specific
                mask_2022 = sdf_y["year"] == 2022
                m_2022    = _metrics(sdf_y[mask_2022], oc[mask_2022])

                n_ev = m["n_events"]
                row = {
                    "slice":              slice_name,
                    "candidate_id":       cand["id"],
                    "label":              cand["label"],
                    "veto_level":         veto_label,
                    "n_events_total":     n_ev,
                    "n_vetoed":           m["n_vetoed"],
                    "n_eligible":         m["n_eligible"],
                    "pct_eligible":       round(m["n_eligible"] / n_ev * 100, 1) if n_ev else None,
                    "n_valid_triggered":  m["n_valid_triggered"],
                    "expectancy_r":       m["expectancy_r"],
                    "win_rate_pct":       m["win_rate_pct"],
                    "loss_rate_pct":      m["loss_rate_pct"],
                    "time_exit_rate_pct": m["time_exit_rate_pct"],
                    "n_vetoed_2022":      m_2022["n_vetoed"],
                    "n_eligible_2022":    m_2022["n_eligible"],
                    "n_valid_2022":       m_2022["n_valid_triggered"],
                    "expectancy_2022":    m_2022["expectancy_r"],
                }
                rows.append(row)
    return pd.DataFrame(rows)


def _build_event_rows_output(primary_df, rd_all, sl_all, sh_all):
    """
    Primary slice events with CANDIDATE_1 simulation outcomes (baseline).
    Suitable as night-before TOS plan reference.
    """
    cand = CANDIDATES[0]
    rd_s = rd_all.reindex(primary_df.index)
    sl_s = sl_all.reindex(primary_df.index)
    sh_s = sh_all.reindex(primary_df.index)

    oc = _simulate_candidate(primary_df, cand, rd_s)

    df = primary_df.copy()
    df["derived_range_dollar"]    = rd_s.values
    df["derived_signal_day_low"]  = sl_s.values
    df["derived_signal_day_high"] = sh_s.values
    df["r6_candidate"]            = cand["id"]
    df["r6_entry_price"]          = oc["entry_price"].values
    df["r6_fill_price"]           = oc["fill_price"].values
    df["r6_stop_price"]           = oc["stop_price"].values
    df["r6_target_price"]         = oc["target_price"].values
    df["r6_risk_dollar"]          = oc["risk_dollar"].values
    df["r6_triggered"]            = oc["triggered"].values
    df["r6_gap_fill"]             = oc["gap_fill_trigger"].values
    df["r6_valid_setup"]          = oc["valid_setup"].values
    df["r6_outcome"]              = oc["outcome"].values
    df["r6_pnl_r"]                = oc["pnl_r"].values

    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    sep = "=" * 80

    print(sep)
    print("research_run_gap_directional_trap_phase_r6_deployable_variant_validation")
    print("Track  : plan_next_day_day_trade")
    print("Family : gap_directional_trap")
    print("Phase  : phase_r6__deployable_variant_validation")
    print(f"Run date: {TODAY}")
    print(sep)

    # -- Load data ------------------------------------------------------------
    if not os.path.isfile(PHASE_R4_EVENTS_CSV):
        print(f"[ERROR] Input file not found:\n  {PHASE_R4_EVENTS_CSV}")
        sys.exit(1)

    all_df = pd.read_csv(PHASE_R4_EVENTS_CSV, low_memory=False)
    print(f"\nPhase_r4 events loaded : {len(all_df):,} rows")
    print(f"Date range             : {all_df['signal_date'].min()} to {all_df['signal_date'].max()}")
    print(f"Unique tickers         : {all_df['ticker'].nunique():,}")

    # -- Filter slices --------------------------------------------------------
    # Primary: grandchild_name == bearish__medium
    primary_df = all_df[all_df["grandchild_name"] == GC_PRIMARY].copy()

    # Secondary: bearish market regime AND (medium OR large) gap_size_band
    # (same filter as phase_r5 batch_2)
    bearish_mask = all_df["market_regime_label"] == "bearish"
    medium_mask  = all_df["gap_size_band"] == "medium"
    large_mask   = all_df["gap_size_band"] == "large"
    secondary_df = all_df[bearish_mask & (medium_mask | large_mask)].copy()

    print(f"\nSlice sizes:")
    print(f"  PRIMARY   {GC_PRIMARY}  n={len(primary_df):,}")
    print(f"  SECONDARY {GC_SECONDARY}  n={len(secondary_df):,}")

    # -- Derive signal prices -------------------------------------------------
    sl_all, sh_all, rd_all = _derive_signal_prices(all_df)
    sl_all.index  = all_df.index
    sh_all.index  = all_df.index
    rd_all.index  = all_df.index

    # -- Spot-check derivation ------------------------------------------------
    row0 = all_df.iloc[0]
    rd0  = row0["signal_day_close"] * row0["signal_day_range_pct"]
    sl0  = row0["signal_day_close"] - row0["signal_day_close_location"] * rd0
    cl0  = (row0["signal_day_close"] - sl0) / rd0 if rd0 > 0 else float("nan")
    print(f"\nDerivation spot check (row 0 | {row0['ticker']} {row0['signal_date']}):")
    print(f"  close_loc stored: {row0['signal_day_close_location']:.4f}  derived: {cl0:.4f}")

    # Mean risk for range-proxy stop on primary slice
    prd  = rd_all.reindex(primary_df.index)
    ep   = primary_df["signal_day_close"] * (1.0 + ENTRY_CLOSE_BUFFER)
    mean_risk_pct = round(float((0.75 * prd / ep * 100).mean()), 3)
    print(f"  CANDIDATE_1 mean risk% (range_proxy_75pct): {mean_risk_pct}%")

    # -- Run validation passes ------------------------------------------------

    print(f"\n{sep}")
    print("Running validation passes...")
    print(sep)

    print("[1/6] Building baseline variant summary...")
    summary_df = _build_variant_summary(primary_df, secondary_df, rd_all)

    print("[2/6] Building slippage sensitivity...")
    slippage_df = _build_slippage_sensitivity(primary_df, secondary_df, rd_all)

    print("[3/6] Building yearly summary...")
    yearly_df = _build_yearly_summary(primary_df, secondary_df, rd_all)

    print("[4/6] Building ticker concentration (CANDIDATE_1, primary)...")
    conc_df, total_pnl, n_valid_total, valid_df_conc = _build_ticker_concentration(primary_df, rd_all)

    print("[5/6] Building regime veto summary...")
    veto_df = _build_regime_veto_summary(primary_df, secondary_df, rd_all)

    print("[6/6] Building event rows output (CANDIDATE_1, primary, baseline)...")
    event_rows_df = _build_event_rows_output(primary_df, rd_all, sl_all, sh_all)

    # -- Write outputs --------------------------------------------------------

    fn_summary   = os.path.join(OUTPUT_DIR, f"variant_summary__gap_directional_trap__phase_r6__{TODAY}.csv")
    fn_slippage  = os.path.join(OUTPUT_DIR, f"variant_slippage_sensitivity__gap_directional_trap__phase_r6__{TODAY}.csv")
    fn_yearly    = os.path.join(OUTPUT_DIR, f"variant_yearly_summary__gap_directional_trap__phase_r6__{TODAY}.csv")
    fn_conc      = os.path.join(OUTPUT_DIR, f"ticker_concentration_summary__gap_directional_trap__phase_r6__{TODAY}.csv")
    fn_veto      = os.path.join(OUTPUT_DIR, f"regime_veto_summary__gap_directional_trap__phase_r6__{TODAY}.csv")
    fn_events    = os.path.join(OUTPUT_DIR, f"variant_event_rows__gap_directional_trap__phase_r6__{TODAY}.csv")

    summary_df.to_csv(fn_summary,  index=False)
    slippage_df.to_csv(fn_slippage, index=False)
    yearly_df.to_csv(fn_yearly,   index=False)
    conc_df.to_csv(fn_conc,     index=False)
    veto_df.to_csv(fn_veto,     index=False)
    event_rows_df.to_csv(fn_events,  index=False)

    # -- Console report -------------------------------------------------------

    print(f"\n{sep}")
    print("PHASE R6 RESULTS")
    print(sep)

    # A. Baseline
    print("\nA. BASELINE SUMMARY (no slippage, no veto)")
    print("-" * 70)
    for _, row in summary_df.iterrows():
        e   = row["expectancy_r"]
        e_s = f"+{e:.3f}R" if e is not None and e >= 0 else (f"{e:.3f}R" if e is not None else "N/A")
        sl  = row["slice"].split("__")
        sl_short = sl[-2] + "__" + sl[-1]
        print(f"  {row['label']} | {row['stop_id']:<25} | {row['target_id']:<15} | slice={sl_short}")
        print(f"    E={e_s:>9}  win={row['win_rate_pct']}%  loss={row['loss_rate_pct']}%  "
              f"time={row['time_exit_rate_pct']}%  n_valid={row['n_valid_triggered']:,}  "
              f"risk={row['mean_risk_pct']}%")

    # B. Slippage sensitivity (primary slice)
    print("\nB. SLIPPAGE SENSITIVITY (primary slice only)")
    print("-" * 70)
    slip_pri = slippage_df[slippage_df["slice"] == GC_PRIMARY]
    for cand in CANDIDATES:
        c_rows = slip_pri[slip_pri["candidate_id"] == cand["id"]]
        print(f"\n  {cand['label']} ({cand['stop_id']} + {cand['target_id']}):")
        for _, row in c_rows.iterrows():
            e   = row["expectancy_r"]
            e_s = f"+{e:.3f}R" if e is not None and e >= 0 else (f"{e:.3f}R" if e is not None else "N/A")
            print(f"    {row['slippage_id']:<15}: E={e_s:>9}  "
                  f"win={row['win_rate_pct']}%  loss={row['loss_rate_pct']}%  "
                  f"time={row['time_exit_rate_pct']}%  n_valid={row['n_valid_triggered']:,}")

    # C. Yearly stability (primary slice)
    print("\nC. YEARLY STABILITY (primary slice)")
    print("-" * 70)
    yr_pri = yearly_df[yearly_df["slice"] == GC_PRIMARY]
    for cand in CANDIDATES:
        c_rows = yr_pri[yr_pri["candidate_id"] == cand["id"]]
        print(f"\n  {cand['label']} ({cand['stop_id']} + {cand['target_id']}):")
        for _, row in c_rows.iterrows():
            e   = row["expectancy_r"]
            e_s = f"+{e:.3f}R" if e is not None and e >= 0 else (f"{e:.3f}R" if e is not None else "N/A")
            print(f"    {int(row['year'])}: E={e_s:>9}  win={row['win_rate_pct']}%  "
                  f"loss={row['loss_rate_pct']}%  time={row['time_exit_rate_pct']}%  "
                  f"n_valid={row['n_valid_triggered']:,}")

    # D. Ticker concentration
    print("\nD. TICKER CONCENTRATION (CANDIDATE_1, primary slice)")
    print("-" * 70)
    print(f"  Valid events (n): {n_valid_total:,}   Total pnl_r: {total_pnl:+.2f}R")
    print(f"  Unique tickers:  {len(conc_df):,}")
    print(f"  Top-15 tickers by pnl contribution:")
    top15 = conc_df.head(15)
    for _, row in top15.iterrows():
        pct  = row["pct_of_total_pnl"]
        cum  = row["cum_pct_pnl"]
        pct_s = f"{pct:+.1f}%" if pct is not None else "  N/A"
        cum_s = f"{cum:+.1f}%" if cum is not None else "  N/A"
        print(f"    #{int(row['rank_by_pnl']):3d} {row['ticker']:<8}  "
              f"n={int(row['n_events']):4d}  pnl_sum={row['pnl_r_sum']:>+7.2f}R  "
              f"mean={row['pnl_r_mean']:>+.4f}R  pct={pct_s}  cum={cum_s}")

    print(f"\n  Exclusion tests (remove top-N by pnl contribution):")
    for n in [5, 10, 20]:
        e_excl, n_rest = _excl_test(valid_df_conc, n)
        if e_excl is not None:
            e_s = f"+{e_excl:.4f}R" if e_excl >= 0 else f"{e_excl:.4f}R"
            print(f"    Excl top-{n:2d}: E={e_s:>10}  n_remaining={n_rest:,}")

    # E. Regime veto (primary slice)
    print("\nE. REGIME VETO SUMMARY (primary slice)")
    print("-" * 70)
    veto_pri = veto_df[veto_df["slice"] == GC_PRIMARY]
    for cand in CANDIDATES:
        c_rows = veto_pri[veto_pri["candidate_id"] == cand["id"]]
        print(f"\n  {cand['label']} ({cand['stop_id']} + {cand['target_id']}):")
        for _, row in c_rows.iterrows():
            e   = row["expectancy_r"]
            e22 = row["expectancy_2022"]
            e_s   = f"+{e:.3f}R"   if e is not None and e >= 0   else (f"{e:.3f}R"   if e is not None else "N/A")
            e22_s = f"+{e22:.3f}R" if e22 is not None and e22 >= 0 else (f"{e22:.3f}R" if e22 is not None else "N/A")
            print(f"    {row['veto_level']:<15}: E={e_s:>9}  n_eligible={row['n_eligible']:,}  "
                  f"pct={row['pct_eligible']:.0f}%  2022_E={e22_s:>9}  2022_n={row['n_valid_2022']}")

    # F. Secondary vs Primary
    print("\nF. SECONDARY vs PRIMARY (baseline)")
    print("-" * 70)
    for cand in CANDIDATES:
        p_row = summary_df[(summary_df["slice"] == GC_PRIMARY)   & (summary_df["candidate_id"] == cand["id"])].iloc[0]
        s_row = summary_df[(summary_df["slice"] == GC_SECONDARY) & (summary_df["candidate_id"] == cand["id"])].iloc[0]
        pe, se = p_row["expectancy_r"], s_row["expectancy_r"]
        pe_s = f"+{pe:.3f}R" if pe >= 0 else f"{pe:.3f}R"
        se_s = f"+{se:.3f}R" if se >= 0 else f"{se:.3f}R"
        print(f"  {cand['label']}: PRIMARY E={pe_s}  (n={int(p_row['n_valid_triggered']):,}) | "
              f"SECONDARY E={se_s}  (n={int(s_row['n_valid_triggered']):,})")

    # G. Output files
    print(f"\nG. OUTPUT FILES  ->  {os.path.relpath(OUTPUT_DIR)}")
    print("-" * 70)
    for fn in [fn_summary, fn_slippage, fn_yearly, fn_conc, fn_veto, fn_events]:
        print(f"  {os.path.basename(fn)}")

    print(f"\n{sep}")
    print("Phase r6 validation complete.")
    print(sep)


if __name__ == "__main__":
    main()
