"""
engineering_build_full_history_backtest__gap_directional_trap__candidate_1_v1.py

track:    plan_next_day_day_trade
family:   gap_directional_trap
variant:  gap_directional_trap__bearish_medium_large__candidate_1_v1
batch:    engineering_build_full_history_backtest_and_activation_study__gap_directional_trap__candidate_1_v1

Purpose:
  Comprehensive full-history backtest and activation study for candidate_1_v1.
  Uses the full repo-native daily cache (2021-03-26 to 2026-03-24).

  Produces two result sets, clearly separated:
    A. raw_module_backtest — all valid module signals per signal_date
    B. operator_portfolio_backtest — selected_top_3 operator portfolio

Critical precondition:
  This script uses ONLY the repo-native daily cache and the phase_r1 market
  context model. No external API calls required. Coverage verified upfront.

Frozen signal filter (all 4 conditions, from research handoff):
  1. gap_direction == gap_up
  2. close_location < 0.20
  3. market_regime_label == bearish
  4. gap_size_band in {medium, large}
     small:  abs(gap_pct) < 0.015
     medium: 0.015 <= abs(gap_pct) < 0.030
     large:  abs(gap_pct) >= 0.030

Frozen price formulas:
  entry_price  = signal_day_close * 1.002
  risk_dollar  = 0.75 * signal_day_range_dollar
  stop_price   = entry_price - risk_dollar
  target_price = entry_price + (2.0 * risk_dollar)

Outcome determination (daily-bar resolution only):
  entry_triggered:    next_day_high >= entry_price
  target_hit:         entry_triggered AND next_day_high >= target_price AND next_day_low > stop_price
  stop_hit:           entry_triggered AND next_day_low <= stop_price AND next_day_high < target_price
  sequence_ambiguous: entry_triggered AND both stop and target within daily range
                      (conservative: realised_r = -1.0, flagged)
  moc_exit:           entry_triggered AND neither stop nor target hit
  no_fill:            next_day_high < entry_price
  no_next_day_data:   next-day OHLCV not in cache

Frozen selection layer (operator top_3 portfolio):
  Hard filters: US common stock (CS+us), price 20-100, ADV20 >= $2M
  Score: 30% ADV + 30% close_location + 25% risk_pct + 15% RVOL - flag penalties
  One bucket leader per occupied price bucket (20-30, 30-50, 50-70, 70-100)
  Top 3 bucket leaders selected for delivery

Usage:
  python engineering_build_full_history_backtest__gap_directional_trap__candidate_1_v1.py

Output directory:
  2_0_agent_engineering/engineering_runtime_outputs/plan_next_day_day_trade/
    gap_directional_trap__candidate_1_v1/

Do NOT:
  - modify frozen signal filter thresholds
  - modify frozen entry/stop/target formulas
  - add broker, Telegram, or scheduling code
  - change the selection layer thresholds
  - redesign the strategy
"""

import math
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

# ═══════════════════════════════════════════════════════════════════════════════
# PATH CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════
# File location: 2_0_agent_engineering/
# parents[0] = 2_0_agent_engineering/
# parents[1] = ai_trading_assistant/ (REPO_ROOT)
REPO_ROOT = Path(__file__).resolve().parents[1]

DAILY_CACHE_DIR = REPO_ROOT / "1_0_strategy_research" / "research_data_cache" / "daily"
UNIVERSE_FILE = (
    REPO_ROOT / "0_1_shared_master_universe" / "shared_symbol_lists"
    / "shared_master_symbol_list_us_common_stocks.csv"
)
UNIVERSE_METADATA_FILE = (
    REPO_ROOT / "0_1_shared_master_universe" / "shared_metadata"
    / "shared_master_metadata_us_common_stocks.csv"
)
MARKET_CONTEXT_FILE = (
    REPO_ROOT / "1_0_strategy_research" / "research_outputs" / "family_lineages"
    / "plan_next_day_day_trade" / "phase_r1_market_context_model"
    / "market_context_model_plan_next_day_day_trade.csv"
)
OUTPUT_DIR = (
    REPO_ROOT / "2_0_agent_engineering" / "engineering_runtime_outputs"
    / "plan_next_day_day_trade" / "gap_directional_trap__candidate_1_v1"
)

DATE_RANGE_TAG = "2021_03_26__2026_03_24"
VARIANT_ID = "gap_directional_trap__bearish_medium_large__candidate_1_v1"
FAMILY_NAME = "gap_directional_trap"

# ═══════════════════════════════════════════════════════════════════════════════
# FROZEN SIGNAL FILTER THRESHOLDS — DO NOT MODIFY
# Source: variant_spec__gap_directional_trap__candidate_1_v1__phase_r8__2026_03_27.yaml
# ═══════════════════════════════════════════════════════════════════════════════
CLOSE_LOCATION_THRESHOLD = 0.20
GAP_SMALL_MAX            = 0.015
GAP_MEDIUM_MAX           = 0.030
ENTRY_CLOSE_BUFFER       = 0.002
RANGE_PROXY_FACTOR       = 0.75
TARGET_R_MULTIPLE        = 2.0

# ═══════════════════════════════════════════════════════════════════════════════
# FROZEN SELECTION LAYER THRESHOLDS — DO NOT MODIFY
# Source: engineering_selection_layer__gap_directional_trap__candidate_1_v1.py
# ═══════════════════════════════════════════════════════════════════════════════
PRICE_MIN            = 20.0
PRICE_MAX            = 100.0
ADV_DOLLAR_MIN       = 2_000_000.0
ADV_LOOKBACK_DAYS    = 20
PRICE_BUCKETS = [
    ("20_to_30",   20.0,  30.0),
    ("30_to_50",   30.0,  50.0),
    ("50_to_70",   50.0,  70.0),
    ("70_to_100",  70.0,  100.001),
]
W_ADV            = 0.30
W_CLOSE_LOC      = 0.30
W_RISK_PCT       = 0.25
W_RVOL           = 0.15
_ADV_LOG_FLOOR   = math.log10(ADV_DOLLAR_MIN)
_ADV_LOG_CEIL    = math.log10(100_000_000.0)
RISK_PCT_CEILING = 0.10
RVOL_CAP         = 2.0
PENALTY_VERY_WIDE_STOP  = 0.15
PENALTY_STOP_BELOW_ZERO = 0.25
MAX_DELIVERY     = 3


# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def load_universe_tickers() -> List[str]:
    df = pd.read_csv(UNIVERSE_FILE)
    return df["ticker"].str.strip().str.upper().tolist()


def load_us_cs_set() -> set:
    """All US common stocks from shared metadata (type='CS', locale='us')."""
    df = pd.read_csv(UNIVERSE_METADATA_FILE, dtype={"ticker": str})
    confirmed = df[(df["type"] == "CS") & (df["locale"] == "us")]["ticker"]
    return set(confirmed.str.strip().str.upper())


def load_market_context() -> pd.DataFrame:
    """Load phase_r1 market context model; index = date string (YYYY-MM-DD)."""
    df = pd.read_csv(MARKET_CONTEXT_FILE)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df.set_index("date")


def load_all_daily_parquets(tickers: List[str]) -> Dict[str, pd.DataFrame]:
    """
    Load all daily parquets into memory.
    Returns dict: ticker -> DataFrame with:
      - index: sorted YYYY-MM-DD string dates
      - columns: open, high, low, close, volume, adv20
    adv20 = 20-session rolling mean of (close * volume), shifted 1 to avoid look-ahead.
    """
    ticker_data: Dict[str, pd.DataFrame] = {}
    total = len(tickers)
    loaded = 0
    missing = 0

    print(f"[data] Loading {total} daily parquets...")
    for i, ticker in enumerate(tickers):
        if i % 500 == 0:
            print(f"  {i}/{total} ({i/total:.0%}) loaded={loaded} missing={missing}")
        path = DAILY_CACHE_DIR / f"{ticker}.parquet"
        if not path.exists():
            missing += 1
            continue
        try:
            df = pd.read_parquet(path)
            # Normalize tz-aware timestamps to plain date strings
            df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
            # Drop duplicates, sort ascending
            df = df[~df.index.duplicated(keep="last")].sort_index()
            # Precompute dollar volume and ADV20 (shifted 1 session forward = no look-ahead)
            df["dollar_vol"] = df["close"] * df["volume"]
            df["adv20"] = df["dollar_vol"].rolling(ADV_LOOKBACK_DAYS, min_periods=ADV_LOOKBACK_DAYS).mean().shift(1)
            ticker_data[ticker] = df
            loaded += 1
        except Exception as e:
            missing += 1

    print(f"  {total}/{total} complete: loaded={loaded} missing={missing}")
    return ticker_data


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def assign_gap_size_band(gap_pct: float) -> str:
    abs_gap = abs(gap_pct)
    if abs_gap < GAP_SMALL_MAX:
        return "small"
    elif abs_gap < GAP_MEDIUM_MAX:
        return "medium"
    else:
        return "large"


def find_next_trading_date(ticker: str, signal_date: str,
                           ticker_data: Dict[str, pd.DataFrame]) -> Optional[str]:
    """Return the date string of the next available session after signal_date for this ticker."""
    df = ticker_data.get(ticker)
    if df is None:
        return None
    dates = df.index.tolist()
    if signal_date not in dates:
        return None
    idx = dates.index(signal_date)
    if idx + 1 >= len(dates):
        return None
    return dates[idx + 1]


def get_previous_trading_date_in_ticker(ticker: str, signal_date: str,
                                         ticker_data: Dict[str, pd.DataFrame]) -> Optional[str]:
    """Return the date string of the session immediately before signal_date for this ticker."""
    df = ticker_data.get(ticker)
    if df is None:
        return None
    dates = df.index.tolist()
    if signal_date not in dates:
        return None
    idx = dates.index(signal_date)
    if idx == 0:
        return None
    return dates[idx - 1]


def assign_price_bucket(close: float) -> Optional[str]:
    for label, low, high in PRICE_BUCKETS:
        if low <= close < high:
            return label
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# SIGNAL GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

