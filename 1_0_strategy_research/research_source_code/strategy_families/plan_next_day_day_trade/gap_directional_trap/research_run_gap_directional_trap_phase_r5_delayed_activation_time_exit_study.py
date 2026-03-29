"""
research_run_gap_directional_trap_phase_r5_delayed_activation_time_exit_study.py

Track:   plan_next_day_day_trade
Family:  gap_directional_trap
Phase:   phase_r5 (execution template research)
Study:   delayed activation window + forced time exit grid study

=== STUDY PURPOSE ===
The baseline candidate_1_v1 template uses a buy-stop entry active from the open with
a MOC (market on close) exit. This study asks: can we improve expectancy and reduce
adverse open-to-fill exposure by (a) delaying the activation window start, and
(b) applying a forced time exit before close?

Research questions:
  1. Does delayed activation improve expectancy vs the MOC baseline?
  2. What is the optimal activation start window?
  3. Does an earlier forced exit improve results?
  4. What is the optimal time exit window?
  5. What combination produces the best practical and TOS-orderable result?
  6. Promotion recommendation: candidate_1_v2, new grandchild, or no promotion?

=== BASELINE VARIANT (candidate_1_v1) ===
  Entry:   signal_day_close * 1.002  (buy stop, day order, active from open)
  Stop:    fill_price - 0.75 * signal_day_range_dollar
  Target:  fill_price + 2.0 * risk_dollar  (2R fixed)
  Risk:    0.75 * signal_day_range_dollar
  Exit:    MOC (flat by close)
  Slice:   gap_up + close_location < 0.20 + bearish regime + gap_size_band in (medium, large)

=== DATA COVERAGE NOTE ===
Intraday 1m parquets cover ~267-298 tickers from approximately 2024-03-25 to 2025-12-31.
Events outside this window are simulated using daily-bar OHLCV only (daily-bar MOC proxy).
The intraday-covered subset is used for the full timing grid study.

=== METHODOLOGY NOTE ===
- For intraday-covered events: minute-bar simulation with exact fill/stop/target detection.
- Entry price = signal_day_close * 1.002 (buy stop trigger; fill proxied at entry_price).
- Stop and target computed from entry_price (fill proxy; consistent with phase_r6 methodology).
- For each (activation_start, cancel_time, exit_time) combo:
    * Buy stop is NOT active before activation_start.
    * If entry_price not hit between activation_start and cancel_time: cancelled.
    * After fill, monitor for stop, target, or forced exit at exit_time.
    * At MOC exit: use close of last available bar in session.
- Daily-bar baseline uses next_day OHLCV columns directly (no intraday data).
"""

import os
import sys
import datetime
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", "..", "..", ".."))

EVENT_ROWS_PATH = os.path.join(
    REPO_ROOT,
    "1_0_strategy_research",
    "research_outputs",
    "family_lineages",
    "plan_next_day_day_trade",
    "gap_directional_trap",
    "phase_r4_structural_validation",
    "grandchild_event_rows__gap_directional_trap__phase_r4__2026_03_27.csv",
)

INTRADAY_CACHE_DIR = os.path.join(
    REPO_ROOT,
    "1_0_strategy_research",
    "research_data_cache",
    "intraday_1m",
)

OUTPUT_DIR = os.path.join(
    REPO_ROOT,
    "1_0_strategy_research",
    "research_outputs",
    "family_lineages",
    "plan_next_day_day_trade",
    "gap_directional_trap",
    "phase_r5_execution_template_research",
)

TODAY = datetime.date.today().strftime("%Y_%m_%d")

# ---------------------------------------------------------------------------
# Production slice filter (MUST NOT CHANGE)
# ---------------------------------------------------------------------------
PROD_FILTER = {
    "gap_direction": "up",
    "signal_day_close_location_max": 0.20,
    "market_regime_label": "bearish",
    "gap_size_bands": ("medium", "large"),
}

# ---------------------------------------------------------------------------
# Timing parameter grid
# ---------------------------------------------------------------------------
MARKET_OPEN_MIN = 9 * 60 + 30    # 570  = 09:30
MARKET_CLOSE_MIN = 16 * 60       # 960  = 16:00

# Activation start times: 10:00 to 14:00 in 15-min steps (inclusive)
ACTIVATION_STARTS_MIN = [10 * 60 + 15 * k for k in range(17)]
# [600, 615, ..., 840]

# Cancel times: 10:30 to 15:00 in 15-min steps
CANCEL_TIMES_MIN = [
    10 * 60 + 30, 10 * 60 + 45,
    11 * 60, 11 * 60 + 15, 11 * 60 + 30, 11 * 60 + 45,
    12 * 60, 12 * 60 + 15, 12 * 60 + 30, 12 * 60 + 45,
    13 * 60, 13 * 60 + 15, 13 * 60 + 30,
    14 * 60, 14 * 60 + 30,
    15 * 60,
]
# [630, 645, 660, 675, 690, 705, 720, 735, 750, 765, 780, 795, 810, 840, 870, 900]

# Exit times: 10:30 to 15:30 in 15-min steps, then 15:55 and MOC (16:00)
EXIT_TIMES_MIN = [10 * 60 + 30 + 15 * k for k in range(22)] + [15 * 60 + 55, 16 * 60]
# [630, 645, ..., 945] + [955, 960]

# MOC sentinel
MOC_MIN = 16 * 60  # 960

# Candidate_1_v1 entry/stop/target parameters
ENTRY_MULT = 1.002
RISK_RANGE_MULT = 0.75   # risk = 0.75 * signal_day_range_dollar
TARGET_R_MULT = 2.0      # target = fill + 2R

# Slippage proxy for adjusted expectancy: applied to triggered trades
SLIPPAGE_ADJ_R = 0.10

# Skip intraday sessions with fewer than this many bars (likely early close / bad data)
MIN_SESSION_BARS = 200

# P&L clip bounds (in R units)
PNL_CLIP_LOW = -3.0
PNL_CLIP_HIGH = 6.0


# ---------------------------------------------------------------------------
# Utility: minute value to HH:MM string
# ---------------------------------------------------------------------------
def min_to_hhmm(m: int) -> str:
    if m == MOC_MIN:
        return "MOC"
    return f"{m // 60:02d}:{m % 60:02d}"


def variant_label(a_min: int, c_min: int, e_min: int) -> str:
    return f"a={min_to_hhmm(a_min)}_c={min_to_hhmm(c_min)}_e={min_to_hhmm(e_min)}"


