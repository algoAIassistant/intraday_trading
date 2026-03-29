"""
engineering_nightly_signal_scan__gap_directional_trap__candidate_1_v2.py

track:    plan_next_day_day_trade
family:   gap_directional_trap
variant:  gap_directional_trap__bearish_medium_large__candidate_1_v2

Purpose:
  Nightly signal scan. Runs after market close. Reads repo-native daily data,
  applies the 4-condition filter (unchanged from v1), computes frozen
  entry/stop/target prices, and writes a v2 signal pack CSV for next-day TOS use.

  v2 differs from v1 in execution timing only:
    - Activate buy stop at 13:15 ET (not market open)
    - Cancel if not triggered by 13:30 ET
    - Forced exit at 14:30 ET (not MOC)

Signal logic and price formulas are frozen and identical to candidate_1_v1.

Output:
  engineering_runtime_outputs/plan_next_day_day_trade/
    gap_directional_trap__candidate_1_v2/
      signal_pack__gap_directional_trap__candidate_1_v2__YYYY_MM_DD.csv

Usage:
  python engineering_nightly_signal_scan__gap_directional_trap__candidate_1_v2.py
  python engineering_nightly_signal_scan__gap_directional_trap__candidate_1_v2.py --signal-date 2026-03-24

Handoff source:
  1_0_strategy_research/research_outputs/family_lineages/plan_next_day_day_trade/
    gap_directional_trap/phase_r8_engineering_handoff/
    variant_spec__gap_directional_trap__candidate_1_v2__phase_r8__2026_03_29.yaml

Do NOT add:
  - Telegram delivery
  - scheduler / cron integration
  - broker API calls
  - Alpaca
  - live execution
  - reactive intraday logic
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# ── Repo root resolution ───────────────────────────────────────────────────────
# File location: 2_0_agent_engineering/integrated_strategy_modules/
#                plan_next_day_day_trade/gap_directional_trap__bearish_medium_large__candidate_1_v2/
# parents[0] = gap_directional_trap__bearish_medium_large__candidate_1_v2/
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

# Operational universe: module-specific pre-filtered list.
# Reuses the same operational universe as candidate_1_v1 — signal filter is identical.
# Built by engineering_build_operational_universe__gap_directional_trap__candidate_1_v1.py
# as part of Stage 0. Used by default when present.
OPERATIONAL_UNIVERSE_FILE = (
    ENG_ROOT
    / "engineering_configs"
    / "engineering_operational_universe__gap_directional_trap__candidate_1_v1.csv"
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
    / "gap_directional_trap__candidate_1_v2"
)

# ── Variant identity (frozen) ──────────────────────────────────────────────────
VARIANT_ID = "gap_directional_trap__bearish_medium_large__candidate_1_v2"
FAMILY_NAME = "gap_directional_trap"
PRODUCTION_PRIORITY = 1
RESEARCH_EXPECTANCY_R = 0.773  # v2 validated expectancy (base, no slippage); source: v2_validation_summary__gap_directional_trap__phase_r6__2026_03_29.csv LENS 1. Slippage-adjusted (LENS 7): +0.673R.

# ── Frozen signal-filter thresholds (unchanged from v1) ───────────────────────
CLOSE_LOCATION_THRESHOLD = 0.20
GAP_SMALL_MAX  = 0.015
GAP_MEDIUM_MAX = 0.030

# ── Frozen price formulas (unchanged from v1) ─────────────────────────────────
ENTRY_CLOSE_BUFFER  = 0.002
RANGE_PROXY_FACTOR  = 0.75
TARGET_R_MULTIPLE   = 2.0

# ── v2 execution timing (key difference from v1) ──────────────────────────────
ACTIVATE_ORDER_AT_ET          = "13:15"
CANCEL_IF_NOT_TRIGGERED_BY_ET = "13:30"
FORCED_EXIT_TIME_ET           = "14:30"

SAME_DAY_EXIT_RULE = (
    "Flatten at 14:30 ET — do not hold to close. "
    "Cancel bracket if stop or target already fired before 14:30."
)
CANCEL_CONDITION_TEXT = (
    "Cancel buy stop if not triggered by 13:30 ET."
)
STRATEGY_CHARACTER_NOTE = (
    "Aftermath/trap family — not continuation. "
    "Stock gapped up but closed in the bottom 20% of its range (failed drive). "
    "Activate buy stop at 13:15 ET only. Cancel at 13:30 if not triggered. "
    "Exit at 14:30 ET regardless. Wide safety stop (~4.7% avg risk). "
    "Size positions significantly smaller than a 1-2% stop trade."
)
RISK_2022_WARNING = (
    "2022 structural risk: sustained directional bear markets suppress this mechanism. "
    "Monitor for prolonged bear conditions and reduce exposure manually."
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def next_business_day(d: date) -> date:
    """Return the next calendar business day (Mon–Fri). Does not account for holidays."""
    d = d + timedelta(days=1)
    while d.weekday() >= 5:
        d = d + timedelta(days=1)
    return d


def assign_gap_size_band(gap_pct: float) -> str:
    abs_gap = abs(gap_pct)
    if abs_gap < GAP_SMALL_MAX:
        return "small"
    elif abs_gap < GAP_MEDIUM_MAX:
        return "medium"
    else:
        return "large"


def load_universe(full_universe: bool = False) -> list[str]:
    """
    Load the ticker list to scan.
    Default: use operational universe (~1,400 tickers) if present.
    Reuses v1 operational universe — same signal filter, same eligible tickers.
    """
    if not full_universe and OPERATIONAL_UNIVERSE_FILE.exists():
        df = pd.read_csv(OPERATIONAL_UNIVERSE_FILE, dtype={"ticker": str})
        tickers = df["ticker"].dropna().str.strip().str.upper().tolist()
        print(
            f"[universe] operational universe: {len(tickers)} tickers  "
            f"(source: {OPERATIONAL_UNIVERSE_FILE.name})"
        )
        return tickers

    if not full_universe and not OPERATIONAL_UNIVERSE_FILE.exists():
        print(
            "[universe] operational universe file not found — falling back to full shared universe.\n"
            f"           Expected: {OPERATIONAL_UNIVERSE_FILE}"
        )

    df = pd.read_csv(UNIVERSE_FILE)
    tickers = df["ticker"].dropna().tolist()
    print(
        f"[universe] full shared universe: {len(tickers)} tickers  "
        f"(source: {UNIVERSE_FILE.name})"
    )
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


# ── Main scan ──────────────────────────────────────────────────────────────────

def run_scan(signal_date_str: str | None = None, full_universe: bool = False) -> None:

    tickers = load_universe(full_universe=full_universe)
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

    regime_is_bearish = (market_regime_label == "bearish")
    if not regime_is_bearish:
        print(f"    [NOTE] Regime is '{market_regime_label}' — candidate_1_v2 requires 'bearish'.")
        print(f"           No signals generated. Writing empty signal pack.")

    next_trade_date = next_business_day(signal_dt)
    print(f"[5] Next trade date (estimated): {next_trade_date}")

    print(f"\n[6] Scanning {len(tickers)} tickers...")

    count_no_data       = 0
    count_no_signal_date = 0
    count_no_prev_row   = 0
    count_zero_range    = 0
    count_passing_gap_up      = 0
    count_passing_cl_low      = 0
    count_passing_regime      = 0
    count_passing_size_band   = 0

    signals = []

    for ticker in tickers:
        daily = load_daily_parquet(ticker)

        if daily is None:
            count_no_data += 1
            continue

        if signal_date not in daily.index:
            count_no_signal_date += 1
            continue

        date_list = list(daily.index)
        signal_idx = date_list.index(signal_date)

        if signal_idx == 0:
            count_no_prev_row += 1
            continue

        signal_row = daily.loc[signal_date]
        prev_row   = daily.iloc[signal_idx - 1]

        signal_day_open = float(signal_row["open"])
        prev_close      = float(prev_row["close"])

        if prev_close <= 0:
            count_no_data += 1
            continue

        gap_pct       = (signal_day_open - prev_close) / prev_close
        gap_direction = "gap_up" if gap_pct > 0 else "gap_down"

        # Condition 1: gap_up
        if gap_direction != "gap_up":
            continue
        count_passing_gap_up += 1

        # Condition 2: close_location < 0.20
        signal_day_high  = float(signal_row["high"])
        signal_day_low   = float(signal_row["low"])
        signal_day_close = float(signal_row["close"])
        signal_day_range_dollar = signal_day_high - signal_day_low

        if signal_day_range_dollar <= 0:
            count_zero_range += 1
            continue

        close_location = (signal_day_close - signal_day_low) / signal_day_range_dollar

        if close_location >= CLOSE_LOCATION_THRESHOLD:
            continue
        count_passing_cl_low += 1

        # Condition 3: bearish regime (global gate)
        if not regime_is_bearish:
            continue
        count_passing_regime += 1

        # Condition 4: gap_size_band in {medium, large}
        gap_size_band = assign_gap_size_band(gap_pct)
        if gap_size_band not in ("medium", "large"):
            continue
        count_passing_size_band += 1

        # Price formulas (frozen — identical to v1)
        entry_price = signal_day_close * (1.0 + ENTRY_CLOSE_BUFFER)
        risk_dollar = RANGE_PROXY_FACTOR * signal_day_range_dollar
        stop_price  = entry_price - risk_dollar
        target_price = entry_price + (TARGET_R_MULTIPLE * risk_dollar)
        risk_pct    = risk_dollar / entry_price

        position_sizing_note = (
            f"shares = account_risk_$ / {risk_dollar:.2f}; "
            f"risk_pct = {risk_pct:.1%} (wide — size significantly smaller than a 1-2% stop trade)"
        )

        warning_flags = []
        if risk_pct > 0.10:
            warning_flags.append(f"very_wide_stop_{risk_pct:.1%}")
        if signal_day_close < 5.0:
            warning_flags.append("low_priced_stock_lt_5")
        if stop_price <= 0:
            warning_flags.append("stop_price_below_zero")

        signals.append({
            "signal_date":                    signal_date,
            "trade_date":                     str(next_trade_date),
            "ticker":                         ticker,
            "variant_id":                     VARIANT_ID,
            "family_name":                    FAMILY_NAME,
            "deployable_variant_name":        VARIANT_ID,
            "production_priority":            PRODUCTION_PRIORITY,
            "market_regime_label":            market_regime_label,
            "gap_size_band":                  gap_size_band,
            "gap_pct":                        round(gap_pct, 6),
            "close_location":                 round(close_location, 4),
            "signal_day_close":               round(signal_day_close, 4),
            "signal_day_high":                round(signal_day_high, 4),
            "signal_day_low":                 round(signal_day_low, 4),
            "signal_day_range_dollar":        round(signal_day_range_dollar, 4),
            "entry_price":                    round(entry_price, 4),
            "stop_price":                     round(stop_price, 4),
            "target_price":                   round(target_price, 4),
            "risk_dollar":                    round(risk_dollar, 4),
            "risk_pct":                       round(risk_pct, 4),
            "activate_order_at_et":           ACTIVATE_ORDER_AT_ET,
            "cancel_if_not_triggered_by_et":  CANCEL_IF_NOT_TRIGGERED_BY_ET,
            "forced_exit_time_et":            FORCED_EXIT_TIME_ET,
            "same_day_exit_rule":             SAME_DAY_EXIT_RULE,
            "cancel_condition_text":          CANCEL_CONDITION_TEXT,
            "strategy_character_note":        STRATEGY_CHARACTER_NOTE,
            "research_expectancy_r":          RESEARCH_EXPECTANCY_R,
            "position_sizing_note":           position_sizing_note,
            "warning_flags":                  "; ".join(warning_flags) if warning_flags else "",
        })

    # Write signal pack
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    date_tag = signal_date.replace("-", "_")
    output_filename = f"signal_pack__gap_directional_trap__candidate_1_v2__{date_tag}.csv"
    output_path = OUTPUT_DIR / output_filename

    output_columns = [
        "signal_date", "trade_date", "ticker", "variant_id", "family_name",
        "deployable_variant_name", "production_priority", "market_regime_label",
        "gap_size_band", "gap_pct", "close_location", "signal_day_close",
        "signal_day_high", "signal_day_low", "signal_day_range_dollar",
        "entry_price", "stop_price", "target_price", "risk_dollar", "risk_pct",
        "activate_order_at_et", "cancel_if_not_triggered_by_et", "forced_exit_time_et",
        "same_day_exit_rule", "cancel_condition_text", "strategy_character_note",
        "research_expectancy_r", "position_sizing_note", "warning_flags",
    ]

    if signals:
        out_df = pd.DataFrame(signals, columns=output_columns)
        out_df = out_df.sort_values("gap_pct", ascending=False).reset_index(drop=True)
        out_df.to_csv(output_path, index=False)
    else:
        pd.DataFrame(columns=output_columns).to_csv(output_path, index=False)

    # Diagnostics
    total = len(tickers)
    with_data = total - count_no_data
    with_signal_date = with_data - count_no_signal_date - count_no_prev_row - count_zero_range

    print()
    print("=" * 62)
    print("  SIGNAL SCAN DIAGNOSTIC SUMMARY  [candidate_1_v2]")
    print("=" * 62)
    print(f"  total universe tickers:          {total:>6}")
    print(f"  tickers with daily cache data:   {with_data:>6}")
    print(f"  tickers with signal-date row:    {with_signal_date:>6}")
    print(f"  ---")
    print(f"  passing gap_up (cond 1):         {count_passing_gap_up:>6}")
    print(f"  passing cl_low_020 (cond 2):     {count_passing_cl_low:>6}")
    print(f"  passing bearish regime (cond 3): {count_passing_regime:>6}")
    print(f"  passing size_band (cond 4):      {count_passing_size_band:>6}")
    print(f"  ---")
    print(f"  FINAL SIGNAL COUNT:              {len(signals):>6}")
    print("=" * 62)
    print(f"  signal_date:    {signal_date}")
    print(f"  trade_date:     {next_trade_date}  (next estimated business day)")
    print(f"  regime:         {market_regime_label}")
    print(f"  output file:    {output_path.name}")
    print(f"  output path:    {output_path}")
    print("=" * 62)
    print(f"  v2 activation:  {ACTIVATE_ORDER_AT_ET} ET")
    print(f"  v2 cancel:      {CANCEL_IF_NOT_TRIGGERED_BY_ET} ET if not triggered")
    print(f"  v2 exit:        {FORCED_EXIT_TIME_ET} ET forced flatten")
    print("=" * 62)
    print(f"  NOTE: {RISK_2022_WARNING}")
    print("=" * 62)

    if signals:
        out_df_check = pd.read_csv(output_path)
        print()
        print("  SIGNAL PACK — TOP 10 BY GAP SIZE:")
        preview_cols = [
            "ticker", "gap_size_band", "gap_pct", "close_location",
            "entry_price", "stop_price", "target_price", "risk_pct",
        ]
        preview = out_df_check[preview_cols].head(10).copy()
        preview["gap_pct"]        = preview["gap_pct"].map(lambda x: f"{x:.2%}")
        preview["close_location"] = preview["close_location"].map(lambda x: f"{x:.3f}")
        preview["risk_pct"]       = preview["risk_pct"].map(lambda x: f"{x:.1%}")
        preview["entry_price"]    = preview["entry_price"].map(lambda x: f"{x:.2f}")
        preview["stop_price"]     = preview["stop_price"].map(lambda x: f"{x:.2f}")
        preview["target_price"]   = preview["target_price"].map(lambda x: f"{x:.2f}")
        print(preview.to_string(index=False))
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Nightly signal scan: gap_directional_trap__bearish_medium_large__candidate_1_v2"
    )
    parser.add_argument(
        "--signal-date",
        type=str,
        default=None,
        help="Signal date YYYY-MM-DD. Default: most recent date in market context model.",
    )
    parser.add_argument(
        "--full-universe",
        action="store_true",
        help="Use full shared master universe instead of operational universe.",
    )
    args = parser.parse_args()
    run_scan(signal_date_str=args.signal_date, full_universe=args.full_universe)


if __name__ == "__main__":
    main()