def scan_signals_for_date(signal_date: str, context_row: pd.Series,
                          ticker_data: Dict[str, pd.DataFrame]) -> List[dict]:
    """
    Scan all tickers for the 4 frozen signal conditions on signal_date.
    Returns list of raw signal dicts (before outcome determination).
    """
    market_regime_label = context_row["market_regime_label"]
    # Condition 3 check (global): regime must be bearish
    if market_regime_label != "bearish":
        return []

    signals = []
    for ticker, df in ticker_data.items():
        if signal_date not in df.index:
            continue
        dates = df.index.tolist()
        sig_idx = dates.index(signal_date)
        if sig_idx == 0:
            continue  # no previous trading session

        sig_row = df.loc[signal_date]
        prev_row = df.iloc[sig_idx - 1]

        # Compute gap
        signal_day_open = float(sig_row["open"])
        prev_close      = float(prev_row["close"])
        if prev_close <= 0:
            continue

        gap_pct       = (signal_day_open - prev_close) / prev_close
        gap_direction = "gap_up" if gap_pct > 0 else "gap_down"

        # Condition 1: gap_up
        if gap_direction != "gap_up":
            continue

        # Condition 2: close_location < 0.20
        signal_day_high  = float(sig_row["high"])
        signal_day_low   = float(sig_row["low"])
        signal_day_close = float(sig_row["close"])
        signal_day_range = signal_day_high - signal_day_low

        if signal_day_range <= 0:
            continue

        close_location = (signal_day_close - signal_day_low) / signal_day_range
        if close_location >= CLOSE_LOCATION_THRESHOLD:
            continue

        # Condition 4: gap_size_band in {medium, large}
        gap_size_band = assign_gap_size_band(gap_pct)
        if gap_size_band not in ("medium", "large"):
            continue

        # Compute frozen entry / stop / target
        entry_price  = signal_day_close * (1.0 + ENTRY_CLOSE_BUFFER)
        risk_dollar  = RANGE_PROXY_FACTOR * signal_day_range
        stop_price   = entry_price - risk_dollar
        target_price = entry_price + (TARGET_R_MULTIPLE * risk_dollar)
        risk_pct     = risk_dollar / entry_price

        # Compute ADV20 (precomputed, no look-ahead)
        adv20_val = df.loc[signal_date, "adv20"] if "adv20" in df.columns else float("nan")
        adv20_val = None if (adv20_val is None or (isinstance(adv20_val, float) and math.isnan(adv20_val))) else float(adv20_val)

        # Compute signal-day RVOL
        sig_dollar_vol = float(sig_row["close"]) * float(sig_row["volume"])
        rvol = (sig_dollar_vol / adv20_val) if adv20_val and adv20_val > 0 else None

        # Warning flags
        warning_flags = []
        if risk_pct > 0.10:
            warning_flags.append(f"very_wide_stop_{risk_pct:.1%}")
        if signal_day_close < 5.0:
            warning_flags.append("low_priced_stock_lt_5")
        if stop_price <= 0:
            warning_flags.append("stop_price_below_zero")

        signals.append({
            "ticker":                   ticker,
            "signal_date":              signal_date,
            "variant_id":               VARIANT_ID,
            "family_name":              FAMILY_NAME,
            "market_regime_label":      market_regime_label,
            "gap_direction":            gap_direction,
            "gap_pct":                  round(gap_pct, 6),
            "gap_size_band":            gap_size_band,
            "close_location":           round(close_location, 4),
            "signal_day_open":          round(signal_day_open, 4),
            "signal_day_high":          round(signal_day_high, 4),
            "signal_day_low":           round(signal_day_low, 4),
            "signal_day_close":         round(signal_day_close, 4),
            "signal_day_range_dollar":  round(signal_day_range, 4),
            "entry_price":              round(entry_price, 4),
            "stop_price":               round(stop_price, 4),
            "target_price":             round(target_price, 4),
            "risk_dollar":              round(risk_dollar, 4),
            "risk_pct":                 round(risk_pct, 6),
            "avg_daily_dollar_volume":  round(adv20_val, 2) if adv20_val is not None else None,
            "relative_volume":          round(rvol, 4) if rvol is not None else None,
            "warning_flags":            "; ".join(warning_flags),
        })

    return signals


# ═══════════════════════════════════════════════════════════════════════════════
# OUTCOME DETERMINATION
# ═══════════════════════════════════════════════════════════════════════════════