# ---------------------------------------------------------------------------
# Daily-bar simulation (phase_r6 style)
# Uses daily OHLCV columns from event rows directly.
# ---------------------------------------------------------------------------
def simulate_daily_bar_moc(events_df: pd.DataFrame) -> pd.DataFrame:
    """
    Simulate candidate_1_v1 using daily OHLCV only.
    Returns a copy of events_df with columns: outcome, pnl_r appended.

    Logic:
      entry_price = signal_day_close * ENTRY_MULT
      risk_dollar = RISK_RANGE_MULT * signal_day_close * signal_day_range_pct
      stop_price  = entry_price - risk_dollar
      target_price= entry_price + TARGET_R_MULT * risk_dollar

      Fill assumed if next_day_high >= entry_price (day high reaches trigger).
      MOC exit = next_day_close.
      Win if target hit (next_day_high >= target) before stop (next_day_low <= stop).
      Loss if stop hit (next_day_low <= stop_price) before or same bar as target.
      MOC: if neither target nor stop hit, use next_day_close.

      For daily bars we use the standard approximation:
        - if both target and stop hit on same day -> treat as loss (conservative)
        - otherwise: if next_day_high >= target AND next_day_low > stop -> win
    """
    df = events_df.copy()

    df["signal_day_range_dollar"] = df["signal_day_close"] * df["signal_day_range_pct"]
    df["entry_price"] = df["signal_day_close"] * ENTRY_MULT
    df["risk_dollar"] = RISK_RANGE_MULT * df["signal_day_range_dollar"]
    df["stop_price"] = df["entry_price"] - df["risk_dollar"]
    df["target_price"] = df["entry_price"] + TARGET_R_MULT * df["risk_dollar"]

    # Events where entry is triggered (next_day_high >= entry_price)
    df["filled"] = df["next_day_high"] >= df["entry_price"]

    def classify_row(row):
        if not row["filled"]:
            return "cancelled", 0.0
        ep = row["entry_price"]
        sp = row["stop_price"]
        tp = row["target_price"]
        rk = row["risk_dollar"]
        if rk <= 0:
            return "bad_data", 0.0
        nh = row["next_day_high"]
        nl = row["next_day_low"]
        nc = row["next_day_close"]
        target_hit = nh >= tp
        stop_hit = nl <= sp
        if target_hit and not stop_hit:
            return "win", TARGET_R_MULT
        elif stop_hit:
            return "loss", -1.0
        else:
            pnl = np.clip((nc - ep) / rk, PNL_CLIP_LOW, PNL_CLIP_HIGH)
            return "time_exit_moc", float(pnl)

    results = df.apply(classify_row, axis=1)
    df["outcome"] = results.map(lambda x: x[0])
    df["pnl_r"] = results.map(lambda x: x[1])
    return df


def compute_summary_stats(df_sim: pd.DataFrame, label: str) -> dict:
    """Compute summary statistics for a simulated event set."""
    traded = df_sim[df_sim["outcome"] != "cancelled"]
    n_total = len(df_sim)
    n_traded = len(traded)
    n_cancelled = n_total - n_traded

    if n_traded == 0:
        return {
            "label": label,
            "n_total": n_total, "n_traded": 0, "n_cancelled": n_cancelled,
            "trigger_rate": 0.0, "n_win": 0, "n_loss": 0, "n_time_exit": 0,
            "win_rate": float("nan"), "loss_rate": float("nan"),
            "time_exit_rate": float("nan"),
            "expectancy_r": float("nan"), "mean_pnl_r": float("nan"),
            "median_pnl_r": float("nan"), "profit_factor": float("nan"),
            "max_single_loss_r": float("nan"), "avg_hold_bars": float("nan"),
            "target_hit_rate": float("nan"), "stop_hit_rate": float("nan"),
        }

    n_win = (traded["outcome"] == "win").sum()
    n_loss = (traded["outcome"] == "loss").sum()
    n_time_exit = traded["outcome"].isin(["time_exit_moc", "time_exit"]).sum()

    pnl = traded["pnl_r"]
    wins = pnl[traded["outcome"] == "win"]
    losses = pnl[traded["outcome"] == "loss"]
    sum_wins = wins.sum() if len(wins) > 0 else 0.0
    sum_losses = abs(losses.sum()) if len(losses) > 0 else 0.0
    pf = sum_wins / sum_losses if sum_losses > 0 else float("nan")

    hold_bars = traded["hold_bars"].mean() if "hold_bars" in traded.columns else float("nan")

    return {
        "label": label,
        "n_total": n_total,
        "n_traded": n_traded,
        "n_cancelled": n_cancelled,
        "trigger_rate": n_traded / n_total if n_total > 0 else 0.0,
        "n_win": int(n_win),
        "n_loss": int(n_loss),
        "n_time_exit": int(n_time_exit),
        "win_rate": n_win / n_traded,
        "loss_rate": n_loss / n_traded,
        "time_exit_rate": n_time_exit / n_traded,
        "expectancy_r": float(pnl.mean()),
        "mean_pnl_r": float(pnl.mean()),
        "median_pnl_r": float(pnl.median()),
        "profit_factor": float(pf),
        "max_single_loss_r": float(pnl.min()),
        "avg_hold_bars": float(hold_bars),
        "target_hit_rate": n_win / n_traded,
        "stop_hit_rate": n_loss / n_traded,
    }


# ---------------------------------------------------------------------------
# Intraday simulation core
# ---------------------------------------------------------------------------
def build_session_arrays(session_df: pd.DataFrame):
    """
    Given a single-day minute-bar DataFrame (index = DatetimeIndex, ET),
    return:
      bar_times_min : np.ndarray int32  (minute-of-day for each bar, e.g. 570..960)
      bar_open      : np.ndarray float64
      bar_high      : np.ndarray float64
      bar_low       : np.ndarray float64
      bar_close     : np.ndarray float64
      n_bars        : int
    """
    bar_times_min = (
        session_df.index.hour * 60 + session_df.index.minute
    ).to_numpy(dtype=np.int32)
    bar_open  = session_df["open"].to_numpy(dtype=np.float64)
    bar_high  = session_df["high"].to_numpy(dtype=np.float64)
    bar_low   = session_df["low"].to_numpy(dtype=np.float64)
    bar_close = session_df["close"].to_numpy(dtype=np.float64)
    return bar_times_min, bar_open, bar_high, bar_low, bar_close, len(bar_times_min)


def build_trigger_arrays(
    bar_high: np.ndarray,
    bar_low: np.ndarray,
    bar_close: np.ndarray,
    entry_price: float,
    stop_price: float,
    target_price: float,
    n_bars: int,
):
    """
    Build forward-scan trigger index arrays.

    trigger_from[j] = first bar index >= j where bar_high >= entry_price
                      (N_BARS if not found)
    stop_from[j]    = first bar index >= j where bar_low <= stop_price
                      (N_BARS if not found)
    target_from[j]  = first bar index >= j where bar_high >= target_price
                      (N_BARS if not found)

    These arrays allow O(1) lookup for any activation start index j.
    """
    NONE = n_bars  # sentinel for "not found"

    trigger_from = np.full(n_bars + 1, NONE, dtype=np.int32)
    stop_from    = np.full(n_bars + 1, NONE, dtype=np.int32)
    target_from  = np.full(n_bars + 1, NONE, dtype=np.int32)

    # Build from right to left for O(n) construction
    last_trigger = NONE
    last_stop    = NONE
    last_target  = NONE

    for i in range(n_bars - 1, -1, -1):
        if bar_high[i] >= entry_price:
            last_trigger = i
        if bar_low[i] <= stop_price:
            last_stop = i
        if bar_high[i] >= target_price:
            last_target = i
        trigger_from[i] = last_trigger
        stop_from[i]    = last_stop
        target_from[i]  = last_target

    return trigger_from, stop_from, target_from


def time_to_bar_idx(
    target_min: int,
    bar_times_min: np.ndarray,
    n_bars: int,
) -> int:
    """
    Return the first bar index whose bar_time_min >= target_min.
    Returns n_bars if target_min is beyond all bars in the session.
    """
    idx = int(np.searchsorted(bar_times_min, target_min, side="left"))
    return min(idx, n_bars)


