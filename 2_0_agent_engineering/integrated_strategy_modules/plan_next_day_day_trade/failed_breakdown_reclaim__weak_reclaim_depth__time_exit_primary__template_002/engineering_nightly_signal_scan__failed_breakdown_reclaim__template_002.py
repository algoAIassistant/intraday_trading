"""
engineering_nightly_signal_scan__failed_breakdown_reclaim__template_002.py

track:    plan_next_day_day_trade
family:   failed_breakdown_reclaim
variant:  failed_breakdown_reclaim__weak_reclaim_depth__time_exit_primary__template_002

Purpose:
  Nightly signal scan. Runs after market close. Reads repo-native daily data,
  applies the locked 3-condition signal filter, applies hard ADV and price gates,
  computes frozen entry/stop prices, and writes a signal pack CSV for next-day TOS use.

Signal filters (locked — do not alter):
  1. signal_day_low < prior_day_low          (breakdown occurred)
  2. signal_day_close > prior_day_low        (reclaim occurred)
  3. breakdown_depth_pct >= 0.005            (breakdown at least 0.5% below prior_day_low)
  4. reclaim_pct <= 0.002                    (close within 0.2% above prior_day_low)

Hard deployment gates (from phase_r6 — do not relax):
  ADV:   adv_50m_100m or adv_100m_plus only
  Price: exclude price_5_10 (signal_day_close < 10.00); exclude price > 100.00 (aligns with gap_directional_trap practical universe)

Context flag (soft — do not hard-block):
  bearish context → context_confidence = "low"
  bullish / neutral → context_confidence = "high"

Execution template (frozen):
  entry_price:    signal_day_high  (buy stop — no buffer)
  stop_price:     signal_day_low   (hard protective stop — no buffer)
  target_price:   none             (time exit is the primary exit)
  cancel_time_et: 13:30            (cancel if not triggered)
  flatten_time_et: 14:30           (flatten all open positions)

Output:
  engineering_runtime_outputs/plan_next_day_day_trade/
    failed_breakdown_reclaim__template_002/
      signal_pack__failed_breakdown_reclaim__template_002__YYYY_MM_DD.csv

Usage:
  python engineering_nightly_signal_scan__failed_breakdown_reclaim__template_002.py
  python engineering_nightly_signal_scan__failed_breakdown_reclaim__template_002.py --signal-date 2026-03-31

Handoff source:
  1_0_strategy_research/research_outputs/family_lineages/plan_next_day_day_trade/
    failed_breakdown_reclaim/phase_r8_handoff/
    deployable_variant_spec__failed_breakdown_reclaim__template_002.md

Assumptions (explicit):
  - ADV is computed as a 20-trading-day rolling mean of (close * volume) ending on the
    day prior to the signal date. This is the best available proxy from daily OHLCV.
    A pre-built operational universe with pre-computed ADV buckets does not exist yet for
    this variant. ADV is computed at scan time from the daily parquet cache.
  - Price bucket is assigned from signal_day_close (the close on the signal day).
  - Market context is loaded from the same context model file used by gap_directional_trap.
  - The module scans the full shared master universe (no pre-filtered operational universe).
  - next_business_day does not account for market holidays — same as gap_directional_trap.
  - Tickers without sufficient parquet history (< 21 trading days before signal date)
    are skipped silently; they cannot have a reliable ADV estimate.

Do NOT add:
  - Telegram delivery
  - scheduler / cron integration
  - broker API calls
  - Alpaca
  - live execution
  - reactive intraday logic
  - ranking logic
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# ── Repo root resolution ───────────────────────────────────────────────────────
# File location: 2_0_agent_engineering/integrated_strategy_modules/
#                plan_next_day_day_trade/failed_breakdown_reclaim__weak_reclaim_depth__time_exit_primary__template_002/
# parents[0] = failed_breakdown_reclaim__weak_reclaim_depth__time_exit_primary__template_002/
# parents[1] = plan_next_day_day_trade/
# parents[2] = integrated_strategy_modules/
# parents[3] = 2_0_agent_engineering/
# parents[4] = ai_trading_assistant/ (REPO_ROOT)
REPO_ROOT = Path(__file__).resolve().parents[4]
ENG_ROOT  = Path(__file__).resolve().parents[3]   # 2_0_agent_engineering/

# ── Data paths ─────────────────────────────────────────────────────────────────
UNIVERSE_FILE = (
    REPO_ROOT
    / "0_1_shared_master_universe"
    / "shared_symbol_lists"
    / "shared_master_symbol_list_us_common_stocks.csv"
)
DAILY_CACHE_DIR = REPO_ROOT / "1_0_strategy_research" / "research_data_cache" / "daily"
MARKET_CONTEXT_FILE = (
    REPO_ROOT
    / "1_0_strategy_research"
    / "research_outputs"
    / "family_lineages"
    / "plan_next_day_day_trade"
    / "phase_r1_market_context_model"
    / "market_context_model_plan_next_day_day_trade.csv"
)
OUTPUT_DIR = (
    REPO_ROOT
    / "2_0_agent_engineering"
    / "engineering_runtime_outputs"
    / "plan_next_day_day_trade"
    / "failed_breakdown_reclaim__template_002"
)

# ── Variant identity (frozen) ──────────────────────────────────────────────────
VARIANT_NAME  = "failed_breakdown_reclaim__weak_reclaim_depth__time_exit_primary__template_002"
FAMILY_NAME   = "failed_breakdown_reclaim"

# Research expectancy from phase_r6 (adv_50m_100m_plus deployment scope, no-slippage basis).
# adv_50m_100m + adv_100m_plus combined: mean_r ~+0.079. adv_100m_plus alone: +0.100.
# Slippage-adjusted estimate at ~0.05% slip (adv_100m_plus): ~+0.067.
RESEARCH_EXPECTANCY_R_NO_SLIP  = 0.079   # combined deployment scope, no slippage
RESEARCH_EXPECTANCY_R_ADJ      = 0.067   # adv_100m_plus estimated at ~0.05% slip

# ── Locked signal-filter thresholds (do not alter) ────────────────────────────
LOCKED_BREAKDOWN_DEPTH_PCT = 0.005   # signal_day_low at least 0.5% below prior_day_low
LOCKED_RECLAIM_PCT         = 0.002   # signal_day_close within 0.2% above prior_day_low

# ── Locked execution template (do not alter) ──────────────────────────────────
# entry = signal_day_high exactly (buy stop, no buffer)
# stop  = signal_day_low exactly (hard protective, no buffer)
# target = none
ACTIVATE_ORDER_AT_ET          = "13:15"
CANCEL_IF_NOT_TRIGGERED_BY_ET = "13:30"
FORCED_EXIT_TIME_ET           = "14:30"

# ── Hard deployment gates (from phase_r6 — do not relax) ──────────────────────
# ADV gate: adv_50m_100m and adv_100m_plus only.
# adv_5m_20m median_r = 0 before slippage; adv_20m_50m marginal. Both excluded.
ADV_ALLOWED_BUCKETS = {"adv_50m_100m", "adv_100m_plus"}

# Price gate: exclude price_5_10 (signal_day_close < 10.00).
# price_5_10 median_r = 0, TE win rate 55.74%. Negative after slippage.
# Upper bound matches gap_directional_trap practical universe: exclude price > 100.00.
PRICE_EXCLUDE_BELOW = 10.0
PRICE_EXCLUDE_ABOVE = 100.0

# ── ADV computation parameters ─────────────────────────────────────────────────
ADV_LOOKBACK_DAYS = 20   # rolling window for average dollar volume estimate

# ── Static text fields ─────────────────────────────────────────────────────────
CANCEL_CONDITION_TEXT = (
    "Cancel buy stop if not triggered by 13:30 ET."
)
SAME_DAY_EXIT_RULE = (
    "Flatten at 14:30 ET. No fixed target — time exit is the primary exit. "
    "Hard stop at signal_day_low remains active until triggered or cancel/flatten."
)
STRATEGY_CHARACTER_NOTE = (
    "Breakdown-trap family. Stock broke below prior_day_low on signal day, "
    "triggering obvious bear thesis, then closed barely above it (reclaim <= 0.2%). "
    "Trapped shorts provide squeeze fuel. Buy stop activates above signal_day_high at 13:15 ET. "
    "Cancel at 13:30 if not triggered. Flatten at 14:30 ET regardless."
)
BEARISH_CONTEXT_WARNING = (
    "bearish_regime: mean_r +0.027 before slippage (near zero after). "
    "context_confidence = low. Consider reduced size or skip."
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def next_business_day(d: date) -> date:
    """Return the next calendar business day (Mon–Fri). Does not account for holidays."""
    d = d + timedelta(days=1)
    while d.weekday() >= 5:
        d = d + timedelta(days=1)
    return d


def assign_adv_bucket(adv_dollar: float) -> str:
    """Assign ADV dollar bucket from rolling mean dollar volume estimate."""
    if adv_dollar < 5_000_000:
        return "adv_lt_5m"
    elif adv_dollar < 20_000_000:
        return "adv_5m_20m"
    elif adv_dollar < 50_000_000:
        return "adv_20m_50m"
    elif adv_dollar < 100_000_000:
        return "adv_50m_100m"
    else:
        return "adv_100m_plus"


def assign_price_bucket(price: float) -> str:
    """Assign price bucket from signal_day_close. Hard gates exclude < $10 and > $100."""
    if price < 10.0:
        return "price_lt_10"    # should not reach here — hard gated
    elif price < 30.0:
        return "price_10_30"
    elif price < 50.0:
        return "price_30_50"
    elif price < 70.0:
        return "price_50_70"
    else:
        return "price_70_100"   # $70–$100 (hard gate at $100 above)


def load_universe() -> list[str]:
    """Load ticker list from shared master universe."""
    df = pd.read_csv(UNIVERSE_FILE, dtype={"ticker": str})
    tickers = df["ticker"].dropna().str.strip().str.upper().tolist()
    print(f"[universe] shared master universe: {len(tickers)} tickers")
    return tickers


def load_market_context() -> pd.DataFrame:
    df = pd.read_csv(MARKET_CONTEXT_FILE)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df.set_index("date")


def load_daily_parquet(ticker: str) -> pd.DataFrame | None:
    """Load daily parquet; normalize index to YYYY-MM-DD strings, sorted ascending."""
    path = DAILY_CACHE_DIR / f"{ticker}.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        df = df[~df.index.duplicated(keep="last")].sort_index()
        return df
    except Exception:
        return None


def compute_rolling_adv(daily: pd.DataFrame, signal_idx: int) -> float | None:
    """
    Compute rolling ADV (average dollar volume) over the ADV_LOOKBACK_DAYS trading days
    ending at the row before signal_idx (i.e., using pre-signal data only).

    Returns None if insufficient history.
    """
    # Use rows prior to signal_idx for ADV — no look-ahead
    end_idx   = signal_idx          # exclusive: rows 0..(signal_idx-1)
    start_idx = end_idx - ADV_LOOKBACK_DAYS
    if start_idx < 0:
        return None

    window = daily.iloc[start_idx:end_idx]
    if len(window) < ADV_LOOKBACK_DAYS:
        return None

    try:
        dollar_vol = window["close"] * window["volume"]
        return float(dollar_vol.mean())
    except Exception:
        return None


# ── Main scan ──────────────────────────────────────────────────────────────────

def run_scan(signal_date_str: str | None = None) -> None:

    tickers = load_universe()
    print(f"[1] Universe loaded: {len(tickers)} tickers")

    market_ctx = load_market_context()
    print(f"[2] Market context model loaded: {len(market_ctx)} dates, "
          f"most recent = {market_ctx.index.max()}")

    if signal_date_str:
        signal_date = signal_date_str
    else:
        signal_date = market_ctx.index.max()
    print(f"[3] Signal date: {signal_date}")

    signal_dt = pd.to_datetime(signal_date).date()
    today = date.today()
    days_old = (today - signal_dt).days
    if days_old > 5:
        print(f"    [WARNING] Signal date is {days_old} days old — daily cache may be stale.")

    if signal_date not in market_ctx.index:
        print(f"[!] No market context row for {signal_date}. Cannot determine regime. Exiting.")
        sys.exit(1)

    market_regime_label = market_ctx.loc[signal_date, "market_regime_label"]
    print(f"[4] Market regime for {signal_date}: {market_regime_label}")

    # Soft flag — bearish does NOT block signal generation, but gets flagged.
    bearish_regime = (market_regime_label == "bearish")
    if bearish_regime:
        print(f"    [FLAG] Bearish regime — signals will be flagged context_confidence=low.")

    # context_confidence: bullish/neutral → high, bearish → low
    context_confidence = "low" if bearish_regime else "high"

    next_trade_date = next_business_day(signal_dt)
    print(f"[5] Next trade date (estimated): {next_trade_date}")

    print(f"\n[6] Scanning {len(tickers)} tickers...")

    count_no_data           = 0
    count_no_signal_date    = 0
    count_no_prev_row       = 0
    count_insufficient_adv  = 0
    count_adv_gate_fail     = 0
    count_price_gate_fail   = 0
    count_no_breakdown      = 0
    count_no_reclaim        = 0
    count_depth_fail        = 0
    count_reclaim_pct_fail  = 0
    count_passing           = 0

    signals = []

    for ticker in tickers:
        daily = load_daily_parquet(ticker)

        if daily is None:
            count_no_data += 1
            continue

        if signal_date not in daily.index:
            count_no_signal_date += 1
            continue

        date_list  = list(daily.index)
        signal_idx = date_list.index(signal_date)

        if signal_idx == 0:
            count_no_prev_row += 1
            continue

        signal_row = daily.loc[signal_date]
        prev_row   = daily.iloc[signal_idx - 1]

        signal_day_open  = float(signal_row["open"])
        signal_day_high  = float(signal_row["high"])
        signal_day_low   = float(signal_row["low"])
        signal_day_close = float(signal_row["close"])
        prior_day_low    = float(prev_row["low"])

        if prior_day_low <= 0 or signal_day_high <= 0:
            count_no_data += 1
            continue

        # ── Hard price gate (computed before ADV to fail fast on out-of-range names) ──
        if signal_day_close < PRICE_EXCLUDE_BELOW or signal_day_close > PRICE_EXCLUDE_ABOVE:
            count_price_gate_fail += 1
            continue
        price_bucket = assign_price_bucket(signal_day_close)

        # ── ADV gate (hard) ────────────────────────────────────────────────────
        adv_dollar = compute_rolling_adv(daily, signal_idx)
        if adv_dollar is None:
            count_insufficient_adv += 1
            continue

        adv_bucket = assign_adv_bucket(adv_dollar)
        if adv_bucket not in ADV_ALLOWED_BUCKETS:
            count_adv_gate_fail += 1
            continue

        # ── Signal filter 1: breakdown occurred ───────────────────────────────
        # signal_day_low must be below prior_day_low
        if signal_day_low >= prior_day_low:
            count_no_breakdown += 1
            continue

        # ── Signal filter 2: reclaim occurred ─────────────────────────────────
        # signal_day_close must be above prior_day_low
        if signal_day_close <= prior_day_low:
            count_no_reclaim += 1
            continue

        # ── Signal filter 3: breakdown depth >= 0.5% (locked) ─────────────────
        breakdown_depth_pct = (prior_day_low - signal_day_low) / prior_day_low
        if breakdown_depth_pct < LOCKED_BREAKDOWN_DEPTH_PCT:
            count_depth_fail += 1
            continue

        # ── Signal filter 4: reclaim pct <= 0.2% (locked) ─────────────────────
        reclaim_pct = (signal_day_close - prior_day_low) / prior_day_low
        if reclaim_pct > LOCKED_RECLAIM_PCT:
            count_reclaim_pct_fail += 1
            continue

        count_passing += 1

        # ── Execution template (frozen) ────────────────────────────────────────
        entry_price = signal_day_high   # buy stop at signal_day_high exactly
        stop_price  = signal_day_low    # hard protective stop at signal_day_low exactly
        risk_dollar = entry_price - stop_price
        risk_distance_pct = risk_dollar / entry_price if entry_price > 0 else np.nan

        # ── Warning flags ──────────────────────────────────────────────────────
        warning_flags = []
        if bearish_regime:
            warning_flags.append(BEARISH_CONTEXT_WARNING)
        if risk_distance_pct > 0.10:
            warning_flags.append(f"very_wide_stop_{risk_distance_pct:.1%}")
        if stop_price <= 0:
            warning_flags.append("stop_price_at_or_below_zero")

        signals.append({
            "signal_date":                    signal_date,
            "trade_date":                     str(next_trade_date),
            "ticker":                         ticker,
            "variant_name":                   VARIANT_NAME,
            "family_name":                    FAMILY_NAME,
            "market_regime_label":            market_regime_label,
            "context_confidence":             context_confidence,
            "prior_day_low":                  round(prior_day_low, 4),
            "signal_day_open":                round(signal_day_open, 4),
            "signal_day_high":                round(signal_day_high, 4),
            "signal_day_low":                 round(signal_day_low, 4),
            "signal_day_close":               round(signal_day_close, 4),
            "breakdown_depth_pct":            round(breakdown_depth_pct, 6),
            "reclaim_pct":                    round(reclaim_pct, 6),
            "adv_dollar_approx":              round(adv_dollar, 0),
            "adv_dollar_bucket":              adv_bucket,
            "price_bucket":                   price_bucket,
            "entry_price":                    round(entry_price, 4),
            "stop_price":                     round(stop_price, 4),
            "risk_dollar":                    round(risk_dollar, 4),
            "risk_distance_pct":              round(risk_distance_pct, 4) if not np.isnan(risk_distance_pct) else "",
            "cancel_time_et":                 CANCEL_IF_NOT_TRIGGERED_BY_ET,
            "flatten_time_et":                FORCED_EXIT_TIME_ET,
            "cancel_condition_text":          CANCEL_CONDITION_TEXT,
            "same_day_exit_rule":             SAME_DAY_EXIT_RULE,
            "strategy_character_note":        STRATEGY_CHARACTER_NOTE,
            "research_expectancy_r_no_slip":  RESEARCH_EXPECTANCY_R_NO_SLIP,
            "research_expectancy_r_adj":      RESEARCH_EXPECTANCY_R_ADJ,
            "warning_flags":                  " | ".join(warning_flags) if warning_flags else "",
        })

    # ── Write signal pack ──────────────────────────────────────────────────────
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    date_tag = signal_date.replace("-", "_")
    output_filename = f"signal_pack__failed_breakdown_reclaim__template_002__{date_tag}.csv"
    output_path = OUTPUT_DIR / output_filename

    output_columns = [
        "signal_date", "trade_date", "ticker", "variant_name", "family_name",
        "market_regime_label", "context_confidence",
        "prior_day_low", "signal_day_open", "signal_day_high", "signal_day_low", "signal_day_close",
        "breakdown_depth_pct", "reclaim_pct",
        "adv_dollar_approx", "adv_dollar_bucket", "price_bucket",
        "entry_price", "stop_price", "risk_dollar", "risk_distance_pct",
        "cancel_time_et", "flatten_time_et",
        "cancel_condition_text", "same_day_exit_rule", "strategy_character_note",
        "research_expectancy_r_no_slip", "research_expectancy_r_adj",
        "warning_flags",
    ]

    if signals:
        out_df = pd.DataFrame(signals, columns=output_columns)
        # Sort by breakdown depth descending — deeper traps first
        out_df = out_df.sort_values("breakdown_depth_pct", ascending=False).reset_index(drop=True)
        out_df.to_csv(output_path, index=False)
    else:
        pd.DataFrame(columns=output_columns).to_csv(output_path, index=False)

    # ── Diagnostic summary ─────────────────────────────────────────────────────
    total     = len(tickers)
    with_data = total - count_no_data

    print()
    print("=" * 66)
    print("  SIGNAL SCAN DIAGNOSTIC SUMMARY  [failed_breakdown_reclaim__template_002]")
    print("=" * 66)
    print(f"  total universe tickers:             {total:>6}")
    print(f"  tickers with daily cache data:      {with_data:>6}")
    print(f"  ---")
    print(f"  skipped (no signal-date row):       {count_no_signal_date:>6}")
    print(f"  skipped (no prior row):             {count_no_prev_row:>6}")
    print(f"  skipped (price gate — <$10 or >$100): {count_price_gate_fail:>6}")
    print(f"  skipped (insufficient ADV history): {count_insufficient_adv:>6}")
    print(f"  skipped (ADV gate — small tiers):   {count_adv_gate_fail:>6}")
    print(f"  ---")
    print(f"  failed breakdown filter (cond 1):   {count_no_breakdown:>6}")
    print(f"  failed reclaim filter (cond 2):     {count_no_reclaim:>6}")
    print(f"  failed depth filter (cond 3):       {count_depth_fail:>6}")
    print(f"  failed reclaim_pct filter (cond 4): {count_reclaim_pct_fail:>6}")
    print(f"  ---")
    print(f"  FINAL SIGNAL COUNT:                 {len(signals):>6}")
    print("=" * 66)
    print(f"  signal_date:      {signal_date}")
    print(f"  trade_date:       {next_trade_date}  (next estimated business day)")
    print(f"  regime:           {market_regime_label}  (context_confidence: {context_confidence})")
    print(f"  output file:      {output_filename}")
    print(f"  output path:      {output_path}")
    print("=" * 66)
    print(f"  execution:        activate {ACTIVATE_ORDER_AT_ET} ET | "
          f"cancel {CANCEL_IF_NOT_TRIGGERED_BY_ET} ET | flatten {FORCED_EXIT_TIME_ET} ET")
    print(f"  ADV gate:         {sorted(ADV_ALLOWED_BUCKETS)}")
    print(f"  price gate:       exclude below ${PRICE_EXCLUDE_BELOW:.2f} (price_5_10) | exclude above ${PRICE_EXCLUDE_ABOVE:.2f}")
    print(f"  signal filters:   depth >= {LOCKED_BREAKDOWN_DEPTH_PCT:.1%} | "
          f"reclaim <= {LOCKED_RECLAIM_PCT:.1%}")
    print("=" * 66)

    if signals:
        out_df_check = pd.read_csv(output_path)
        print()
        print("  SIGNAL PACK — TOP 10 BY BREAKDOWN DEPTH:")
        preview_cols = [
            "ticker", "adv_dollar_bucket", "price_bucket",
            "breakdown_depth_pct", "reclaim_pct",
            "entry_price", "stop_price", "risk_distance_pct", "context_confidence",
        ]
        preview = out_df_check[preview_cols].head(10).copy()
        preview["breakdown_depth_pct"] = preview["breakdown_depth_pct"].map(lambda x: f"{x:.3%}")
        preview["reclaim_pct"]         = preview["reclaim_pct"].map(lambda x: f"{x:.3%}")
        preview["risk_distance_pct"]   = preview["risk_distance_pct"].map(
            lambda x: f"{float(x):.1%}" if x != "" else ""
        )
        preview["entry_price"] = preview["entry_price"].map(lambda x: f"{x:.2f}")
        preview["stop_price"]  = preview["stop_price"].map(lambda x: f"{x:.2f}")
        print(preview.to_string(index=False))
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Nightly signal scan: "
            "failed_breakdown_reclaim__weak_reclaim_depth__time_exit_primary__template_002"
        )
    )
    parser.add_argument(
        "--signal-date",
        type=str,
        default=None,
        help="Signal date YYYY-MM-DD. Default: most recent date in market context model.",
    )
    args = parser.parse_args()
    run_scan(signal_date_str=args.signal_date)


if __name__ == "__main__":
    main()