def determine_outcome(signal: dict, next_day_row: Optional[pd.Series]) -> dict:
    """
    Determine trade outcome from next-day daily OHLCV.
    Returns a dict with outcome fields merged into the signal dict.
    """
    entry_price  = signal["entry_price"]
    stop_price   = signal["stop_price"]
    target_price = signal["target_price"]
    risk_dollar  = signal["risk_dollar"]

    if next_day_row is None:
        return {
            "trade_date":                       None,
            "next_day_open":                    None,
            "next_day_high":                    None,
            "next_day_low":                     None,
            "next_day_close":                   None,
            "open_above_entry":                 None,
            "entry_triggered":                  False,
            "stop_hit":                         False,
            "target_hit":                       False,
            "moc_exit":                         False,
            "no_fill":                          False,
            "sequence_ambiguous_daily_bar":     False,
            "outcome_label":                    "no_next_day_data",
            "realized_exit_price":              None,
            "realized_pnl_per_share":           None,
            "realized_pnl_pct":                 None,
            "realized_r":                       None,
            "mfe_pct_daily_bar_approx":         None,
            "mae_pct_daily_bar_approx":         None,
        }

    nd_open  = float(next_day_row["open"])
    nd_high  = float(next_day_row["high"])
    nd_low   = float(next_day_row["low"])
    nd_close = float(next_day_row["close"])

    open_above_entry = (nd_open >= entry_price)

    # Entry triggered?
    if nd_high < entry_price:
        return {
            "trade_date":                       next_day_row.name,
            "next_day_open":                    nd_open,
            "next_day_high":                    nd_high,
            "next_day_low":                     nd_low,
            "next_day_close":                   nd_close,
            "open_above_entry":                 open_above_entry,
            "entry_triggered":                  False,
            "stop_hit":                         False,
            "target_hit":                       False,
            "moc_exit":                         False,
            "no_fill":                          True,
            "sequence_ambiguous_daily_bar":     False,
            "outcome_label":                    "no_fill",
            "realized_exit_price":              None,
            "realized_pnl_per_share":           None,
            "realized_pnl_pct":                 None,
            "realized_r":                       None,
            "mfe_pct_daily_bar_approx":         None,
            "mae_pct_daily_bar_approx":         None,
        }

    # Entry triggered — determine bracket outcome
    fill_price = entry_price  # assumed fill = entry_price (consistent with research methodology)

    stop_reachable   = (nd_low <= stop_price)
    target_reachable = (nd_high >= target_price)

    # Daily-bar approximations for MFE / MAE
    mfe_pct = (nd_high - fill_price) / fill_price
    mae_pct = (fill_price - nd_low)  / fill_price

    if target_reachable and stop_reachable:
        # Both brackets within same daily bar — sequence unknown from daily data
        realized_exit_price    = stop_price   # conservative assumption
        realized_pnl_per_share = realized_exit_price - fill_price
        realized_pnl_pct       = realized_pnl_per_share / fill_price
        realized_r             = realized_pnl_per_share / risk_dollar  # ≈ -1.0R
        return {
            "trade_date":                       next_day_row.name,
            "next_day_open":                    nd_open,
            "next_day_high":                    nd_high,
            "next_day_low":                     nd_low,
            "next_day_close":                   nd_close,
            "open_above_entry":                 open_above_entry,
            "entry_triggered":                  True,
            "stop_hit":                         False,
            "target_hit":                       False,
            "moc_exit":                         False,
            "no_fill":                          False,
            "sequence_ambiguous_daily_bar":     True,
            "outcome_label":                    "sequence_ambiguous_daily_bar",
            "realized_exit_price":              round(realized_exit_price, 4),
            "realized_pnl_per_share":           round(realized_pnl_per_share, 4),
            "realized_pnl_pct":                 round(realized_pnl_pct, 6),
            "realized_r":                       round(realized_r, 4),
            "mfe_pct_daily_bar_approx":         round(mfe_pct, 6),
            "mae_pct_daily_bar_approx":         round(mae_pct, 6),
        }

    elif target_reachable:
        realized_exit_price    = target_price
        realized_pnl_per_share = realized_exit_price - fill_price
        realized_pnl_pct       = realized_pnl_per_share / fill_price
        realized_r             = realized_pnl_per_share / risk_dollar  # ≈ +2.0R
        return {
            "trade_date":                       next_day_row.name,
            "next_day_open":                    nd_open,
            "next_day_high":                    nd_high,
            "next_day_low":                     nd_low,
            "next_day_close":                   nd_close,
            "open_above_entry":                 open_above_entry,
            "entry_triggered":                  True,
            "stop_hit":                         False,
            "target_hit":                       True,
            "moc_exit":                         False,
            "no_fill":                          False,
            "sequence_ambiguous_daily_bar":     False,
            "outcome_label":                    "target_hit",
            "realized_exit_price":              round(realized_exit_price, 4),
            "realized_pnl_per_share":           round(realized_pnl_per_share, 4),
            "realized_pnl_pct":                 round(realized_pnl_pct, 6),
            "realized_r":                       round(realized_r, 4),
            "mfe_pct_daily_bar_approx":         round(mfe_pct, 6),
            "mae_pct_daily_bar_approx":         round(mae_pct, 6),
        }

    elif stop_reachable:
        realized_exit_price    = stop_price
        realized_pnl_per_share = realized_exit_price - fill_price
        realized_pnl_pct       = realized_pnl_per_share / fill_price
        realized_r             = realized_pnl_per_share / risk_dollar  # ≈ -1.0R
        return {
            "trade_date":                       next_day_row.name,
            "next_day_open":                    nd_open,
            "next_day_high":                    nd_high,
            "next_day_low":                     nd_low,
            "next_day_close":                   nd_close,
            "open_above_entry":                 open_above_entry,
            "entry_triggered":                  True,
            "stop_hit":                         True,
            "target_hit":                       False,
            "moc_exit":                         False,
            "no_fill":                          False,
            "sequence_ambiguous_daily_bar":     False,
            "outcome_label":                    "stop_hit",
            "realized_exit_price":              round(realized_exit_price, 4),
            "realized_pnl_per_share":           round(realized_pnl_per_share, 4),
            "realized_pnl_pct":                 round(realized_pnl_pct, 6),
            "realized_r":                       round(realized_r, 4),
            "mfe_pct_daily_bar_approx":         round(mfe_pct, 6),
            "mae_pct_daily_bar_approx":         round(mae_pct, 6),
        }

    else:
        # MOC exit
        realized_exit_price    = nd_close
        realized_pnl_per_share = realized_exit_price - fill_price
        realized_pnl_pct       = realized_pnl_per_share / fill_price
        realized_r             = realized_pnl_per_share / risk_dollar
        outcome_label = "moc_win" if realized_pnl_per_share > 0 else "moc_loss"
        return {
            "trade_date":                       next_day_row.name,
            "next_day_open":                    nd_open,
            "next_day_high":                    nd_high,
            "next_day_low":                     nd_low,
            "next_day_close":                   nd_close,
            "open_above_entry":                 open_above_entry,
            "entry_triggered":                  True,
            "stop_hit":                         False,
            "target_hit":                       False,
            "moc_exit":                         True,
            "no_fill":                          False,
            "sequence_ambiguous_daily_bar":     False,
            "outcome_label":                    outcome_label,
            "realized_exit_price":              round(realized_exit_price, 4),
            "realized_pnl_per_share":           round(realized_pnl_per_share, 4),
            "realized_pnl_pct":                 round(realized_pnl_pct, 6),
            "realized_r":                       round(realized_r, 4),
            "mfe_pct_daily_bar_approx":         round(mfe_pct, 6),
            "mae_pct_daily_bar_approx":         round(mae_pct, 6),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# SELECTION LAYER (frozen replica for backtest)
# ═══════════════════════════════════════════════════════════════════════════════

def _score_adv(adv: float) -> float:
    if adv <= 0:
        return 0.0
    raw = (math.log10(adv) - _ADV_LOG_FLOOR) / (_ADV_LOG_CEIL - _ADV_LOG_FLOOR)
    return max(0.0, min(1.0, raw))


def _score_close_location(cl: float) -> float:
    return max(0.0, min(1.0, (0.20 - cl) / 0.20))


def _score_risk_pct(risk_pct: float) -> float:
    return max(0.0, 1.0 - (risk_pct / RISK_PCT_CEILING))


def _score_rvol(rvol: float) -> float:
    return min(rvol / RVOL_CAP, 1.0)


def _flag_penalty(warning_flags: str) -> float:
    if not warning_flags:
        return 0.0
    penalty = 0.0
    if "very_wide_stop" in warning_flags:
        penalty += PENALTY_VERY_WIDE_STOP
    if "stop_price_below_zero" in warning_flags:
        penalty += PENALTY_STOP_BELOW_ZERO
    return penalty


def apply_selection_layer(raw_signals: List[dict], us_cs_set: set) -> List[dict]:
    """
    Apply the frozen selection layer to raw_signals for one signal_date.
    Returns list of up to MAX_DELIVERY selected signals (with selection scoring fields added).
    Also returns all candidates after hard filters (for ranked_signal_pack).
    """
    candidates = []

    for sig in raw_signals:
        ticker = sig["ticker"]
        close  = sig["signal_day_close"]

        # Hard filter 1: US common stock
        if ticker not in us_cs_set:
            continue

        # Hard filter 2: price 20-100
        if not (PRICE_MIN <= close <= PRICE_MAX):
            continue

        # Hard filter 3: ADV20 >= $2M
        adv = sig.get("avg_daily_dollar_volume")
        if adv is None or adv < ADV_DOLLAR_MIN:
            continue

        rvol = sig.get("relative_volume") or 0.0

        # Score
        s_adv     = _score_adv(adv)
        s_cl      = _score_close_location(sig["close_location"])
        s_risk    = _score_risk_pct(sig["risk_pct"])
        s_rvol    = _score_rvol(rvol)
        penalty   = _flag_penalty(sig["warning_flags"])
        score     = (W_ADV * s_adv + W_CLOSE_LOC * s_cl + W_RISK_PCT * s_risk + W_RVOL * s_rvol) - penalty

        bucket = assign_price_bucket(close)

        candidates.append({
            **sig,
            "price_bucket_operator": bucket,
            "adv_dollar_score":      round(s_adv,   4),
            "close_location_score":  round(s_cl,    4),
            "risk_pct_score":        round(s_risk,  4),
            "rvol_score":            round(s_rvol,  4),
            "flag_penalty":          round(penalty, 4),
            "selection_score":       round(score,   4),
            "selected_for_delivery": False,
            "selection_rank_overall": None,
        })

    if not candidates:
        return []

    # Sort by selection_score descending
    candidates.sort(key=lambda x: x["selection_score"], reverse=True)

    # Assign overall rank
    for rank, cand in enumerate(candidates, start=1):
        cand["selection_rank_overall"] = rank

    # One bucket leader per occupied bucket
    bucket_leaders: List[dict] = []
    occupied: set = set()
    for cand in candidates:
        bkt = cand["price_bucket_operator"]
        if bkt and bkt not in occupied:
            bucket_leaders.append(cand)
            occupied.add(bkt)

    # Top MAX_DELIVERY bucket leaders
    bucket_leaders.sort(key=lambda x: x["selection_score"], reverse=True)
    selected = bucket_leaders[:MAX_DELIVERY]
    selected_tickers = {s["ticker"] for s in selected}

    for cand in candidates:
        if cand["ticker"] in selected_tickers:
            cand["selected_for_delivery"] = True

    return selected


# ═══════════════════════════════════════════════════════════════════════════════
# FULL HISTORY BACKTEST LOOP
# ═══════════════════════════════════════════════════════════════════════════════

def run_backtest(
    ticker_data: Dict[str, pd.DataFrame],
    context_df: pd.DataFrame,
    us_cs_set: set,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Main backtest loop over all bearish, non-warmup_na dates.
    Returns:
      raw_trades_df   — one row per raw module signal
      selected_trades_df — one row per selected_top_3 signal
    """
    # Filter to usable signal dates: non-warmup_na bearish days only
    usable_dates = context_df[
        (context_df["market_regime_label"] == "bearish")
    ].index.tolist()

    print(f"\n[backtest] Signal dates to process: {len(usable_dates)} (bearish, non-warmup_na)")

    raw_trades: List[dict]      = []
    selected_trades: List[dict] = []

    for i, signal_date in enumerate(sorted(usable_dates)):
        if i % 50 == 0:
            print(f"  [{i}/{len(usable_dates)}] processing {signal_date} ...")

        context_row = context_df.loc[signal_date]

        # Generate raw signals
        raw_signals = scan_signals_for_date(signal_date, context_row, ticker_data)

        if not raw_signals:
            continue

        # Determine outcomes for raw signals
        for sig in raw_signals:
            ticker        = sig["ticker"]
            next_date_str = find_next_trading_date(ticker, signal_date, ticker_data)
            next_day_row  = None
            if next_date_str is not None:
                df = ticker_data.get(ticker)
                if df is not None and next_date_str in df.index:
                    next_day_row = df.loc[next_date_str]

            outcome = determine_outcome(sig, next_day_row)

            # Merge context fields into trade record
            raw_trade = {
                **sig,
                **outcome,
                "raw_or_selected":        "raw",
                "year":                   signal_date[:4],
                "year_month":             signal_date[:7],
                "spy_realized_vol_20d":   context_row.get("spy_realized_vol_20d"),
                "spy_above_sma20":        context_row.get("spy_above_sma20"),
                "spy_above_sma50":        context_row.get("spy_above_sma50"),
                "spy_above_sma200":       context_row.get("spy_above_sma200"),
                "spy_return_5d":          context_row.get("spy_return_5d"),
                "spy_return_20d":         context_row.get("spy_return_20d"),
                "spy_return_60d":         context_row.get("spy_return_60d"),
                "spy_range_expansion":    context_row.get("spy_range_expansion"),
            }
            raw_trades.append(raw_trade)

        # Apply selection layer
        selected_signals = apply_selection_layer(raw_signals, us_cs_set)

        for sel_sig in selected_signals:
            ticker        = sel_sig["ticker"]
            next_date_str = find_next_trading_date(ticker, signal_date, ticker_data)
            next_day_row  = None
            if next_date_str is not None:
                df = ticker_data.get(ticker)
                if df is not None and next_date_str in df.index:
                    next_day_row = df.loc[next_date_str]

            outcome = determine_outcome(sel_sig, next_day_row)

            sel_trade = {
                **sel_sig,
                **outcome,
                "raw_or_selected":        "selected",
                "year":                   signal_date[:4],
                "year_month":             signal_date[:7],
                "spy_realized_vol_20d":   context_row.get("spy_realized_vol_20d"),
                "spy_above_sma20":        context_row.get("spy_above_sma20"),
                "spy_above_sma50":        context_row.get("spy_above_sma50"),
                "spy_above_sma200":       context_row.get("spy_above_sma200"),
                "spy_return_5d":          context_row.get("spy_return_5d"),
                "spy_return_20d":         context_row.get("spy_return_20d"),
                "spy_return_60d":         context_row.get("spy_return_60d"),
                "spy_range_expansion":    context_row.get("spy_range_expansion"),
            }
            selected_trades.append(sel_trade)

    print(f"[backtest] Done. raw_trades={len(raw_trades)}, selected_trades={len(selected_trades)}")

    raw_df      = pd.DataFrame(raw_trades)
    selected_df = pd.DataFrame(selected_trades)
    return raw_df, selected_df


# ═══════════════════════════════════════════════════════════════════════════════
# STATISTICS COMPUTATION
# ═══════════════════════════════════════════════════════════════════════════════

def compute_trade_stats(df: pd.DataFrame, label: str = "") -> dict:
    """Compute comprehensive per-trade statistics from a trades DataFrame."""
    if df.empty:
        return {"label": label, "total_signals": 0}

    total_signals     = len(df)
    triggered         = df[df["entry_triggered"] == True]
    no_fill_df        = df[df["outcome_label"] == "no_fill"]
    no_next_data_df   = df[df["outcome_label"] == "no_next_day_data"]

    n_triggered       = len(triggered)
    n_no_fill         = len(no_fill_df)
    n_no_next_data    = len(no_next_data_df)
    n_target_hit      = int(triggered["target_hit"].sum()) if "target_hit" in triggered.columns else 0
    n_stop_hit        = int(triggered["stop_hit"].sum())   if "stop_hit"   in triggered.columns else 0
    n_moc_exit        = int(triggered["moc_exit"].sum())   if "moc_exit"   in triggered.columns else 0
    n_ambiguous       = int((triggered["outcome_label"] == "sequence_ambiguous_daily_bar").sum())
    n_moc_win         = int((triggered["outcome_label"] == "moc_win").sum())
    n_moc_loss        = int((triggered["outcome_label"] == "moc_loss").sum())

    # Triggered R values (including ambiguous — tagged conservatively as -1R)
    r_series = triggered["realized_r"].dropna()
    n_r_valid = len(r_series)

    if n_r_valid > 0:
        expectancy_r   = float(r_series.mean())
        median_r       = float(r_series.median())
        cumulative_r   = float(r_series.sum())
        std_r          = float(r_series.std()) if n_r_valid > 1 else 0.0
        n_positive_r   = int((r_series > 0).sum())
        n_negative_r   = int((r_series < 0).sum())
        win_rate        = n_positive_r / n_r_valid
        loss_rate       = n_negative_r / n_r_valid
        best_trade_r    = float(r_series.max())
        worst_trade_r   = float(r_series.min())

        # Profit factor
        gross_wins   = r_series[r_series > 0].sum()
        gross_losses = abs(r_series[r_series < 0].sum())
        profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else float("inf")

        # MAE / MFE
        mae_series = triggered["mae_pct_daily_bar_approx"].dropna()
        mfe_series = triggered["mfe_pct_daily_bar_approx"].dropna()
        avg_mae = float(mae_series.mean()) if len(mae_series) > 0 else None
        avg_mfe = float(mfe_series.mean()) if len(mfe_series) > 0 else None

        # PnL pct
        pnl_series = triggered["realized_pnl_pct"].dropna()
        avg_pnl_pct    = float(pnl_series.mean())   if len(pnl_series) > 0 else None
        median_pnl_pct = float(pnl_series.median()) if len(pnl_series) > 0 else None

        # Streak analysis
        outcomes_bin = (r_series > 0).astype(int).tolist()
        max_win_streak  = _max_streak(outcomes_bin, 1)
        max_loss_streak = _max_streak(outcomes_bin, 0)
    else:
        expectancy_r = median_r = cumulative_r = std_r = 0.0
        n_positive_r = n_negative_r = 0
        win_rate = loss_rate = 0.0
        best_trade_r = worst_trade_r = 0.0
        profit_factor = 0.0
        avg_mae = avg_mfe = avg_pnl_pct = median_pnl_pct = None
        max_win_streak = max_loss_streak = 0

    no_fill_rate = n_no_fill / total_signals if total_signals > 0 else 0.0
    trigger_rate = n_triggered / (total_signals - n_no_next_data) if (total_signals - n_no_next_data) > 0 else 0.0

    return {
        "label":                  label,
        "total_signals":          total_signals,
        "n_triggered":            n_triggered,
        "n_no_fill":              n_no_fill,
        "n_no_next_day_data":     n_no_next_data,
        "trigger_rate_pct":       round(trigger_rate * 100, 1),
        "no_fill_rate_pct":       round(no_fill_rate * 100, 1),
        "n_target_hit":           n_target_hit,
        "n_stop_hit":             n_stop_hit,
        "n_moc_win":              n_moc_win,
        "n_moc_loss":             n_moc_loss,
        "n_ambiguous":            n_ambiguous,
        "target_hit_rate_pct":    round(n_target_hit / n_triggered * 100, 1) if n_triggered > 0 else 0.0,
        "stop_hit_rate_pct":      round(n_stop_hit   / n_triggered * 100, 1) if n_triggered > 0 else 0.0,
        "moc_exit_rate_pct":      round((n_moc_win + n_moc_loss) / n_triggered * 100, 1) if n_triggered > 0 else 0.0,
        "moc_win_rate_pct":       round(n_moc_win  / n_triggered * 100, 1) if n_triggered > 0 else 0.0,
        "moc_loss_rate_pct":      round(n_moc_loss / n_triggered * 100, 1) if n_triggered > 0 else 0.0,
        "n_valid_r":              n_r_valid,
        "expectancy_r":           round(expectancy_r, 4),
        "median_r":               round(median_r, 4),
        "cumulative_r":           round(cumulative_r, 2),
        "std_r":                  round(std_r, 4),
        "win_rate_pct":           round(win_rate * 100, 1),
        "loss_rate_pct":          round(loss_rate * 100, 1),
        "best_trade_r":           round(best_trade_r, 4),
        "worst_trade_r":          round(worst_trade_r, 4),
        "profit_factor":          round(profit_factor, 3),
        "avg_pnl_pct":            round(avg_pnl_pct * 100, 2) if avg_pnl_pct is not None else None,
        "median_pnl_pct":         round(median_pnl_pct * 100, 2) if median_pnl_pct is not None else None,
        "avg_mae_pct":            round(avg_mae * 100, 2) if avg_mae is not None else None,
        "avg_mfe_pct":            round(avg_mfe * 100, 2) if avg_mfe is not None else None,
        "max_win_streak":         max_win_streak,
        "max_loss_streak":        max_loss_streak,
    }


def _max_streak(seq: list, val: int) -> int:
    """Return maximum consecutive run of val in seq."""
    max_s = cur_s = 0
    for x in seq:
        if x == val:
            cur_s += 1
            max_s = max(max_s, cur_s)
        else:
            cur_s = 0
    return max_s


def compute_yearly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per-year summary: signals, triggered, expectancy, win rate, etc."""
    if df.empty:
        return pd.DataFrame()

    rows = []
    for year in sorted(df["year"].unique()):
        sub = df[df["year"] == year]
        stats = compute_trade_stats(sub, label=year)
        rows.append(stats)
    return pd.DataFrame(rows)


def compute_monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per year-month summary."""
    if df.empty:
        return pd.DataFrame()
    rows = []
    for ym in sorted(df["year_month"].unique()):
        sub = df[df["year_month"] == ym]
        stats = compute_trade_stats(sub, label=ym)
        rows.append({
            "year_month": ym,
            "total_signals": stats["total_signals"],
            "n_triggered": stats["n_triggered"],
            "expectancy_r": stats["expectancy_r"],
            "win_rate_pct": stats["win_rate_pct"],
            "n_target_hit": stats["n_target_hit"],
            "n_stop_hit": stats["n_stop_hit"],
            "n_moc_win": stats["n_moc_win"],
            "n_moc_loss": stats["n_moc_loss"],
            "cumulative_r": stats["cumulative_r"],
        })
    return pd.DataFrame(rows)


def compute_outcome_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Outcome type distribution."""
    if df.empty:
        return pd.DataFrame()
    counts = df["outcome_label"].value_counts().reset_index()
    counts.columns = ["outcome_label", "count"]
    counts["pct_of_all_signals"] = (counts["count"] / len(df) * 100).round(1)
    triggered = df[df["entry_triggered"] == True]
    n_triggered = len(triggered)
    outcome_r = (
        triggered.groupby("outcome_label")["realized_r"]
        .agg(["mean", "median", "sum", "count"])
        .reset_index()
        .rename(columns={"mean": "avg_r", "median": "median_r", "sum": "total_r", "count": "triggered_count"})
    )
    result = counts.merge(outcome_r, on="outcome_label", how="left")
    result["pct_of_triggered"] = (result["triggered_count"] / n_triggered * 100).round(1) if n_triggered > 0 else 0.0
    return result.sort_values("count", ascending=False)


def compute_ticker_concentration(df: pd.DataFrame, top_n: int = 30) -> pd.DataFrame:
    """Ticker-level contribution to total realized R."""
    triggered = df[df["entry_triggered"] == True].copy()
    if triggered.empty:
        return pd.DataFrame()

    total_r = triggered["realized_r"].dropna().sum()

    ticker_stats = (
        triggered.groupby("ticker")["realized_r"]
        .agg(["sum", "mean", "count"])
        .reset_index()
        .rename(columns={"sum": "total_r", "mean": "avg_r", "count": "n_triggered"})
        .sort_values("total_r", ascending=False)
        .reset_index(drop=True)
    )
    ticker_stats["pct_of_total_r"] = (ticker_stats["total_r"] / total_r * 100).round(2) if total_r != 0 else 0.0
    ticker_stats["cumulative_pct_r"] = ticker_stats["pct_of_total_r"].cumsum().round(2)
    return ticker_stats.head(top_n)


def compute_portfolio_r_series(df: pd.DataFrame) -> pd.Series:
    """
    For selected_top_3: compute per-trade cumulative R series.
    Treats each triggered trade as 1 risk unit (equal position sizing).
    Series index = sequential trade number, values = cumulative R.
    """
    triggered = df[df["entry_triggered"] == True].copy()
    if triggered.empty:
        return pd.Series(dtype=float)
    r_vals = triggered["realized_r"].dropna().reset_index(drop=True)
    return r_vals.cumsum()


def compute_daily_portfolio_r(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute daily portfolio R for the selected_top_3 portfolio.
    Each day: mean(realized_r) for triggered trades on that day.
    Returns DataFrame with columns: signal_date, n_triggered, sum_r, mean_r.
    """
    triggered = df[(df["entry_triggered"] == True) & df["realized_r"].notna()].copy()
    if triggered.empty:
        return pd.DataFrame(columns=["signal_date", "n_triggered", "sum_r", "mean_r"])
    daily = (
        triggered.groupby("signal_date")["realized_r"]
        .agg(["sum", "mean", "count"])
        .reset_index()
        .rename(columns={"sum": "sum_r", "mean": "mean_r", "count": "n_triggered"})
        .sort_values("signal_date")
    )
    daily["cumulative_r"] = daily["sum_r"].cumsum()
    return daily


def compute_drawdown(daily_portfolio_df: pd.DataFrame) -> dict:
    """Compute drawdown metrics from daily portfolio R series."""
    if daily_portfolio_df.empty:
        return {}

    cum_r    = daily_portfolio_df["cumulative_r"].values
    running_max = np.maximum.accumulate(cum_r)
    drawdown    = cum_r - running_max

    max_dd      = float(drawdown.min())
    dates       = daily_portfolio_df["signal_date"].values

    # Find max drawdown period
    end_idx   = int(np.argmin(drawdown))
    start_idx = int(np.argmax(cum_r[:end_idx + 1])) if end_idx > 0 else 0

    # Drawdown periods (sequences where equity < peak)
    in_drawdown = drawdown < 0
    transitions = np.diff(in_drawdown.astype(int), prepend=0, append=0)
    dd_starts   = np.where(transitions == 1)[0]
    dd_ends     = np.where(transitions == -1)[0]
    dd_durations = []
    for s, e in zip(dd_starts, dd_ends):
        dd_durations.append(e - s)

    avg_dd_length = float(np.mean(dd_durations)) if dd_durations else 0.0
    max_dd_length = int(max(dd_durations)) if dd_durations else 0

    return {
        "max_drawdown_r":              round(max_dd, 4),
        "max_drawdown_start_date":     str(dates[start_idx]) if start_idx < len(dates) else None,
        "max_drawdown_end_date":       str(dates[end_idx])   if end_idx   < len(dates) else None,
        "max_drawdown_length_trading_days": max_dd_length,
        "avg_drawdown_length_trading_days": round(avg_dd_length, 1),
        "n_drawdown_periods":          len(dd_durations),
        "final_cumulative_r":          round(float(cum_r[-1]), 4),
        "peak_cumulative_r":           round(float(running_max.max()), 4),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ACTIVATION STUDY
# ═══════════════════════════════════════════════════════════════════════════════

def run_activation_study(df: pd.DataFrame, context_df: pd.DataFrame) -> dict:
    """
    Study whether simple activation rules can improve module performance.
    Operates on triggered selected trades only (for meaningful portfolio context).

    Dimensions tested:
      1. SPY realized vol 20d buckets (low / medium / high)
      2. SPY MA position (above sma200 vs below sma200)
      3. SPY 60d return magnitude (extreme bear vs moderate bear)
      4. SPY monthly return bucket (spy_return_20d)
      5. Signal count per day (low / medium / high signal days)
      6. Year (for temporal patterns)
    """
    triggered = df[(df["entry_triggered"] == True) & df["realized_r"].notna()].copy()

    if triggered.empty:
        return {"note": "no triggered trades available for activation study"}

    results = {}

    # ── Dimension 1: SPY realized vol 20d ──────────────────────────────────────
    vol_col = "spy_realized_vol_20d"
    if vol_col in triggered.columns:
        vol_series = triggered[vol_col].dropna()
        if len(vol_series) > 0:
            q33 = float(vol_series.quantile(0.33))
            q67 = float(vol_series.quantile(0.67))
            def vol_bucket(v):
                if pd.isna(v): return "unknown"
                if v < q33:    return "low_vol"
                elif v < q67:  return "medium_vol"
                else:          return "high_vol"
            triggered["vol_bucket"] = triggered[vol_col].apply(vol_bucket)
            vol_stats = []
            for bucket in ["low_vol", "medium_vol", "high_vol"]:
                sub = triggered[triggered["vol_bucket"] == bucket]
                if len(sub) >= 5:
                    vol_stats.append({
                        "bucket": bucket,
                        "n_trades": len(sub),
                        "expectancy_r": round(sub["realized_r"].mean(), 4),
                        "vol_q33_threshold": round(q33, 4),
                        "vol_q67_threshold": round(q67, 4),
                    })
            results["vol_regime"] = {
                "description": "Performance by SPY realized_vol_20d bucket",
                "q33_threshold": round(q33, 4),
                "q67_threshold": round(q67, 4),
                "buckets": vol_stats,
            }

    # ── Dimension 2: SPY above / below SMA200 ──────────────────────────────────
    sma200_col = "spy_above_sma200"
    if sma200_col in triggered.columns:
        sma_stats = []
        for val, label in [(0, "spy_below_sma200"), (1, "spy_above_sma200")]:
            sub = triggered[triggered[sma200_col] == val]
            if len(sub) >= 5:
                sma_stats.append({
                    "bucket": label,
                    "n_trades": len(sub),
                    "expectancy_r": round(sub["realized_r"].mean(), 4),
                })
        results["spy_sma200_position"] = {
            "description": "Performance when bearish regime AND SPY above vs below SMA200",
            "note": "All these trades are already in bearish regime; this sub-conditions further",
            "buckets": sma_stats,
        }

    # ── Dimension 3: SPY 60d return magnitude ──────────────────────────────────
    ret60_col = "spy_return_60d"
    if ret60_col in triggered.columns:
        ret60_series = triggered[ret60_col].dropna()
        if len(ret60_series) > 0:
            def ret60_bucket(r):
                if pd.isna(r):   return "unknown"
                if r < -0.15:    return "extreme_bear_gt15pct_down"
                elif r < -0.05:  return "moderate_bear_5_15pct_down"
                else:            return "mild_bear_lt5pct_down"
            triggered["ret60_bucket"] = triggered[ret60_col].apply(ret60_bucket)
            ret60_stats = []
            for bucket in ["extreme_bear_gt15pct_down", "moderate_bear_5_15pct_down", "mild_bear_lt5pct_down"]:
                sub = triggered[triggered["ret60_bucket"] == bucket]
                if len(sub) >= 5:
                    ret60_stats.append({
                        "bucket": bucket,
                        "n_trades": len(sub),
                        "expectancy_r": round(sub["realized_r"].mean(), 4),
                    })
            results["spy_60d_return"] = {
                "description": "Performance by SPY 60d return magnitude",
                "buckets": ret60_stats,
            }

    # ── Dimension 4: SPY 20d return ────────────────────────────────────────────
    ret20_col = "spy_return_20d"
    if ret20_col in triggered.columns:
        ret20_series = triggered[ret20_col].dropna()
        if len(ret20_series) > 0:
            def ret20_bucket(r):
                if pd.isna(r):   return "unknown"
                if r < -0.08:    return "acute_sell_gt8pct_20d"
                elif r < -0.03:  return "moderate_sell_3_8pct_20d"
                else:            return "mild_sell_lt3pct_20d"
            triggered["ret20_bucket"] = triggered[ret20_col].apply(ret20_bucket)
            ret20_stats = []
            for bucket in ["acute_sell_gt8pct_20d", "moderate_sell_3_8pct_20d", "mild_sell_lt3pct_20d"]:
                sub = triggered[triggered["ret20_bucket"] == bucket]
                if len(sub) >= 5:
                    ret20_stats.append({
                        "bucket": bucket,
                        "n_trades": len(sub),
                        "expectancy_r": round(sub["realized_r"].mean(), 4),
                    })
            results["spy_20d_return"] = {
                "description": "Performance by SPY 20d return magnitude",
                "buckets": ret20_stats,
            }

    # ── Dimension 5: SPY range expansion ───────────────────────────────────────
    expansion_col = "spy_range_expansion"
    if expansion_col in triggered.columns:
        exp_stats = []
        for val, label in [(0, "normal_vol_day"), (1, "expansion_vol_day")]:
            sub = triggered[triggered[expansion_col] == val]
            if len(sub) >= 5:
                exp_stats.append({
                    "bucket": label,
                    "n_trades": len(sub),
                    "expectancy_r": round(sub["realized_r"].mean(), 4),
                })
        results["spy_range_expansion"] = {
            "description": "Performance on normal vs expanding range days",
            "buckets": exp_stats,
        }

    # ── Dimension 6: Year ──────────────────────────────────────────────────────
    year_stats = []
    for year in sorted(triggered["year"].unique()):
        sub = triggered[triggered["year"] == year]
        if len(sub) >= 3:
            year_stats.append({
                "year": year,
                "n_trades": len(sub),
                "expectancy_r": round(sub["realized_r"].mean(), 4),
                "cumulative_r": round(sub["realized_r"].sum(), 4),
            })
    results["by_year"] = {
        "description": "Performance by year (triggered selected trades)",
        "years": year_stats,
    }

    # ── Dimension 7: Gap size band ──────────────────────────────────────────────
    if "gap_size_band" in triggered.columns:
        gap_stats = []
        for band in ["medium", "large"]:
            sub = triggered[triggered["gap_size_band"] == band]
            if len(sub) >= 5:
                gap_stats.append({
                    "bucket": band,
                    "n_trades": len(sub),
                    "expectancy_r": round(sub["realized_r"].mean(), 4),
                })
        results["gap_size_band"] = {
            "description": "Performance by gap size band (medium vs large)",
            "buckets": gap_stats,
        }

    # ── Activation candidate summary ───────────────────────────────────────────
    # Identify dimensions where muting improves the remaining portfolio
    baseline_expectancy = float(triggered["realized_r"].mean())
    baseline_n          = len(triggered)

    activation_candidates = []

    for dim_key, dim_data in results.items():
        if "buckets" not in dim_data and "years" not in dim_data:
            continue
        buckets = dim_data.get("buckets", [])
        for b in buckets:
            b_exp = b.get("expectancy_r", 0)
            b_n   = b.get("n_trades", 0)
            if b_n < 5:
                continue
            # What's the expectancy if we mute this bucket?
            other_n   = baseline_n - b_n
            other_sum = triggered["realized_r"].sum() - b_exp * b_n
            other_exp = other_sum / other_n if other_n > 0 else 0.0
            improvement = other_exp - baseline_expectancy

            if b_exp < 0:
                verdict = "promising_mute" if improvement > 0.05 else "weak_improvement"
            elif b_exp < baseline_expectancy * 0.5:
                verdict = "below_average_bucket"
            else:
                verdict = "above_average_bucket"

            activation_candidates.append({
                "dimension": dim_key,
                "bucket": b.get("bucket") or b.get("year"),
                "n_trades": b_n,
                "bucket_expectancy_r": b_exp,
                "expectancy_if_muted_r": round(other_exp, 4),
                "expectancy_improvement_if_muted": round(improvement, 4),
                "verdict": verdict,
            })

    results["activation_candidates"] = activation_candidates
    results["baseline_expectancy_r"] = round(baseline_expectancy, 4)
    results["baseline_n_trades"]     = baseline_n

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# COVERAGE AUDIT
# ═══════════════════════════════════════════════════════════════════════════════

def build_coverage_audit(
    ticker_data: Dict[str, pd.DataFrame],
    tickers: List[str],
    context_df: pd.DataFrame,
) -> dict:
    """Summarize data coverage for the backtest audit section."""
    all_min_dates = []
    all_max_dates = []
    tickers_with_data = len(ticker_data)
    tickers_missing   = len(tickers) - tickers_with_data

    for df in ticker_data.values():
        dates = df.index.tolist()
        if dates:
            all_min_dates.append(dates[0])
            all_max_dates.append(dates[-1])

    regime_counts = context_df["market_regime_label"].value_counts().to_dict()

    # How many tickers have data going back to first bearish date
    all_bearish = sorted(context_df[context_df["market_regime_label"] == "bearish"].index.tolist())
    first_bearish = all_bearish[0] if all_bearish else "unknown"
    last_bearish  = all_bearish[-1] if all_bearish else "unknown"

    tickers_covering_full_range = sum(
        1 for df in ticker_data.values()
        if df.index[0] <= first_bearish
    )

    return {
        "cache_start_date":              sorted(all_min_dates)[0]  if all_min_dates else "unknown",
        "cache_end_date":                sorted(all_max_dates)[-1] if all_max_dates else "unknown",
        "universe_size_from_symbol_list":len(tickers),
        "parquets_loaded":               tickers_with_data,
        "parquets_missing":              tickers_missing,
        "context_model_total_dates":     len(context_df),
        "context_model_first_date":      context_df.index[0]  if len(context_df) > 0 else "unknown",
        "context_model_last_date":       context_df.index[-1] if len(context_df) > 0 else "unknown",
        "regime_distribution":           regime_counts,
        "n_bearish_signal_dates":        regime_counts.get("bearish", 0),
        "first_bearish_signal_date":     first_bearish,
        "last_bearish_signal_date":      last_bearish,
        "tickers_with_full_range_coverage": tickers_covering_full_range,
        "tickers_with_partial_range":    tickers_with_data - tickers_covering_full_range,
        "data_source":                   "repo-native daily cache only (no Polygon API calls)",
        "polygon_used":                  False,
        "note": (
            "The daily cache was originally built via the 'massive' Polygon provider. "
            "All data is fully local at time of this backtest. "
            "Tickers with partial coverage started trading or were added to the universe after 2021-03-26. "
            "warmup_na dates (19 dates) are EXCLUDED from all backtest analysis."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# OUTPUT WRITERS
# ═══════════════════════════════════════════════════════════════════════════════

def write_coverage_audit(audit: dict, tag: str) -> Path:
    path = OUTPUT_DIR / f"data_coverage_audit__gap_directional_trap__candidate_1_v1__{tag}.md"
    rd   = audit["regime_distribution"]
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# data_coverage_audit__gap_directional_trap__candidate_1_v1__{tag}\n\n")
        f.write(f"variant_id:   {VARIANT_ID}\n")
        f.write(f"generated:    {pd.Timestamp.now().strftime('%Y-%m-%d')}\n\n")
        f.write("---\n\n")
        f.write("## Daily cache coverage\n\n")
        f.write(f"| field | value |\n|-------|-------|\n")
        f.write(f"| cache_start_date | {audit['cache_start_date']} |\n")
        f.write(f"| cache_end_date | {audit['cache_end_date']} |\n")
        f.write(f"| universe_tickers_in_symbol_list | {audit['universe_size_from_symbol_list']} |\n")
        f.write(f"| parquets_loaded | {audit['parquets_loaded']} |\n")
        f.write(f"| parquets_missing | {audit['parquets_missing']} |\n")
        f.write(f"| tickers_with_full_range_coverage | {audit['tickers_with_full_range_coverage']} |\n")
        f.write(f"| tickers_with_partial_range | {audit['tickers_with_partial_range']} |\n")
        f.write(f"| data_source | {audit['data_source']} |\n")
        f.write(f"| polygon_used | {audit['polygon_used']} |\n\n")
        f.write("## Market context model\n\n")
        f.write(f"| field | value |\n|-------|-------|\n")
        f.write(f"| total_dates | {audit['context_model_total_dates']} |\n")
        f.write(f"| first_date | {audit['context_model_first_date']} |\n")
        f.write(f"| last_date | {audit['context_model_last_date']} |\n")
        for regime, cnt in rd.items():
            f.write(f"| regime_{regime} | {cnt} dates |\n")
        f.write(f"\n**Bearish signal dates (backtest scope):** {audit['n_bearish_signal_dates']} dates\n")
        f.write(f"**First bearish date:** {audit['first_bearish_signal_date']}\n")
        f.write(f"**Last bearish date:** {audit['last_bearish_signal_date']}\n\n")
        f.write("## Notes\n\n")
        f.write(audit["note"] + "\n")
    return path


def write_trade_logs(raw_df: pd.DataFrame, sel_df: pd.DataFrame, tag: str) -> Tuple[Path, Path]:
    raw_path = OUTPUT_DIR / f"full_history_trade_log__gap_directional_trap__candidate_1_v1__{tag}.csv"
    sel_path = OUTPUT_DIR / f"full_history_trade_log__selected_top_3__gap_directional_trap__candidate_1_v1__{tag}.csv"
    raw_df.to_csv(raw_path, index=False)
    sel_df.to_csv(sel_path, index=False)
    return raw_path, sel_path


def write_yearly_summary(raw_yearly: pd.DataFrame, sel_yearly: pd.DataFrame, tag: str) -> Path:
    path = OUTPUT_DIR / f"backtest_yearly_summary__gap_directional_trap__candidate_1_v1__{tag}.csv"
    raw_yearly["layer"] = "raw_module"
    sel_yearly["layer"] = "selected_top_3"
    combined = pd.concat([raw_yearly, sel_yearly], ignore_index=True)
    combined.to_csv(path, index=False)
    return path


def write_monthly_summary(raw_monthly: pd.DataFrame, sel_monthly: pd.DataFrame, tag: str) -> Path:
    path = OUTPUT_DIR / f"backtest_monthly_summary__gap_directional_trap__candidate_1_v1__{tag}.csv"
    raw_monthly["layer"] = "raw_module"
    sel_monthly["layer"] = "selected_top_3"
    combined = pd.concat([raw_monthly, sel_monthly], ignore_index=True)
    combined.to_csv(path, index=False)
    return path


def write_drawdown_summary(dd_dict: dict, daily_df: pd.DataFrame, tag: str) -> Path:
    path = OUTPUT_DIR / f"backtest_drawdown_summary__gap_directional_trap__candidate_1_v1__{tag}.csv"
    dd_df = pd.DataFrame([dd_dict])
    dd_df.to_csv(path, index=False)
    if not daily_df.empty:
        eq_path = OUTPUT_DIR / f"backtest_equity_curve__selected_top_3__gap_directional_trap__candidate_1_v1__{tag}.csv"
        daily_df.to_csv(eq_path, index=False)
    return path


def write_ticker_concentration(raw_conc: pd.DataFrame, sel_conc: pd.DataFrame, tag: str) -> Path:
    path = OUTPUT_DIR / f"backtest_ticker_concentration__gap_directional_trap__candidate_1_v1__{tag}.csv"
    raw_conc["layer"] = "raw_module"
    sel_conc["layer"] = "selected_top_3"
    combined = pd.concat([raw_conc, sel_conc], ignore_index=True)
    combined.to_csv(path, index=False)
    return path


def write_raw_vs_selected_comparison(raw_stats: dict, sel_stats: dict, tag: str) -> Path:
    path = OUTPUT_DIR / f"backtest_raw_vs_selected_comparison__gap_directional_trap__candidate_1_v1__{tag}.csv"
    metrics = [
        "total_signals", "n_triggered", "n_no_fill", "trigger_rate_pct",
        "n_target_hit", "n_stop_hit", "n_moc_win", "n_moc_loss", "n_ambiguous",
        "target_hit_rate_pct", "stop_hit_rate_pct", "moc_win_rate_pct", "moc_loss_rate_pct",
        "expectancy_r", "median_r", "cumulative_r", "win_rate_pct", "loss_rate_pct",
        "profit_factor", "avg_pnl_pct", "avg_mae_pct", "avg_mfe_pct",
        "max_win_streak", "max_loss_streak",
    ]
    rows = []
    for m in metrics:
        rows.append({
            "metric": m,
            "raw_module": raw_stats.get(m),
            "selected_top_3": sel_stats.get(m),
        })
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def write_regime_summary(df: pd.DataFrame, tag: str) -> Path:
    """Regime-dimension summary using context fields on triggered trades."""
    path = OUTPUT_DIR / f"backtest_regime_summary__gap_directional_trap__candidate_1_v1__{tag}.csv"
    triggered = df[(df["entry_triggered"] == True) & df["realized_r"].notna()].copy()
    rows = []
    # Group by year
    for year in sorted(triggered["year"].unique()):
        sub = triggered[triggered["year"] == year]
        rows.append({
            "dimension": "year",
            "bucket": year,
            "n_triggered": len(sub),
            "expectancy_r": round(sub["realized_r"].mean(), 4),
            "cumulative_r": round(sub["realized_r"].sum(), 4),
        })
    # Group by gap_size_band
    for band in ["medium", "large"]:
        sub = triggered[triggered.get("gap_size_band", pd.Series()) == band] if "gap_size_band" in triggered.columns else pd.DataFrame()
        if len(sub) > 0:
            rows.append({
                "dimension": "gap_size_band",
                "bucket": band,
                "n_triggered": len(sub),
                "expectancy_r": round(sub["realized_r"].mean(), 4),
                "cumulative_r": round(sub["realized_r"].sum(), 4),
            })
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def write_activation_study(study: dict, tag: str) -> Path:
    path = OUTPUT_DIR / f"activation_study__gap_directional_trap__candidate_1_v1__{tag}.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# activation_study__gap_directional_trap__candidate_1_v1__{tag}\n\n")
        f.write(f"variant_id:      {VARIANT_ID}\n")
        f.write(f"layer_analyzed:  selected_top_3 triggered trades\n")
        f.write(f"baseline_expectancy_r: {study.get('baseline_expectancy_r', 'N/A')}\n")
        f.write(f"baseline_n_trades:     {study.get('baseline_n_trades', 'N/A')}\n\n")
        f.write("---\n\n")
        f.write("## Activation study purpose\n\n")
        f.write(
            "This study tests whether simple, already-available context signals can identify "
            "periods where the module should be muted or activated.\n\n"
            "Rules tested are simple and transparent. No ML model. No overfitting.\n"
            "Verdict definitions:\n"
            "- **promising_mute**: muting this bucket improves expectancy meaningfully (>0.05R)\n"
            "- **weak_improvement**: negative bucket, but muting barely improves the whole\n"
            "- **below_average_bucket**: positive but below baseline — consider deprioritizing\n"
            "- **above_average_bucket**: performs better than baseline\n\n"
        )

        dim_descriptions = {
            "vol_regime":        "SPY realized vol 20d (low / medium / high)",
            "spy_sma200_position": "SPY position vs SMA200",
            "spy_60d_return":    "SPY 60d return magnitude (extreme vs moderate vs mild bear)",
            "spy_20d_return":    "SPY 20d return magnitude",
            "spy_range_expansion": "SPY range expansion flag",
            "gap_size_band":     "Gap size band (medium vs large)",
        }

        skip_keys = {"activation_candidates", "baseline_expectancy_r", "baseline_n_trades", "by_year"}

        for dim_key, dim_data in study.items():
            if dim_key in skip_keys:
                continue
            if not isinstance(dim_data, dict):
                continue
            desc = dim_descriptions.get(dim_key, dim_key)
            f.write(f"## Dimension: {desc}\n\n")
            if "description" in dim_data:
                f.write(f"*{dim_data['description']}*\n\n")
            if "q33_threshold" in dim_data:
                f.write(f"Vol thresholds: q33={dim_data['q33_threshold']}, q67={dim_data['q67_threshold']}\n\n")
            buckets = dim_data.get("buckets", [])
            if buckets:
                f.write("| bucket | n_trades | expectancy_r |\n|--------|----------|--------------|\n")
                for b in buckets:
                    f.write(f"| {b.get('bucket')} | {b.get('n_trades')} | {b.get('expectancy_r', 'N/A')} |\n")
            f.write("\n")

        f.write("## By year (selected_top_3 triggered trades)\n\n")
        year_data = study.get("by_year", {})
        years = year_data.get("years", [])
        if years:
            f.write("| year | n_trades | expectancy_r | cumulative_r |\n|------|----------|--------------|------------- |\n")
            for y in years:
                f.write(f"| {y['year']} | {y['n_trades']} | {y['expectancy_r']} | {y['cumulative_r']} |\n")
        f.write("\n---\n\n")

        f.write("## Activation candidate summary\n\n")
        candidates = study.get("activation_candidates", [])
        if candidates:
            f.write("| dimension | bucket | n_trades | bucket_expectancy_r | expectancy_if_muted | improvement | verdict |\n")
            f.write("|-----------|--------|----------|---------------------|---------------------|-------------|--------|\n")
            for c in sorted(candidates, key=lambda x: x["expectancy_improvement_if_muted"], reverse=True):
                f.write(
                    f"| {c['dimension']} | {c['bucket']} | {c['n_trades']} | "
                    f"{c['bucket_expectancy_r']} | {c['expectancy_if_muted_r']} | "
                    f"{c['expectancy_improvement_if_muted']} | {c['verdict']} |\n"
                )
        else:
            f.write("No activation candidates computed.\n")

        f.write("\n---\n\n## Activation recommendation\n\n")
        f.write(
            "See the candidate table above. For any dimension marked **promising_mute**, "
            "evaluate:\n"
            "1. Is the sample large enough to be credible?\n"
            "2. Is there a plausible behavioral reason for the muting rule?\n"
            "3. Does the rule pass a simple out-of-sample check (e.g., hold out 2021-2022, test 2023+)?\n\n"
            "Do NOT promote a muting rule without completing all three checks.\n"
            "Report any promising rule to the research track for formal phase_r4/r5 re-evaluation.\n"
        )
    return path


def write_overall_summary_csv(raw_stats: dict, sel_stats: dict, tag: str) -> Path:
    path = OUTPUT_DIR / f"backtest_overall_summary__gap_directional_trap__candidate_1_v1__{tag}.csv"
    raw_row = {"layer": "raw_module",    **raw_stats}
    sel_row = {"layer": "selected_top_3", **sel_stats}
    pd.DataFrame([raw_row, sel_row]).to_csv(path, index=False)
    return path


def write_executive_summary(
    audit: dict,
    raw_stats: dict,
    sel_stats: dict,
    raw_yearly: pd.DataFrame,
    sel_yearly: pd.DataFrame,
    dd_dict: dict,
    activation: dict,
    tag: str,
) -> Path:
    path = OUTPUT_DIR / f"executive_summary__gap_directional_trap__candidate_1_v1__{tag}.md"

    def s(val, fmt=None):
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return "N/A"
        if fmt:
            return fmt.format(val)
        return str(val)

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# executive_summary__gap_directional_trap__candidate_1_v1__{tag}\n\n")
        f.write(f"variant_id:    {VARIANT_ID}\n")
        f.write(f"generated:     {pd.Timestamp.now().strftime('%Y-%m-%d')}\n\n")
        f.write("---\n\n")

        f.write("## 1. Data coverage\n\n")
        f.write(f"- Cache range: {audit['cache_start_date']} to {audit['cache_end_date']}\n")
        f.write(f"- Universe: {audit['universe_size_from_symbol_list']} tickers "
                f"({audit['parquets_loaded']} loaded, {audit['parquets_missing']} missing)\n")
        f.write(f"- Bearish signal dates: {audit['n_bearish_signal_dates']} "
                f"({audit['first_bearish_signal_date']} → {audit['last_bearish_signal_date']})\n")
        f.write(f"- Data source: cache-only (no Polygon API calls)\n\n")

        f.write("## 2. Raw module results (all valid signals)\n\n")
        f.write(f"| metric | value |\n|--------|-------|\n")
        for k in ["total_signals", "n_triggered", "n_no_fill", "trigger_rate_pct",
                  "n_target_hit", "n_stop_hit", "n_moc_win", "n_moc_loss", "n_ambiguous",
                  "target_hit_rate_pct", "stop_hit_rate_pct", "moc_win_rate_pct", "moc_loss_rate_pct",
                  "expectancy_r", "median_r", "cumulative_r", "win_rate_pct", "loss_rate_pct", "profit_factor"]:
            f.write(f"| {k} | {s(raw_stats.get(k))} |\n")
        f.write("\n")

        f.write("## 3. Selected top_3 portfolio results\n\n")
        f.write(f"| metric | value |\n|--------|-------|\n")
        for k in ["total_signals", "n_triggered", "n_no_fill", "trigger_rate_pct",
                  "n_target_hit", "n_stop_hit", "n_moc_win", "n_moc_loss", "n_ambiguous",
                  "target_hit_rate_pct", "stop_hit_rate_pct", "moc_win_rate_pct", "moc_loss_rate_pct",
                  "expectancy_r", "median_r", "cumulative_r", "win_rate_pct", "loss_rate_pct", "profit_factor"]:
            f.write(f"| {k} | {s(sel_stats.get(k))} |\n")
        f.write("\n")

        f.write("## 4. Yearly results — raw module\n\n")
        if not raw_yearly.empty and "label" in raw_yearly.columns:
            f.write("| year | signals | triggered | expectancy_r | cumulative_r |\n")
            f.write("|------|---------|-----------|--------------|---------------|\n")
            for _, row in raw_yearly.sort_values("label").iterrows():
                f.write(
                    f"| {row.get('label')} | {row.get('total_signals', '?')} | "
                    f"{row.get('n_triggered', '?')} | {row.get('expectancy_r', '?')} | "
                    f"{row.get('cumulative_r', '?')} |\n"
                )
        f.write("\n")

        f.write("## 5. Yearly results — selected top_3\n\n")
        if not sel_yearly.empty and "label" in sel_yearly.columns:
            f.write("| year | signals | triggered | expectancy_r | cumulative_r |\n")
            f.write("|------|---------|-----------|--------------|---------------|\n")
            for _, row in sel_yearly.sort_values("label").iterrows():
                f.write(
                    f"| {row.get('label')} | {row.get('total_signals', '?')} | "
                    f"{row.get('n_triggered', '?')} | {row.get('expectancy_r', '?')} | "
                    f"{row.get('cumulative_r', '?')} |\n"
                )
        f.write("\n")

        f.write("## 6. Drawdown summary (selected top_3)\n\n")
        f.write(f"| metric | value |\n|--------|-------|\n")
        for k, v in dd_dict.items():
            f.write(f"| {k} | {s(v)} |\n")
        f.write("\n")

        f.write("## 7. Raw vs selected comparison\n\n")
        comparison_metrics = [
            ("expectancy_r",      "Expectancy R (per triggered trade)"),
            ("cumulative_r",      "Cumulative R (total triggered trades)"),
            ("n_triggered",       "Triggered trades"),
            ("win_rate_pct",      "Win rate %"),
            ("loss_rate_pct",     "Loss rate %"),
            ("profit_factor",     "Profit factor"),
            ("moc_win_rate_pct",  "MOC win rate %"),
            ("moc_loss_rate_pct", "MOC loss rate %"),
        ]
        f.write("| metric | raw_module | selected_top_3 |\n|--------|------------|----------------|\n")
        for k, desc in comparison_metrics:
            f.write(f"| {desc} | {s(raw_stats.get(k))} | {s(sel_stats.get(k))} |\n")
        f.write("\n")

        f.write("## 8. Activation study summary\n\n")
        candidates = activation.get("activation_candidates", [])
        promising  = [c for c in candidates if c["verdict"] == "promising_mute"]
        if promising:
            f.write("**Promising muting candidates found:**\n\n")
            for c in sorted(promising, key=lambda x: x["expectancy_improvement_if_muted"], reverse=True):
                f.write(
                    f"- Dimension: **{c['dimension']}**, bucket: `{c['bucket']}` | "
                    f"n_trades={c['n_trades']}, bucket_exp={c['bucket_expectancy_r']}R, "
                    f"improvement_if_muted=+{c['expectancy_improvement_if_muted']}R\n"
                )
        else:
            f.write("No strongly promising muting candidates found. Module behavior is relatively uniform.\n")
        f.write("\n")

        # Module activation recommendation
        sel_exp = sel_stats.get("expectancy_r", 0) or 0
        raw_exp = raw_stats.get("expectancy_r", 0) or 0
        if sel_exp > 0.15:
            activation_verdict = "**always_on** — expectancy positive and material across full history"
        elif sel_exp > 0.05:
            activation_verdict = "**conditionally_on** — positive expectancy but improvement via muting likely worthwhile"
        elif sel_exp > 0:
            activation_verdict = "**hold_for_more_work** — marginally positive; needs regime-gating to improve"
        else:
            activation_verdict = "**hold_for_more_work** — negative or negligible expectancy; needs regime investigation"

        f.write("## 9. Module activation recommendation\n\n")
        f.write(f"Raw module expectancy:      {s(raw_exp, '{:.4f}')}R\n")
        f.write(f"Selected top_3 expectancy:  {s(sel_exp, '{:.4f}')}R\n\n")
        f.write(f"**Recommendation:** {activation_verdict}\n\n")

        f.write("## 10. Files created in this batch\n\n")
        output_files = [
            f"data_coverage_audit__gap_directional_trap__candidate_1_v1__{tag}.md",
            f"full_history_trade_log__gap_directional_trap__candidate_1_v1__{tag}.csv",
            f"full_history_trade_log__selected_top_3__gap_directional_trap__candidate_1_v1__{tag}.csv",
            f"backtest_overall_summary__gap_directional_trap__candidate_1_v1__{tag}.csv",
            f"backtest_yearly_summary__gap_directional_trap__candidate_1_v1__{tag}.csv",
            f"backtest_monthly_summary__gap_directional_trap__candidate_1_v1__{tag}.csv",
            f"backtest_regime_summary__gap_directional_trap__candidate_1_v1__{tag}.csv",
            f"backtest_drawdown_summary__gap_directional_trap__candidate_1_v1__{tag}.csv",
            f"backtest_equity_curve__selected_top_3__gap_directional_trap__candidate_1_v1__{tag}.csv",
            f"backtest_ticker_concentration__gap_directional_trap__candidate_1_v1__{tag}.csv",
            f"backtest_raw_vs_selected_comparison__gap_directional_trap__candidate_1_v1__{tag}.csv",
            f"activation_study__gap_directional_trap__candidate_1_v1__{tag}.md",
            f"executive_summary__gap_directional_trap__candidate_1_v1__{tag}.md",
        ]
        for fn in output_files:
            f.write(f"- {fn}\n")
        f.write("\n")

        f.write("## 11. Next step\n\n")
        f.write(
            "Review activation study and drawdown findings.\n"
            "If a promising muting candidate is confirmed, propose it as a phase_r4 addendum "
            "in the research track before applying it to the engineering module.\n"
            "If activation verdict is **always_on**, proceed to: "
            "`engineering_build_windows_task_scheduler__gap_directional_trap__candidate_1_v1`.\n"
        )
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print("=" * 72)
    print("  FULL HISTORY BACKTEST + ACTIVATION STUDY")
    print(f"  variant: {VARIANT_ID}")
    print(f"  range:   {DATE_RANGE_TAG}")
    print("=" * 72)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Load data ─────────────────────────────────────────────────────────────
    print("\n[step 1/7] Loading universe tickers...")
    tickers    = load_universe_tickers()
    us_cs_set  = load_us_cs_set()
    print(f"  universe: {len(tickers)} tickers, us_cs_set: {len(us_cs_set)}")

    print("\n[step 2/7] Loading market context model...")
    context_df = load_market_context()
    regime_counts = context_df["market_regime_label"].value_counts().to_dict()
    print(f"  {len(context_df)} dates loaded: {regime_counts}")

    print("\n[step 3/7] Loading daily parquets (this takes several minutes)...")
    ticker_data = load_all_daily_parquets(tickers)

    # ── Coverage audit ────────────────────────────────────────────────────────
    print("\n[step 4/7] Building coverage audit...")
    audit = build_coverage_audit(ticker_data, tickers, context_df)
    write_coverage_audit(audit, DATE_RANGE_TAG)
    print(f"  Bearish signal dates:  {audit['n_bearish_signal_dates']}")
    print(f"  Parquets loaded:       {audit['parquets_loaded']}")

    # ── Run backtest ──────────────────────────────────────────────────────────
    print("\n[step 5/7] Running full history backtest...")
    raw_df, sel_df = run_backtest(ticker_data, context_df, us_cs_set)

    if raw_df.empty:
        print("[!] No raw trades generated. Check data and market context model.")
        sys.exit(1)

    # Write trade logs first
    write_trade_logs(raw_df, sel_df, DATE_RANGE_TAG)
    print(f"  Raw module trades:      {len(raw_df)}")
    print(f"  Selected top_3 trades:  {len(sel_df)}")

    # ── Compute statistics ────────────────────────────────────────────────────
    print("\n[step 6/7] Computing statistics...")

    raw_stats  = compute_trade_stats(raw_df,  label="raw_module")
    sel_stats  = compute_trade_stats(sel_df,  label="selected_top_3")
    raw_yearly = compute_yearly_summary(raw_df)
    sel_yearly = compute_yearly_summary(sel_df)
    raw_monthly = compute_monthly_summary(raw_df)
    sel_monthly = compute_monthly_summary(sel_df)

    daily_portfolio = compute_daily_portfolio_r(sel_df)
    dd_dict = compute_drawdown(daily_portfolio) if not daily_portfolio.empty else {}

    raw_conc = compute_ticker_concentration(raw_df)
    sel_conc = compute_ticker_concentration(sel_df)

    # ── Activation study ──────────────────────────────────────────────────────
    activation = run_activation_study(sel_df, context_df)

    # ── Write all outputs ─────────────────────────────────────────────────────
    print("\n[step 7/7] Writing output files...")

    write_overall_summary_csv(raw_stats, sel_stats, DATE_RANGE_TAG)
    write_yearly_summary(raw_yearly, sel_yearly, DATE_RANGE_TAG)
    write_monthly_summary(raw_monthly, sel_monthly, DATE_RANGE_TAG)
    write_drawdown_summary(dd_dict, daily_portfolio, DATE_RANGE_TAG)
    write_ticker_concentration(raw_conc, sel_conc, DATE_RANGE_TAG)
    write_raw_vs_selected_comparison(raw_stats, sel_stats, DATE_RANGE_TAG)
    write_regime_summary(sel_df, DATE_RANGE_TAG)
    write_activation_study(activation, DATE_RANGE_TAG)
    exec_path = write_executive_summary(
        audit, raw_stats, sel_stats,
        raw_yearly, sel_yearly,
        dd_dict, activation, DATE_RANGE_TAG,
    )

    # ── Print terminal summary ─────────────────────────────────────────────────
    print()
    print("=" * 72)
    print("  BACKTEST COMPLETE")
    print("=" * 72)
    print(f"  Date range:             {DATE_RANGE_TAG}")
    print(f"  Bearish signal dates:   {audit['n_bearish_signal_dates']}")
    print(f"  Raw module signals:     {raw_stats['total_signals']}")
    print(f"  Raw triggered trades:   {raw_stats['n_triggered']}")
    print(f"  Raw expectancy:         {raw_stats['expectancy_r']}R")
    print(f"  Raw cumulative R:       {raw_stats['cumulative_r']}R")
    print(f"  ---")
    print(f"  Selected signals:       {sel_stats['total_signals']}")
    print(f"  Selected triggered:     {sel_stats['n_triggered']}")
    print(f"  Selected expectancy:    {sel_stats['expectancy_r']}R")
    print(f"  Selected cumulative R:  {sel_stats['cumulative_r']}R")
    if dd_dict:
        print(f"  Max drawdown (sel):     {dd_dict.get('max_drawdown_r', 'N/A')}R")
        print(f"  DD period start:        {dd_dict.get('max_drawdown_start_date', 'N/A')}")
        print(f"  DD period end:          {dd_dict.get('max_drawdown_end_date', 'N/A')}")
    print(f"  ---")
    print(f"  Output dir:  {OUTPUT_DIR}")
    print(f"  Exec summary: {exec_path.name}")
    print("=" * 72)

    # Print activation candidates
    print("\n  ACTIVATION STUDY TOP CANDIDATES:")
    candidates = activation.get("activation_candidates", [])
    promising  = [c for c in candidates if c["verdict"] == "promising_mute"]
    if promising:
        for c in sorted(promising, key=lambda x: x["expectancy_improvement_if_muted"], reverse=True)[:5]:
            print(
                f"    [{c['verdict']}] {c['dimension']}::{c['bucket']} | "
                f"n={c['n_trades']} exp={c['bucket_expectancy_r']}R "
                f"improvement=+{c['expectancy_improvement_if_muted']}R"
            )
    else:
        print("    No strongly promising muting candidates — module is relatively uniform.")
    print()


if __name__ == "__main__":
    main()