def simulate_one_event_intraday(
    entry_price: float,
    stop_price: float,
    target_price: float,
    risk_dollar: float,
    bar_times_min: np.ndarray,
    bar_close: np.ndarray,
    trigger_from: np.ndarray,
    stop_from: np.ndarray,
    target_from: np.ndarray,
    n_bars: int,
    a_idx: int,    # activation start bar index
    c_idx: int,    # cancel bar index
    e_idx: int,    # exit bar index (may equal n_bars-1 for MOC)
    is_moc_exit: bool,
) -> tuple:
    """
    Simulate a single event for one (activation_start, cancel_time, exit_time) combo.

    Returns (outcome, pnl_r, hold_bars):
      outcome   : 'cancelled' | 'win' | 'loss' | 'time_exit'
      pnl_r     : float
      hold_bars : int (0 if cancelled)
    """
    NONE = n_bars

    # Find fill bar (first trigger >= activation_start and <= cancel_time)
    fill_bar = trigger_from[a_idx]

    if fill_bar == NONE or fill_bar > c_idx:
        return "cancelled", 0.0, 0

    if risk_dollar <= 0:
        return "bad_data", 0.0, 0

    # After fill, look for stop and target starting from fill_bar
    s_bar = stop_from[fill_bar]
    t_bar = target_from[fill_bar]

    # Determine exit bar index: whichever comes first among stop, target, forced exit
    # Exit bar index for forced time exit
    # e_idx is the bar index of the exit time bar

    # Outcome logic
    stop_before_exit   = (s_bar != NONE) and (s_bar <= e_idx)
    target_before_exit = (t_bar != NONE) and (t_bar <= e_idx)

    if target_before_exit and (not stop_before_exit or t_bar < s_bar):
        # Target hit before stop (and before exit)
        hold = t_bar - fill_bar
        return "win", TARGET_R_MULT, hold

    elif stop_before_exit:
        # Stop hit before target (or both hit same bar -> conservative loss)
        hold = s_bar - fill_bar
        return "loss", -1.0, hold

    else:
        # Neither hit by exit time: time exit
        if is_moc_exit:
            # Use last available bar close in session
            exit_close = bar_close[n_bars - 1]
        else:
            # Use close of the exit bar (or last bar before it)
            actual_e = min(e_idx, n_bars - 1)
            exit_close = bar_close[actual_e]

        pnl = np.clip(
            (exit_close - entry_price) / risk_dollar,
            PNL_CLIP_LOW,
            PNL_CLIP_HIGH,
        )
        hold = e_idx - fill_bar
        return "time_exit", float(pnl), hold


# ---------------------------------------------------------------------------
# Load and process all events, grouped by ticker
# ---------------------------------------------------------------------------
def load_production_slice(event_rows_path: str) -> pd.DataFrame:
    """Load event rows and apply production slice filter."""
    df = pd.read_csv(event_rows_path, low_memory=False)
    df["signal_date"] = pd.to_datetime(df["signal_date"]).dt.date
    df["next_date"]   = pd.to_datetime(df["next_date"]).dt.date

    # Production slice
    mask = (
        (df["gap_direction"] == PROD_FILTER["gap_direction"])
        & (df["signal_day_close_location"] < PROD_FILTER["signal_day_close_location_max"])
        & (df["market_regime_label"] == PROD_FILTER["market_regime_label"])
        & (df["gap_size_band"].isin(PROD_FILTER["gap_size_bands"]))
    )
    df = df[mask].copy().reset_index(drop=True)
    print(f"  Production slice loaded: {len(df):,} events, "
          f"{df['ticker'].nunique()} unique tickers")
    return df


def load_ticker_intraday(ticker: str) -> pd.DataFrame | None:
    """
    Load intraday parquet for one ticker.
    Returns DataFrame with DatetimeIndex (ET) or None on failure.
    """
    path = os.path.join(INTRADAY_CACHE_DIR, f"{ticker}.parquet")
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_parquet(path)
        if df.index.tz is None:
            df.index = df.index.tz_localize("America/New_York")
        else:
            df.index = df.index.tz_convert("America/New_York")
        df = df.sort_index()
        return df
    except Exception as e:
        print(f"    WARNING: failed to load {ticker}: {e}")
        return None


# ---------------------------------------------------------------------------
# Main intraday grid simulation
# ---------------------------------------------------------------------------
def run_intraday_grid_simulation(
    slice_df: pd.DataFrame,
    combos: list,
) -> tuple:
    """
    Run the full timing grid simulation.

    Parameters
    ----------
    slice_df : production slice DataFrame
    combos   : list of (a_min, c_min, e_min, is_moc) tuples

    Returns
    -------
    results_by_event : dict { event_idx -> list of (combo_idx, outcome, pnl_r, hold_bars) }
    covered_event_indices : list of int (event indices that had intraday data)
    """
    n_combos = len(combos)

    # Pre-compute per-event static fields
    slice_df = slice_df.copy()
    slice_df["signal_day_range_dollar"] = (
        slice_df["signal_day_close"] * slice_df["signal_day_range_pct"]
    )
    slice_df["entry_price"] = slice_df["signal_day_close"] * ENTRY_MULT
    slice_df["risk_dollar"] = RISK_RANGE_MULT * slice_df["signal_day_range_dollar"]
    slice_df["stop_price"]  = slice_df["entry_price"] - slice_df["risk_dollar"]
    slice_df["target_price"]= slice_df["entry_price"] + TARGET_R_MULT * slice_df["risk_dollar"]
    slice_df["year"]        = slice_df["signal_date"].apply(lambda d: d.year)

    # Group by ticker
    tickers = slice_df["ticker"].unique()
    n_tickers = len(tickers)

    # results_matrix[event_idx][combo_idx] = (outcome, pnl_r, hold_bars)
    # We store as lists to build later DataFrames efficiently
    # Shape: (n_covered_events, n_combos)
    covered_rows = []          # list of event row dicts (subset with intraday data)
    outcomes_matrix = []       # list (one per covered event) of list (one per combo)

    n_skipped_no_parquet = 0
    n_skipped_no_date    = 0
    n_skipped_short_sess = 0
    n_covered_events     = 0

    for t_idx, ticker in enumerate(tickers):
        if (t_idx + 1) % 25 == 0 or t_idx == 0:
            print(f"  Processing ticker {t_idx + 1}/{n_tickers}: {ticker} "
                  f"(covered events so far: {n_covered_events:,})")

        ticker_events = slice_df[slice_df["ticker"] == ticker]

        # Load parquet
        intra_df = load_ticker_intraday(ticker)
        if intra_df is None:
            n_skipped_no_parquet += len(ticker_events)
            continue

        # Group intraday df by date for fast lookup
        intra_by_date = {}
        for date_ts, session in intra_df.groupby(intra_df.index.date):
            intra_by_date[date_ts] = session

        for _, row in ticker_events.iterrows():
            next_date = row["next_date"]

            if next_date not in intra_by_date:
                n_skipped_no_date += 1
                continue

            session = intra_by_date[next_date]

            # Filter to market hours 9:30 to 16:00
            try:
                session = session.between_time("09:30", "16:00")
            except Exception:
                n_skipped_short_sess += 1
                continue

            n_bars = len(session)
            if n_bars < MIN_SESSION_BARS:
                n_skipped_short_sess += 1
                continue

            # Build arrays
            (bar_times_min, bar_open, bar_high, bar_low,
             bar_close, n_bars) = build_session_arrays(session)

            entry_price  = row["entry_price"]
            stop_price   = row["stop_price"]
            target_price = row["target_price"]
            risk_dollar  = row["risk_dollar"]

            if risk_dollar <= 0:
                continue

            # Build trigger arrays once per event
            trigger_from, stop_from, target_from = build_trigger_arrays(
                bar_high, bar_low, bar_close,
                entry_price, stop_price, target_price,
                n_bars,
            )

            # Run all combos for this event
            event_combo_results = []
            for a_min, c_min, e_min, is_moc in combos:
                a_idx = time_to_bar_idx(a_min, bar_times_min, n_bars)
                c_idx = time_to_bar_idx(c_min, bar_times_min, n_bars)

                if is_moc:
                    # Exit at last bar (MOC close)
                    e_idx = n_bars - 1
                else:
                    e_idx = time_to_bar_idx(e_min, bar_times_min, n_bars)
                    if e_idx >= n_bars:
                        e_idx = n_bars - 1

                outcome, pnl_r, hold_bars = simulate_one_event_intraday(
                    entry_price, stop_price, target_price, risk_dollar,
                    bar_times_min, bar_close,
                    trigger_from, stop_from, target_from,
                    n_bars, a_idx, c_idx, e_idx, is_moc,
                )
                event_combo_results.append((outcome, pnl_r, hold_bars))

            outcomes_matrix.append(event_combo_results)
            covered_rows.append({
                "ticker":      row["ticker"],
                "signal_date": row["signal_date"],
                "next_date":   row["next_date"],
                "year":        row["year"],
                "entry_price": entry_price,
                "risk_dollar": risk_dollar,
                "next_day_open":  row["next_day_open"],
                "next_day_high":  row["next_day_high"],
                "next_day_low":   row["next_day_low"],
                "next_day_close": row["next_day_close"],
            })
            n_covered_events += 1

    print(f"\n  Intraday coverage summary:")
    print(f"    Covered events:             {n_covered_events:,}")
    print(f"    Skipped (no parquet):       {n_skipped_no_parquet:,}")
    print(f"    Skipped (date not in data): {n_skipped_no_date:,}")
    print(f"    Skipped (short session):    {n_skipped_short_sess:,}")

    return covered_rows, outcomes_matrix, n_covered_events


# ---------------------------------------------------------------------------
# Aggregate combo results into summary rows
# ---------------------------------------------------------------------------
def aggregate_combo_results(
    covered_rows: list,
    outcomes_matrix: list,
    combos: list,
) -> pd.DataFrame:
    """
    Build the matrix of summary stats, one row per combo.
    """
    n_covered = len(covered_rows)
    n_combos  = len(combos)

    years = sorted(set(r["year"] for r in covered_rows))

    # Pre-index year membership for fast per-combo yearly breakdown
    year_indices = {yr: [] for yr in years}
    for i, row in enumerate(covered_rows):
        year_indices[row["year"]].append(i)

    records = []
    for ci, (a_min, c_min, e_min, is_moc) in enumerate(combos):
        outcomes = [outcomes_matrix[i][ci] for i in range(n_covered)]
        outcome_strs = [o[0] for o in outcomes]
        pnl_rs       = np.array([o[1] for o in outcomes], dtype=np.float64)
        hold_bars_arr= np.array([o[2] for o in outcomes], dtype=np.float64)

        mask_traded  = np.array([s not in ("cancelled", "bad_data") for s in outcome_strs])
        mask_win     = np.array([s == "win"        for s in outcome_strs])
        mask_loss    = np.array([s == "loss"       for s in outcome_strs])
        mask_te      = np.array([s == "time_exit"  for s in outcome_strs])

        n_traded   = int(mask_traded.sum())
        n_cancelled= n_covered - n_traded
        n_win      = int(mask_win.sum())
        n_loss     = int(mask_loss.sum())
        n_te       = int(mask_te.sum())

        if n_traded == 0:
            records.append({
                "activation_start": min_to_hhmm(a_min),
                "cancel_time":      min_to_hhmm(c_min),
                "exit_time":        "MOC" if is_moc else min_to_hhmm(e_min),
                "activation_start_min": a_min,
                "cancel_time_min":  c_min,
                "exit_time_min":    e_min,
                "is_moc_exit":      is_moc,
                "n_total":          n_covered,
                "n_traded":         0,
                "n_cancelled":      n_cancelled,
                "trigger_rate":     0.0,
                "n_win": 0, "n_loss": 0, "n_time_exit": 0,
                "win_rate": float("nan"), "loss_rate": float("nan"),
                "time_exit_rate": float("nan"),
                "expectancy_r": float("nan"), "mean_pnl_r": float("nan"),
                "median_pnl_r": float("nan"), "profit_factor": float("nan"),
                "max_single_loss_r": float("nan"), "avg_hold_bars": float("nan"),
                "target_hit_rate": float("nan"), "stop_hit_rate": float("nan"),
                "vs_baseline_expectancy_r": float("nan"),
                "slippage_adj_expectancy_r": float("nan"),
            })
            continue

        traded_pnl  = pnl_rs[mask_traded]
        traded_hold = hold_bars_arr[mask_traded]

        sum_wins   = pnl_rs[mask_win].sum()
        sum_losses = abs(pnl_rs[mask_loss].sum())
        pf = sum_wins / sum_losses if sum_losses > 0 else float("nan")

        expectancy = float(traded_pnl.mean())
        # Slippage adjustment: -SLIPPAGE_ADJ_R per triggered trade
        slippage_adj_exp = expectancy - SLIPPAGE_ADJ_R

        records.append({
            "activation_start": min_to_hhmm(a_min),
            "cancel_time":      min_to_hhmm(c_min),
            "exit_time":        "MOC" if is_moc else min_to_hhmm(e_min),
            "activation_start_min": a_min,
            "cancel_time_min":  c_min,
            "exit_time_min":    e_min,
            "is_moc_exit":      is_moc,
            "n_total":          n_covered,
            "n_traded":         n_traded,
            "n_cancelled":      n_cancelled,
            "trigger_rate":     n_traded / n_covered,
            "n_win":            n_win,
            "n_loss":           n_loss,
            "n_time_exit":      n_te,
            "win_rate":         n_win / n_traded,
            "loss_rate":        n_loss / n_traded,
            "time_exit_rate":   n_te / n_traded,
            "expectancy_r":     expectancy,
            "mean_pnl_r":       expectancy,
            "median_pnl_r":     float(np.median(traded_pnl)),
            "profit_factor":    float(pf),
            "max_single_loss_r":float(traded_pnl.min()),
            "avg_hold_bars":    float(traded_hold.mean()),
            "target_hit_rate":  n_win / n_traded,
            "stop_hit_rate":    n_loss / n_traded,
            "vs_baseline_expectancy_r": float("nan"),  # filled in later
            "slippage_adj_expectancy_r": slippage_adj_exp,
        })

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Yearly breakdown for top variants
# ---------------------------------------------------------------------------
def build_yearly_breakdown(
    covered_rows: list,
    outcomes_matrix: list,
    combos: list,
    top_variant_indices: list,
) -> pd.DataFrame:
    """Build yearly breakdown for the top N combo indices."""
    years = sorted(set(r["year"] for r in covered_rows))
    year_idx_map = {}
    for i, row in enumerate(covered_rows):
        yr = row["year"]
        if yr not in year_idx_map:
            year_idx_map[yr] = []
        year_idx_map[yr].append(i)

    records = []
    for ci in top_variant_indices:
        a_min, c_min, e_min, is_moc = combos[ci]
        vlabel = variant_label(a_min, c_min, e_min)

        for yr in years:
            yr_indices = year_idx_map.get(yr, [])
            if not yr_indices:
                continue

            outcomes  = [outcomes_matrix[i][ci] for i in yr_indices]
            out_strs  = [o[0] for o in outcomes]
            pnl_rs    = np.array([o[1] for o in outcomes], dtype=np.float64)

            mask_traded = np.array([s not in ("cancelled", "bad_data") for s in out_strs])
            mask_win    = np.array([s == "win"  for s in out_strs])
            mask_loss   = np.array([s == "loss" for s in out_strs])
            mask_te     = np.array([s == "time_exit" for s in out_strs])

            n_traded = int(mask_traded.sum())
            n_win    = int(mask_win.sum())
            n_te     = int(mask_te.sum())

            if n_traded == 0:
                records.append({
                    "activation_start": min_to_hhmm(a_min),
                    "cancel_time":      min_to_hhmm(c_min),
                    "exit_time":        "MOC" if is_moc else min_to_hhmm(e_min),
                    "variant_label":    vlabel,
                    "year":             yr,
                    "n_traded":         0,
                    "win_rate":         float("nan"),
                    "expectancy_r":     float("nan"),
                    "n_time_exit":      0,
                })
                continue

            traded_pnl = pnl_rs[mask_traded]
            records.append({
                "activation_start": min_to_hhmm(a_min),
                "cancel_time":      min_to_hhmm(c_min),
                "exit_time":        "MOC" if is_moc else min_to_hhmm(e_min),
                "variant_label":    vlabel,
                "year":             yr,
                "n_traded":         n_traded,
                "win_rate":         n_win / n_traded,
                "expectancy_r":     float(traded_pnl.mean()),
                "n_time_exit":      n_te,
            })

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Coverage report builder
# ---------------------------------------------------------------------------
def build_coverage_report(
    full_slice: pd.DataFrame,
    intraday_covered_df: pd.DataFrame,
    full_sim: pd.DataFrame,
    covered_sim: pd.DataFrame,
    intraday_moc_baseline_exp: float,
) -> pd.DataFrame:
    """Build the coverage comparison report."""
    def year_counts(df):
        counts = df["year"].value_counts().sort_index()
        return {f"year_{yr}": int(cnt) for yr, cnt in counts.items()}

    full_years    = year_counts(full_slice)
    covered_years = year_counts(intraday_covered_df)

    full_traded    = full_sim[full_sim["outcome"] != "cancelled"]
    covered_traded = covered_sim[covered_sim["outcome"] != "cancelled"]

    full_exp    = float(full_traded["pnl_r"].mean()) if len(full_traded) > 0 else float("nan")
    covered_exp = float(covered_traded["pnl_r"].mean()) if len(covered_traded) > 0 else float("nan")

    all_years = sorted(set(list(full_years.keys()) + list(covered_years.keys())))

    rows = []
    for cat, n, tickers, df, exp in [
        ("full_slice",               len(full_slice),
         full_slice["ticker"].nunique(), full_slice, full_exp),
        ("intraday_covered_subset",  len(intraday_covered_df),
         intraday_covered_df["ticker"].nunique(), intraday_covered_df, covered_exp),
    ]:
        dates = df["signal_date"]
        row = {
            "category": cat,
            "n_events": n,
            "n_unique_tickers": tickers,
            "date_start": str(dates.min()),
            "date_end":   str(dates.max()),
            "baseline_expectancy_r": round(exp, 4),
        }
        yc = year_counts(df)
        for yr_key in all_years:
            row[yr_key] = yc.get(yr_key, 0)
        rows.append(row)

    # Coverage pct row
    row_pct = {
        "category": "coverage_pct",
        "n_events":  round(len(intraday_covered_df) / len(full_slice) * 100, 1),
        "n_unique_tickers": round(
            intraday_covered_df["ticker"].nunique() / full_slice["ticker"].nunique() * 100, 1
        ),
        "date_start": "",
        "date_end":   "",
        "baseline_expectancy_r": "",
    }
    for yr_key in all_years:
        full_n = full_years.get(yr_key, 0)
        cov_n  = covered_years.get(yr_key, 0)
        row_pct[yr_key] = round(cov_n / full_n * 100, 1) if full_n > 0 else 0.0
    rows.append(row_pct)

    # Intraday MOC baseline row
    row_intra_moc = {
        "category": "intraday_subset_intraday_moc_baseline",
        "n_events":  len(intraday_covered_df),
        "n_unique_tickers": intraday_covered_df["ticker"].nunique(),
        "date_start": "",
        "date_end":   "",
        "baseline_expectancy_r": round(intraday_moc_baseline_exp, 4),
    }
    for yr_key in all_years:
        row_intra_moc[yr_key] = ""
    rows.append(row_intra_moc)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Baseline comparison builder
# ---------------------------------------------------------------------------
def build_baseline_comparison(
    matrix_df: pd.DataFrame,
    full_exp: float,
    covered_daily_exp: float,
    covered_intraday_moc_exp: float,
) -> pd.DataFrame:
    """
    Build baseline comparison rows:
      - fixed reference points
      - activation impact study (at cancel=EOD, exit=MOC, vary activation_start)
      - exit timing study (at activation=10:00, cancel=14:00, vary exit_time)
    """
    rows = []

    rows.append({
        "row_label":    "full_slice_daily_bar_moc",
        "n_events":     9865,
        "expectancy_r": round(full_exp, 4),
        "n_traded":     None,
        "trigger_rate": None,
        "win_rate":     None,
        "note":         "daily-bar simulation, full 9865-event slice",
    })
    rows.append({
        "row_label":    "intraday_subset_daily_bar_moc",
        "n_events":     None,
        "expectancy_r": round(covered_daily_exp, 4),
        "n_traded":     None,
        "trigger_rate": None,
        "win_rate":     None,
        "note":         "daily-bar simulation, intraday-covered subset",
    })
    rows.append({
        "row_label":    "intraday_subset_intraday_moc",
        "n_events":     None,
        "expectancy_r": round(covered_intraday_moc_exp, 4),
        "n_traded":     None,
        "trigger_rate": None,
        "win_rate":     None,
        "note":         "intraday sim, a=09:30, c=EOD, e=MOC (methodology baseline)",
    })

    # Activation impact study: cancel at last cancel time, exit=MOC, vary activation_start
    last_cancel = max(CANCEL_TIMES_MIN)
    act_rows = matrix_df[
        (matrix_df["cancel_time_min"] == last_cancel)
        & (matrix_df["is_moc_exit"] == True)
    ].sort_values("activation_start_min")
    for _, r in act_rows.iterrows():
        rows.append({
            "row_label":    f"activation_study__a={r['activation_start']}_c=EOD_e=MOC",
            "n_events":     int(r["n_total"]),
            "expectancy_r": round(r["expectancy_r"], 4),
            "n_traded":     int(r["n_traded"]),
            "trigger_rate": round(r["trigger_rate"], 4),
            "win_rate":     round(r["win_rate"], 4) if r["n_traded"] > 0 else None,
            "note":         "activation impact study row",
        })

    # Exit timing study: activation=10:00, cancel=14:00, vary exit_time
    act_600 = 10 * 60
    can_840 = 14 * 60
    exit_rows = matrix_df[
        (matrix_df["activation_start_min"] == act_600)
        & (matrix_df["cancel_time_min"] == can_840)
    ].sort_values("exit_time_min")
    for _, r in exit_rows.iterrows():
        rows.append({
            "row_label":    f"exit_study__a=10:00_c=14:00_e={r['exit_time']}",
            "n_events":     int(r["n_total"]),
            "expectancy_r": round(r["expectancy_r"], 4),
            "n_traded":     int(r["n_traded"]),
            "trigger_rate": round(r["trigger_rate"], 4),
            "win_rate":     round(r["win_rate"], 4) if r["n_traded"] > 0 else None,
            "note":         "exit timing study row",
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Finalist summary text report
# ---------------------------------------------------------------------------
def write_finalist_summary(
    output_path: str,
    full_slice: pd.DataFrame,
    covered_df: pd.DataFrame,
    full_exp: float,
    covered_daily_exp: float,
    covered_intraday_moc_exp: float,
    matrix_df: pd.DataFrame,
    top_variants_df: pd.DataFrame,
):
    """Write the human-readable finalist summary text file."""
    top5 = top_variants_df.head(5)

    lines = []
    lines.append("=" * 80)
    lines.append("FINALIST SUMMARY: gap_directional_trap — phase_r5 delayed activation "
                 "& time exit study")
    lines.append(f"Generated: {TODAY}")
    lines.append("=" * 80)
    lines.append("")

    # --- Data coverage ---
    lines.append("1. DATA COVERAGE")
    lines.append("-" * 40)
    lines.append(f"  Full production slice:         {len(full_slice):,} events, "
                 f"{full_slice['ticker'].nunique()} tickers, "
                 f"{full_slice['signal_date'].min()} to {full_slice['signal_date'].max()}")
    lines.append(f"  Intraday-covered subset:       {len(covered_df):,} events, "
                 f"{covered_df['ticker'].nunique()} tickers, "
                 f"{covered_df['signal_date'].min()} to {covered_df['signal_date'].max()}")
    coverage_pct = len(covered_df) / len(full_slice) * 100 if len(full_slice) > 0 else 0
    lines.append(f"  Coverage:                      {coverage_pct:.1f}% of events, "
                 f"{covered_df['ticker'].nunique() / full_slice['ticker'].nunique() * 100:.1f}% of tickers")
    lines.append("")

    # --- Baseline comparison ---
    lines.append("2. BASELINE COMPARISON (representativeness)")
    lines.append("-" * 40)
    lines.append(f"  Full slice daily-bar MOC expectancy:          {full_exp:+.4f}R")
    lines.append(f"  Intraday subset daily-bar MOC expectancy:     {covered_daily_exp:+.4f}R")
    lines.append(f"  Intraday subset intraday MOC expectancy:      {covered_intraday_moc_exp:+.4f}R")
    diff = covered_daily_exp - full_exp
    lines.append(f"  Subset vs full slice delta:                   {diff:+.4f}R")
    if abs(diff) < 0.05:
        rep_note = "Subset appears representative of full slice (delta < 0.05R)."
    elif abs(diff) < 0.10:
        rep_note = "Subset shows modest difference from full slice (delta 0.05-0.10R)."
    else:
        rep_note = ("WARNING: subset shows meaningful difference from full slice. "
                    "Interpret intraday results with caution.")
    lines.append(f"  Assessment: {rep_note}")
    lines.append("")

    # --- Top variants ---
    lines.append("3. TOP 5 PRACTICAL VARIANTS")
    lines.append("-" * 40)
    for rank, (_, row) in enumerate(top5.iterrows(), start=1):
        lines.append(f"  Rank {rank}: a={row['activation_start']}  c={row['cancel_time']}  "
                     f"e={row['exit_time']}")
        lines.append(f"    n_total={int(row['n_total'])}  n_traded={int(row['n_traded'])}  "
                     f"trigger_rate={row['trigger_rate']:.2%}")
        lines.append(f"    win_rate={row['win_rate']:.2%}  loss_rate={row['loss_rate']:.2%}  "
                     f"time_exit_rate={row['time_exit_rate']:.2%}")
        lines.append(f"    expectancy_r={row['expectancy_r']:+.4f}R  "
                     f"slippage_adj_expectancy_r={row['slippage_adj_expectancy_r']:+.4f}R")
        lines.append(f"    profit_factor={row['profit_factor']:.2f}  "
                     f"max_single_loss_r={row['max_single_loss_r']:+.3f}R  "
                     f"avg_hold_bars={row['avg_hold_bars']:.0f}")
        vs_baseline = row["vs_baseline_expectancy_r"]
        vs_str = f"{vs_baseline:+.4f}R" if not np.isnan(vs_baseline) else "n/a"
        lines.append(f"    vs_intraday_moc_baseline={vs_str}")
        lines.append("")
        lines.append(f"    TOS ORDER LOGIC:")
        lines.append(f"      - Buy Stop trigger:  signal_day_close * {ENTRY_MULT}")
        lines.append(f"      - Stop loss:         fill_price - {RISK_RANGE_MULT} * signal_day_range_dollar")
        lines.append(f"      - Target:            fill_price + {TARGET_R_MULT} * risk_dollar")
        lines.append(f"      - Order activation:  {row['activation_start']} ET")
        lines.append(f"      - Order cancel if not filled by: {row['cancel_time']} ET")
        lines.append(f"      - Forced time exit:  {row['exit_time']} ET (or MOC if MOC)")
        lines.append("")

    # --- Research questions ---
    lines.append("4. RESEARCH QUESTION ANSWERS")
    lines.append("-" * 40)

    valid_matrix = matrix_df[(matrix_df["n_traded"] > 10)].copy()
    best_exp = valid_matrix["expectancy_r"].max() if len(valid_matrix) > 0 else float("nan")
    moc_rows = valid_matrix[valid_matrix["is_moc_exit"] == True]
    best_moc_exp = moc_rows["expectancy_r"].max() if len(moc_rows) > 0 else float("nan")

    # Q1
    imp = best_exp - covered_intraday_moc_exp
    if imp > 0.02:
        q1_ans = (f"YES. Best combo achieves {best_exp:+.4f}R vs intraday MOC baseline "
                  f"{covered_intraday_moc_exp:+.4f}R (+{imp:.4f}R improvement).")
    elif imp > 0:
        q1_ans = (f"MARGINAL. Best combo {best_exp:+.4f}R vs MOC baseline "
                  f"{covered_intraday_moc_exp:+.4f}R. Small positive improvement.")
    else:
        q1_ans = (f"NO. Best combo {best_exp:+.4f}R does not exceed MOC baseline "
                  f"{covered_intraday_moc_exp:+.4f}R.")
    lines.append(f"  Q1 (Does delayed activation improve expectancy?):")
    lines.append(f"    {q1_ans}")
    lines.append("")

    # Q2: Best activation window
    if len(moc_rows) > 0:
        best_act_row = moc_rows.loc[moc_rows["expectancy_r"].idxmax()]
        q2_ans = (f"Best activation_start with MOC exit: {best_act_row['activation_start']} "
                  f"(cancel={best_act_row['cancel_time']}, expectancy={best_act_row['expectancy_r']:+.4f}R)")
    else:
        q2_ans = "Insufficient data."
    lines.append(f"  Q2 (Optimal activation window?):")
    lines.append(f"    {q2_ans}")
    lines.append("")

    # Q3: Does earlier exit improve?
    non_moc = valid_matrix[valid_matrix["is_moc_exit"] == False]
    best_non_moc_exp = non_moc["expectancy_r"].max() if len(non_moc) > 0 else float("nan")
    if not np.isnan(best_non_moc_exp) and best_non_moc_exp > covered_intraday_moc_exp:
        q3_ans = (f"YES. Best non-MOC exit achieves {best_non_moc_exp:+.4f}R vs "
                  f"MOC baseline {covered_intraday_moc_exp:+.4f}R.")
    else:
        q3_ans = (f"NO (or marginal). Best non-MOC exit {best_non_moc_exp:+.4f}R vs "
                  f"MOC baseline {covered_intraday_moc_exp:+.4f}R.")
    lines.append(f"  Q3 (Does earlier forced exit improve results?):")
    lines.append(f"    {q3_ans}")
    lines.append("")

    # Q4: Optimal time exit window
    if len(non_moc) > 0:
        best_te_row = non_moc.loc[non_moc["expectancy_r"].idxmax()]
        q4_ans = (f"Best non-MOC exit time: {best_te_row['exit_time']} "
                  f"(a={best_te_row['activation_start']}, c={best_te_row['cancel_time']}, "
                  f"expectancy={best_te_row['expectancy_r']:+.4f}R)")
    else:
        q4_ans = "Insufficient non-MOC results."
    lines.append(f"  Q4 (Optimal time exit window?):")
    lines.append(f"    {q4_ans}")
    lines.append("")

    # Q5: Best practical combination
    if len(top5) > 0:
        best_row = top5.iloc[0]
        q5_ans = (f"Best combo: a={best_row['activation_start']}, "
                  f"c={best_row['cancel_time']}, e={best_row['exit_time']} "
                  f"(expectancy={best_row['expectancy_r']:+.4f}R, "
                  f"slippage_adj={best_row['slippage_adj_expectancy_r']:+.4f}R, "
                  f"trigger_rate={best_row['trigger_rate']:.1%}, "
                  f"win_rate={best_row['win_rate']:.1%})")
    else:
        q5_ans = "No valid combos found."
    lines.append(f"  Q5 (Best practical combination?):")
    lines.append(f"    {q5_ans}")
    lines.append("")

    # Q6: Promotion recommendation
    lines.append(f"  Q6 (Promotion recommendation):")
    if len(top5) > 0:
        best_adj = top5.iloc[0]["slippage_adj_expectancy_r"]
        if best_adj > covered_intraday_moc_exp + 0.05:
            promo = ("PROMOTE as candidate_1_v2. Best delayed-activation + time-exit "
                     "combo meaningfully exceeds the MOC baseline after slippage adjustment. "
                     "Proceed to phase_r6 validation for this variant.")
        elif best_adj > covered_intraday_moc_exp:
            promo = ("CONDITIONAL PROMOTE. Marginal improvement after slippage adjustment. "
                     "Review yearly stability before promoting to candidate_1_v2. "
                     "If stable across years, proceed to phase_r6.")
        else:
            promo = ("NO PROMOTION. Delayed activation and/or time exit do not improve "
                     "slippage-adjusted expectancy over the MOC baseline. "
                     "Retain candidate_1_v1 as the primary variant. "
                     "Archive this study as negative evidence.")
    else:
        promo = "INSUFFICIENT DATA. Cannot make promotion recommendation."
    lines.append(f"    {promo}")
    lines.append("")

    lines.append("=" * 80)
    lines.append("END OF REPORT")
    lines.append("=" * 80)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n  Finalist summary written to: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 70)
    print("gap_directional_trap — phase_r5 delayed activation + time exit study")
    print(f"Run date: {TODAY}")
    print("=" * 70)

    # ------------------------------------------------------------------
    # 1. Load production slice
    # ------------------------------------------------------------------
    print("\n[Step 1] Loading production slice event rows...")
    if not os.path.exists(EVENT_ROWS_PATH):
        print(f"ERROR: event rows not found at:\n  {EVENT_ROWS_PATH}")
        sys.exit(1)

    full_slice = load_production_slice(EVENT_ROWS_PATH)
    full_slice["year"] = full_slice["signal_date"].apply(lambda d: d.year)

    # ------------------------------------------------------------------
    # 2. Daily-bar simulation on full slice (baseline reference)
    # ------------------------------------------------------------------
    print("\n[Step 2] Daily-bar simulation on full slice (9,865-event baseline)...")
    full_sim = simulate_daily_bar_moc(full_slice)
    full_traded = full_sim[full_sim["outcome"] != "cancelled"]
    full_exp = float(full_traded["pnl_r"].mean()) if len(full_traded) > 0 else float("nan")
    print(f"  Full slice daily-bar MOC expectancy: {full_exp:+.4f}R "
          f"(n_traded={len(full_traded):,}/{len(full_sim):,})")

    # ------------------------------------------------------------------
    # 3. Build timing grid combos
    # ------------------------------------------------------------------
    print("\n[Step 3] Building timing parameter grid...")
    combos = []
    for a_min in ACTIVATION_STARTS_MIN:
        for c_min in CANCEL_TIMES_MIN:
            if c_min <= a_min:
                continue  # cancel must be after activation start
            for e_min in EXIT_TIMES_MIN:
                is_moc = (e_min == MOC_MIN)
                combos.append((a_min, c_min, e_min, is_moc))

    # Also add the "open baseline" combo: a=9:30, c=15:00 (last cancel), e=MOC
    # This serves as the intraday methodology baseline (no delay)
    open_baseline = (MARKET_OPEN_MIN, max(CANCEL_TIMES_MIN), MOC_MIN, True)
    if open_baseline not in combos:
        combos.insert(0, open_baseline)

    print(f"  Total valid (activation, cancel, exit) combos: {len(combos):,}")

    # ------------------------------------------------------------------
    # 4. Run intraday grid simulation
    # ------------------------------------------------------------------
    print("\n[Step 4] Running intraday grid simulation...")
    print(f"  Loading parquets from: {INTRADAY_CACHE_DIR}")

    covered_rows, outcomes_matrix, n_covered = run_intraday_grid_simulation(
        full_slice, combos
    )

    if n_covered == 0:
        print("ERROR: No intraday-covered events found. Check parquet path.")
        sys.exit(1)

    # Build covered DataFrame for reporting
    covered_df = pd.DataFrame(covered_rows)
    covered_df["signal_date"] = pd.to_datetime(covered_df["signal_date"]).dt.date
    covered_df["next_date"]   = pd.to_datetime(covered_df["next_date"]).dt.date

    # ------------------------------------------------------------------
    # 5. Daily-bar simulation on intraday-covered subset
    # ------------------------------------------------------------------
    print("\n[Step 5] Daily-bar simulation on intraday-covered subset...")
    covered_for_daily = full_slice[
        full_slice.apply(
            lambda r: any(
                cr["ticker"] == r["ticker"] and cr["next_date"] == r["next_date"]
                for cr in covered_rows
            ),
            axis=1,
        )
    ] if False else None  # Avoid slow apply; use merge instead

    # Efficient merge approach
    covered_keys = pd.DataFrame(covered_rows)[["ticker", "next_date"]].copy()
    covered_keys["next_date"] = pd.to_datetime(covered_keys["next_date"]).dt.date
    covered_keys["_in_covered"] = True

    full_slice_copy = full_slice.copy()
    merged = full_slice_copy.merge(covered_keys, on=["ticker", "next_date"], how="left")
    covered_for_daily = merged[merged["_in_covered"] == True].drop(columns=["_in_covered"]).copy()
    covered_for_daily["year"] = covered_for_daily["signal_date"].apply(lambda d: d.year)

    covered_daily_sim = simulate_daily_bar_moc(covered_for_daily)
    covered_daily_traded = covered_daily_sim[covered_daily_sim["outcome"] != "cancelled"]
    covered_daily_exp = float(covered_daily_traded["pnl_r"].mean()) if len(covered_daily_traded) > 0 else float("nan")
    print(f"  Intraday subset daily-bar MOC expectancy: {covered_daily_exp:+.4f}R "
          f"(n_traded={len(covered_daily_traded):,}/{len(covered_for_daily):,})")

    # ------------------------------------------------------------------
    # 6. Identify intraday MOC baseline combo
    # ------------------------------------------------------------------
    print("\n[Step 6] Identifying intraday MOC baseline (a=09:30 equivalent)...")
    # Find the open_baseline combo index
    open_baseline_idx = None
    for ci, (a_min, c_min, e_min, is_moc) in enumerate(combos):
        if a_min == MARKET_OPEN_MIN and c_min == max(CANCEL_TIMES_MIN) and is_moc:
            open_baseline_idx = ci
            break

    if open_baseline_idx is None:
        # Fall back to first MOC combo with earliest activation
        for ci, (a_min, c_min, e_min, is_moc) in enumerate(combos):
            if is_moc:
                open_baseline_idx = ci
                break

    if open_baseline_idx is not None:
        # Compute expectancy for this combo from outcomes_matrix
        ob_outcomes = [outcomes_matrix[i][open_baseline_idx] for i in range(n_covered)]
        ob_pnl = np.array([o[1] for o in ob_outcomes if o[0] not in ("cancelled", "bad_data")])
        covered_intraday_moc_exp = float(ob_pnl.mean()) if len(ob_pnl) > 0 else float("nan")
    else:
        covered_intraday_moc_exp = covered_daily_exp

    print(f"  Intraday MOC baseline expectancy (a=09:30, c=15:00, e=MOC): "
          f"{covered_intraday_moc_exp:+.4f}R")

    # ------------------------------------------------------------------
    # 7. Aggregate combo results into matrix
    # ------------------------------------------------------------------
    print("\n[Step 7] Aggregating combo results into summary matrix...")
    matrix_df = aggregate_combo_results(covered_rows, outcomes_matrix, combos)

    # Fill vs_baseline_expectancy_r
    matrix_df["vs_baseline_expectancy_r"] = matrix_df["expectancy_r"] - covered_intraday_moc_exp

    print(f"  Matrix rows: {len(matrix_df):,}")
    valid_rows = matrix_df[matrix_df["n_traded"] > 0]
    if len(valid_rows) > 0:
        best_row = valid_rows.loc[valid_rows["expectancy_r"].idxmax()]
        print(f"  Best combo: a={best_row['activation_start']} c={best_row['cancel_time']} "
              f"e={best_row['exit_time']}  expectancy={best_row['expectancy_r']:+.4f}R")

    # ------------------------------------------------------------------
    # 8. Build top variants (top 50 by expectancy)
    # ------------------------------------------------------------------
    top_variants_df = (
        matrix_df[matrix_df["n_traded"] > 10]
        .sort_values("expectancy_r", ascending=False)
        .head(50)
        .reset_index(drop=True)
    )

    # ------------------------------------------------------------------
    # 9. Build yearly breakdown for top 20
    # ------------------------------------------------------------------
    print("\n[Step 8] Building yearly breakdown for top 20 variants...")
    top20_combos = top_variants_df.head(20)
    top20_indices = []
    for _, row in top20_combos.iterrows():
        for ci, (a_min, c_min, e_min, is_moc) in enumerate(combos):
            if (min_to_hhmm(a_min) == row["activation_start"]
                    and min_to_hhmm(c_min) == row["cancel_time"]
                    and (("MOC" if is_moc else min_to_hhmm(e_min)) == row["exit_time"])):
                top20_indices.append(ci)
                break

    yearly_df = build_yearly_breakdown(covered_rows, outcomes_matrix, combos, top20_indices)

    # ------------------------------------------------------------------
    # 10. Build baseline comparison
    # ------------------------------------------------------------------
    print("\n[Step 9] Building baseline comparison table...")
    baseline_comp_df = build_baseline_comparison(
        matrix_df, full_exp, covered_daily_exp, covered_intraday_moc_exp
    )

    # ------------------------------------------------------------------
    # 11. Build coverage report
    # ------------------------------------------------------------------
    print("\n[Step 10] Building coverage report...")
    coverage_df = build_coverage_report(
        full_slice, covered_df,
        full_sim, covered_daily_sim,
        covered_intraday_moc_exp,
    )

    # ------------------------------------------------------------------
    # 12. Save outputs
    # ------------------------------------------------------------------
    print("\n[Step 11] Saving outputs...")

    # Clean matrix for output (drop helper columns)
    output_matrix = matrix_df.drop(
        columns=["activation_start_min", "cancel_time_min", "exit_time_min", "is_moc_exit"],
        errors="ignore",
    )

    output_top = top_variants_df.drop(
        columns=["activation_start_min", "cancel_time_min", "exit_time_min", "is_moc_exit"],
        errors="ignore",
    )

    paths = {
        "coverage_report": os.path.join(
            OUTPUT_DIR,
            f"delayed_activation_coverage_report__gap_directional_trap__phase_r5__{TODAY}.csv"
        ),
        "matrix": os.path.join(
            OUTPUT_DIR,
            f"delayed_activation_matrix__gap_directional_trap__phase_r5__{TODAY}.csv"
        ),
        "top_variants": os.path.join(
            OUTPUT_DIR,
            f"delayed_activation_top_variants__gap_directional_trap__phase_r5__{TODAY}.csv"
        ),
        "yearly": os.path.join(
            OUTPUT_DIR,
            f"delayed_activation_yearly_breakdown__gap_directional_trap__phase_r5__{TODAY}.csv"
        ),
        "baseline_comp": os.path.join(
            OUTPUT_DIR,
            f"delayed_activation_baseline_comparison__gap_directional_trap__phase_r5__{TODAY}.csv"
        ),
        "finalist_txt": os.path.join(
            OUTPUT_DIR,
            f"delayed_activation_finalist_summary__gap_directional_trap__phase_r5__{TODAY}.txt"
        ),
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    coverage_df.to_csv(paths["coverage_report"], index=False)
    print(f"  Saved: {os.path.basename(paths['coverage_report'])}")

    output_matrix.to_csv(paths["matrix"], index=False)
    print(f"  Saved: {os.path.basename(paths['matrix'])} ({len(output_matrix):,} rows)")

    output_top.to_csv(paths["top_variants"], index=False)
    print(f"  Saved: {os.path.basename(paths['top_variants'])} ({len(output_top):,} rows)")

    if len(yearly_df) > 0:
        yearly_df.to_csv(paths["yearly"], index=False)
        print(f"  Saved: {os.path.basename(paths['yearly'])} ({len(yearly_df):,} rows)")
    else:
        print(f"  SKIPPED yearly breakdown (no data).")

    baseline_comp_df.to_csv(paths["baseline_comp"], index=False)
    print(f"  Saved: {os.path.basename(paths['baseline_comp'])}")

    # ------------------------------------------------------------------
    # 13. Write finalist summary
    # ------------------------------------------------------------------
    write_finalist_summary(
        paths["finalist_txt"],
        full_slice, covered_df,
        full_exp, covered_daily_exp, covered_intraday_moc_exp,
        matrix_df, top_variants_df,
    )

    # ------------------------------------------------------------------
    # 14. Console summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("TOP 10 VARIANTS BY EXPECTANCY_R")
    print("=" * 70)
    top10 = output_top.head(10) if len(output_top) >= 10 else output_top
    for rank, (_, row) in enumerate(top10.iterrows(), start=1):
        print(
            f"  #{rank:2d}  a={row['activation_start']}  c={row['cancel_time']}  "
            f"e={row['exit_time']:6s}  "
            f"exp={row['expectancy_r']:+.4f}R  "
            f"adj={row['slippage_adj_expectancy_r']:+.4f}R  "
            f"n_traded={int(row['n_traded']):4d}  "
            f"wr={row['win_rate']:.1%}  "
            f"trig={row['trigger_rate']:.1%}"
        )

    print("\n" + "=" * 70)
    print("PROMOTION RECOMMENDATION")
    print("=" * 70)
    if len(top_variants_df) > 0:
        best_adj = top_variants_df.iloc[0]["slippage_adj_expectancy_r"]
        if best_adj > covered_intraday_moc_exp + 0.05:
            rec = ("PROMOTE as candidate_1_v2 — delayed activation + time exit "
                   "meaningfully improves slippage-adjusted expectancy.")
        elif best_adj > covered_intraday_moc_exp:
            rec = ("CONDITIONAL PROMOTE — marginal improvement. Review yearly "
                   "stability before promoting.")
        else:
            rec = ("NO PROMOTION — delayed activation does not improve "
                   "slippage-adjusted expectancy over MOC baseline.")
    else:
        rec = "INSUFFICIENT DATA."
    print(f"  {rec}")
    print("=" * 70)
    print("\nDone.")


if __name__ == "__main__":
    main()
