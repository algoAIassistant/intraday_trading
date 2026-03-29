"""
engineering_selection_layer__gap_directional_trap__candidate_1_v2.py

track:    plan_next_day_day_trade
family:   gap_directional_trap
variant:  gap_directional_trap__bearish_medium_large__candidate_1_v2

Purpose:
  Operator-facing selection layer. Reads the raw v2 signal pack, applies
  hard operator filters (US common stock, price $20-$100, ADV20 >= $2M),
  computes a transparent selection score, assigns operator price buckets, and
  selects up to 3 signals for manual TOS next-day execution.

  This module does NOT modify the raw signal pack.

Inputs:
  Raw signal pack:
    engineering_runtime_outputs/plan_next_day_day_trade/
      gap_directional_trap__candidate_1_v2/
        signal_pack__gap_directional_trap__candidate_1_v2__YYYY_MM_DD.csv

  Shared universe metadata (for type='CS' confirmation):
    0_1_shared_master_universe/shared_metadata/shared_master_metadata_us_common_stocks.csv

  Daily price cache (for ADV and RVOL):
    1_0_strategy_research/research_data_cache/daily/<ticker>.parquet

Outputs:
  engineering_runtime_outputs/plan_next_day_day_trade/
    gap_directional_trap__candidate_1_v2/
      ranked_signal_pack__gap_directional_trap__candidate_1_v2__YYYY_MM_DD.csv
      selected_top_3__gap_directional_trap__candidate_1_v2__YYYY_MM_DD.csv
      selection_summary__gap_directional_trap__candidate_1_v2__YYYY_MM_DD.md

Usage:
  python engineering_selection_layer__gap_directional_trap__candidate_1_v2.py
  python engineering_selection_layer__gap_directional_trap__candidate_1_v2.py --signal-date 2026-03-24
"""

import argparse
import math
import sys
from pathlib import Path

import pandas as pd

# ── Repo root resolution ───────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[4]

# ── Data paths ─────────────────────────────────────────────────────────────────
UNIVERSE_METADATA_FILE = (
    REPO_ROOT
    / "0_1_shared_master_universe"
    / "shared_metadata"
    / "shared_master_metadata_us_common_stocks.csv"
)
DAILY_CACHE_DIR = REPO_ROOT / "1_0_strategy_research" / "research_data_cache" / "daily"
SIGNAL_PACK_DIR = (
    REPO_ROOT
    / "2_0_agent_engineering"
    / "engineering_runtime_outputs"
    / "plan_next_day_day_trade"
    / "gap_directional_trap__candidate_1_v2"
)
OUTPUT_DIR = SIGNAL_PACK_DIR

VARIANT_ID = "gap_directional_trap__bearish_medium_large__candidate_1_v2"

# ── Hard filter thresholds (same as v1) ───────────────────────────────────────
PRICE_MIN     = 20.0
PRICE_MAX     = 100.0
ADV_DOLLAR_MIN = 2_000_000.0
ADV_LOOKBACK_DAYS = 20

# ── Operator price buckets ─────────────────────────────────────────────────────
PRICE_BUCKETS = [
    ("20_to_30",   20.0,  30.0),
    ("30_to_50",   30.0,  50.0),
    ("50_to_70",   50.0,  70.0),
    ("70_to_100",  70.0, 100.001),
]

# ── Score component weights (same as v1) ──────────────────────────────────────
W_ADV       = 0.30
W_CLOSE_LOC = 0.30
W_RISK_PCT  = 0.25
W_RVOL      = 0.15

_ADV_LOG_FLOOR = math.log10(ADV_DOLLAR_MIN)
_ADV_LOG_CEIL  = math.log10(100_000_000.0)

RISK_PCT_CEILING       = 0.10
RVOL_CAP               = 2.0
PENALTY_VERY_WIDE_STOP = 0.15
PENALTY_STOP_BELOW_ZERO = 0.25

MAX_DELIVERY = 3


# ── Data loaders ───────────────────────────────────────────────────────────────

def load_us_common_stock_set() -> set:
    df = pd.read_csv(UNIVERSE_METADATA_FILE, dtype={"ticker": str})
    confirmed = df[(df["type"] == "CS") & (df["locale"] == "us")]["ticker"]
    return set(confirmed.str.strip().str.upper())


def load_raw_signal_pack(signal_date: str) -> pd.DataFrame:
    date_str = signal_date.replace("-", "_")
    filename = f"signal_pack__gap_directional_trap__candidate_1_v2__{date_str}.csv"
    path = SIGNAL_PACK_DIR / filename
    if not path.exists():
        print(f"[ERROR] raw signal pack not found: {path}")
        print(f"        Run engineering_nightly_signal_scan first for {signal_date}.")
        sys.exit(1)
    return pd.read_csv(path, dtype={"ticker": str})


def load_daily_parquet(ticker: str) -> pd.DataFrame | None:
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


def compute_adv_and_rvol(ticker: str, signal_date: str) -> tuple:
    df = load_daily_parquet(ticker)
    if df is None:
        return None, None
    idx_list = list(df.index)
    if signal_date not in idx_list:
        return None, None
    sig_pos = idx_list.index(signal_date)
    if sig_pos == 0:
        return None, None
    df_prior = df.iloc[:sig_pos].copy()
    if df_prior.empty:
        return None, None
    df_prior["dollar_vol"] = df_prior["close"] * df_prior["volume"]
    adv = df_prior["dollar_vol"].tail(ADV_LOOKBACK_DAYS).mean()
    sig_row = df.loc[signal_date]
    sig_dollar_vol = float(sig_row["close"]) * float(sig_row["volume"])
    rvol = sig_dollar_vol / adv if adv and adv > 0 else None
    return float(adv), rvol


# ── Scoring functions ──────────────────────────────────────────────────────────

def score_adv(adv: float) -> float:
    if adv <= 0:
        return 0.0
    raw = (math.log10(adv) - _ADV_LOG_FLOOR) / (_ADV_LOG_CEIL - _ADV_LOG_FLOOR)
    return max(0.0, min(1.0, raw))


def score_close_location(cl: float) -> float:
    return max(0.0, min(1.0, (0.20 - cl) / 0.20))


def score_risk_pct(risk_pct: float) -> float:
    return max(0.0, 1.0 - (risk_pct / RISK_PCT_CEILING))


def score_rvol(rvol: float) -> float:
    return min(rvol / RVOL_CAP, 1.0)


def compute_flag_penalty(warning_flags_val) -> float:
    if pd.isna(warning_flags_val) or not str(warning_flags_val).strip():
        return 0.0
    flags = str(warning_flags_val)
    penalty = 0.0
    if "very_wide_stop" in flags:
        penalty += PENALTY_VERY_WIDE_STOP
    if "stop_price_below_zero" in flags:
        penalty += PENALTY_STOP_BELOW_ZERO
    return penalty


def assign_price_bucket(close: float) -> str | None:
    for label, low, high in PRICE_BUCKETS:
        if low <= close < high:
            return label
    return None


# ── Main selection logic ───────────────────────────────────────────────────────

def run_selection(signal_date: str) -> None:
    print(f"\n{'='*72}")
    print(f"  gap_directional_trap  |  CANDIDATE_1_V2  |  selection layer")
    print(f"  signal_date: {signal_date}")
    print(f"{'='*72}\n")

    us_cs_tickers = load_us_common_stock_set()
    raw_df = load_raw_signal_pack(signal_date)
    total_raw = len(raw_df)
    print(f"[load]   raw signal pack rows:                 {total_raw}")

    out = raw_df.copy()
    out["us_common_stock_confirmed"]    = False
    out["price_bucket_operator"]        = None
    out["avg_daily_dollar_volume"]      = None
    out["relative_volume"]              = None
    out["adv_dollar_score"]             = None
    out["close_location_score"]         = None
    out["risk_pct_score"]               = None
    out["rvol_score"]                   = None
    out["flag_penalty"]                 = None
    out["selection_score"]              = None
    out["selection_rank_within_bucket"] = None
    out["selection_rank_overall"]       = None
    out["selected_for_delivery"]        = False
    out["exclusion_reason"]             = ""

    excluded_not_cs   = []
    excluded_price    = []
    excluded_adv      = []
    candidate_indices = []

    for idx, row in out.iterrows():
        ticker = str(row["ticker"]).strip().upper()
        close  = float(row["signal_day_close"])

        if ticker not in us_cs_tickers:
            out.at[idx, "exclusion_reason"] = "not_us_common_stock"
            excluded_not_cs.append(ticker)
            continue
        out.at[idx, "us_common_stock_confirmed"] = True

        if not (PRICE_MIN <= close <= PRICE_MAX):
            out.at[idx, "exclusion_reason"] = "price_outside_20_to_100"
            excluded_price.append(ticker)
            continue

        adv, rvol = compute_adv_and_rvol(ticker, signal_date)
        if adv is None or adv < ADV_DOLLAR_MIN:
            out.at[idx, "exclusion_reason"] = (
                f"adv_below_{ADV_DOLLAR_MIN / 1_000_000:.0f}m_dollar_threshold"
            )
            out.at[idx, "avg_daily_dollar_volume"] = adv
            excluded_adv.append((ticker, adv))
            continue

        out.at[idx, "avg_daily_dollar_volume"] = adv
        out.at[idx, "relative_volume"]         = rvol
        candidate_indices.append(idx)

    n_us_confirmed = int(out["us_common_stock_confirmed"].sum())
    n_price_pass   = n_us_confirmed - len(excluded_price)
    n_candidates   = len(candidate_indices)

    print(f"[filter] excluded (not us common stock):       {len(excluded_not_cs)}")
    print(f"[filter] confirmed us common stock:            {n_us_confirmed}")
    print(f"[filter] excluded (price outside 20-100):      {len(excluded_price)}")
    print(f"[filter] pass price filter:                    {n_price_pass}")
    print(
        f"[filter] excluded (adv < ${ADV_DOLLAR_MIN / 1_000_000:.0f}M / {ADV_LOOKBACK_DAYS}d):"
        f"  {len(excluded_adv)}"
    )
    for ticker, adv in excluded_adv:
        adv_str = f"${adv / 1_000_000:.2f}M" if adv is not None else "N/A"
        print(f"           {ticker}: ADV20 = {adv_str}")
    print(f"[filter] candidates for scoring:               {n_candidates}")
    print()

    if n_candidates == 0:
        print("[result] no candidates survived filters — writing empty selected_top_3\n")
        _write_empty_outputs(signal_date, raw_df)
        return

    # Score candidates
    for idx in candidate_indices:
        row    = out.loc[idx]
        adv    = float(row["avg_daily_dollar_volume"])
        rvol   = float(row["relative_volume"]) if pd.notna(row["relative_volume"]) else 0.0
        cl     = float(row["close_location"])
        rp     = float(row["risk_pct"])
        flags  = row["warning_flags"]

        s_adv   = score_adv(adv)
        s_cl    = score_close_location(cl)
        s_risk  = score_risk_pct(rp)
        s_rvol  = score_rvol(rvol)
        penalty = compute_flag_penalty(flags)

        raw_score   = W_ADV * s_adv + W_CLOSE_LOC * s_cl + W_RISK_PCT * s_risk + W_RVOL * s_rvol
        final_score = raw_score - penalty

        out.at[idx, "adv_dollar_score"]     = round(s_adv,       4)
        out.at[idx, "close_location_score"] = round(s_cl,        4)
        out.at[idx, "risk_pct_score"]       = round(s_risk,      4)
        out.at[idx, "rvol_score"]           = round(s_rvol,      4)
        out.at[idx, "flag_penalty"]         = round(penalty,     4)
        out.at[idx, "selection_score"]      = round(final_score, 4)
        out.at[idx, "price_bucket_operator"] = assign_price_bucket(float(row["signal_day_close"]))

    cand_df = out.loc[candidate_indices].copy().sort_values("selection_score", ascending=False)
    for rank, idx in enumerate(cand_df.index, start=1):
        out.at[idx, "selection_rank_overall"] = rank

    for bucket_label, _, _ in PRICE_BUCKETS:
        bucket_rows = cand_df[cand_df["price_bucket_operator"] == bucket_label]
        for rank, idx in enumerate(bucket_rows.index, start=1):
            out.at[idx, "selection_rank_within_bucket"] = rank

    bucket_leaders = []
    for bucket_label, _, _ in PRICE_BUCKETS:
        bucket_rows = cand_df[cand_df["price_bucket_operator"] == bucket_label]
        if not bucket_rows.empty:
            leader_idx = bucket_rows.index[0]
            bucket_leaders.append((leader_idx, float(out.at[leader_idx, "selection_score"])))

    bucket_leaders.sort(key=lambda x: x[1], reverse=True)
    final_indices = [idx for idx, _ in bucket_leaders[:MAX_DELIVERY]]

    for idx in final_indices:
        out.at[idx, "selected_for_delivery"] = True

    n_buckets_occupied = len(bucket_leaders)
    n_selected         = len(final_indices)

    print(f"[score]  candidates scored:                    {n_candidates}")
    print(f"[score]  price buckets occupied:               {n_buckets_occupied}")
    print(f"[score]  signals selected for delivery:        {n_selected}")
    print()

    selected_df = out.loc[final_indices].sort_values("selection_score", ascending=False)
    hdr = f"  {'#':<3} {'Ticker':<7} {'Bucket':<13} {'Close':>7} {'Entry':>7} {'Stop':>7} {'Target':>8} {'Risk%':>6} {'RVOL':>5} {'ADV$M':>7} {'Score':>7}"
    print("  SELECTED SIGNALS:")
    print(hdr)
    print(f"  {'-'*78}")
    for rank, (_, row) in enumerate(selected_df.iterrows(), start=1):
        adv_m  = float(row["avg_daily_dollar_volume"]) / 1_000_000 if pd.notna(row["avg_daily_dollar_volume"]) else 0.0
        rvol_v = float(row["relative_volume"]) if pd.notna(row["relative_volume"]) else 0.0
        print(
            f"  {rank:<3} {row['ticker']:<7} {str(row['price_bucket_operator']):<13} "
            f"{float(row['signal_day_close']):>7.2f} {float(row['entry_price']):>7.2f} "
            f"{float(row['stop_price']):>7.2f} {float(row['target_price']):>8.2f} "
            f"{float(row['risk_pct']) * 100:>5.1f}% {rvol_v:>5.2f} "
            f"{adv_m:>6.1f}M {float(row['selection_score']):>7.4f}"
        )
    print()

    # Write outputs
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = signal_date.replace("-", "_")

    ranked_path = OUTPUT_DIR / f"ranked_signal_pack__gap_directional_trap__candidate_1_v2__{date_str}.csv"
    out.to_csv(ranked_path, index=False)
    print(f"[output] ranked_signal_pack  -> {ranked_path.name}")

    top3_cols = [
        "ticker", "signal_date", "trade_date", "variant_id",
        "price_bucket_operator",
        "market_regime_label", "gap_size_band", "gap_pct",
        "signal_day_close", "signal_day_high", "signal_day_low",
        "signal_day_range_dollar",
        "close_location",
        "entry_price", "stop_price", "target_price",
        "risk_dollar", "risk_pct",
        "activate_order_at_et", "cancel_if_not_triggered_by_et", "forced_exit_time_et",
        "same_day_exit_rule", "cancel_condition_text",
        "warning_flags",
        "avg_daily_dollar_volume", "relative_volume",
        "adv_dollar_score", "close_location_score", "risk_pct_score",
        "rvol_score", "flag_penalty", "selection_score",
        "selection_rank_within_bucket", "selection_rank_overall",
        "selected_for_delivery",
        "research_expectancy_r", "position_sizing_note",
    ]
    top3_df = (
        out.loc[final_indices, top3_cols]
        .sort_values("selection_score", ascending=False)
        .reset_index(drop=True)
    )
    top3_path = OUTPUT_DIR / f"selected_top_3__gap_directional_trap__candidate_1_v2__{date_str}.csv"
    top3_df.to_csv(top3_path, index=False)
    print(f"[output] selected_top_3      -> {top3_path.name}")

    summary_path = OUTPUT_DIR / f"selection_summary__gap_directional_trap__candidate_1_v2__{date_str}.md"
    trade_date_str = str(raw_df["trade_date"].iloc[0]) if not raw_df.empty else "N/A"
    _write_summary(
        summary_path, signal_date, trade_date_str, date_str,
        total_raw, len(excluded_not_cs), n_us_confirmed,
        len(excluded_price), n_price_pass, excluded_adv, n_candidates,
        n_buckets_occupied, n_selected, selected_df,
    )
    print(f"[output] selection_summary   -> {summary_path.name}")
    print()
    print(f"[done]   selection complete  signal_date={signal_date}\n")


def _write_empty_outputs(signal_date: str, raw_df: pd.DataFrame) -> None:
    """Write empty selected_top_3 when no candidates survive filters."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    date_str   = signal_date.replace("-", "_")
    empty_cols = ["ticker", "signal_date", "trade_date", "variant_id", "selected_for_delivery"]
    top3_path  = OUTPUT_DIR / f"selected_top_3__gap_directional_trap__candidate_1_v2__{date_str}.csv"
    pd.DataFrame(columns=empty_cols).to_csv(top3_path, index=False)
    print(f"[output] selected_top_3 (empty) -> {top3_path.name}")


def _write_summary(
    path, signal_date, trade_date_str, date_str,
    total_raw, n_not_cs, n_us_confirmed,
    n_excl_price, n_price_pass, excluded_adv, n_candidates,
    n_buckets_occupied, n_selected, selected_df,
):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# selection_summary__gap_directional_trap__candidate_1_v2__{date_str}\n\n")
        f.write(f"signal_date:   {signal_date}\n")
        f.write(f"trade_date:    {trade_date_str}\n")
        f.write(f"variant_id:    {VARIANT_ID}\n\n")
        f.write("---\n\n")

        f.write("## Filter funnel\n\n")
        f.write("| step | count |\n|------|-------|\n")
        f.write(f"| raw signal pack | {total_raw} |\n")
        f.write(f"| excluded (not us common stock) | {n_not_cs} |\n")
        f.write(f"| confirmed us common stock | {n_us_confirmed} |\n")
        f.write(f"| excluded (price outside 20-100) | {n_excl_price} |\n")
        f.write(f"| pass price filter | {n_price_pass} |\n")
        f.write(f"| excluded (ADV20 < ${ADV_DOLLAR_MIN / 1_000_000:.0f}M) | {len(excluded_adv)} |\n")
        f.write(f"| candidates for scoring | {n_candidates} |\n")
        f.write(f"| price buckets occupied | {n_buckets_occupied} |\n")
        f.write(f"| selected for delivery | {n_selected} |\n\n")

        f.write("## Score weights and formulas\n\n")
        f.write("| component | weight | formula |\n|-----------|--------|--------|\n")
        f.write(f"| adv_dollar_score | {W_ADV:.0%} | log10 scale; floor = ${ADV_DOLLAR_MIN / 1_000_000:.0f}M, ceil = $100M |\n")
        f.write(f"| close_location_score | {W_CLOSE_LOC:.0%} | (0.20 - close_location) / 0.20 |\n")
        f.write(f"| risk_pct_score | {W_RISK_PCT:.0%} | max(0, 1 - risk_pct / {RISK_PCT_CEILING:.0%}) |\n")
        f.write(f"| rvol_score | {W_RVOL:.0%} | min(rvol_20 / {RVOL_CAP:.1f}, 1.0) |\n\n")

        if n_selected > 0:
            f.write("## Selected signals\n\n")
            f.write("| # | ticker | bucket | close | entry | stop | target | risk_pct | rvol | adv_dollar | score |\n")
            f.write("|---|--------|--------|-------|-------|------|--------|----------|------|------------|-------|\n")
            for rank, (_, row) in enumerate(selected_df.iterrows(), start=1):
                adv_m  = float(row["avg_daily_dollar_volume"]) / 1_000_000 if pd.notna(row["avg_daily_dollar_volume"]) else 0.0
                rvol_v = float(row["relative_volume"]) if pd.notna(row["relative_volume"]) else 0.0
                f.write(
                    f"| {rank} | {row['ticker']} | {row['price_bucket_operator']} | "
                    f"${float(row['signal_day_close']):.2f} | ${float(row['entry_price']):.2f} | "
                    f"${float(row['stop_price']):.2f} | ${float(row['target_price']):.2f} | "
                    f"{float(row['risk_pct']) * 100:.1f}% | {rvol_v:.2f} | "
                    f"${adv_m:.1f}M | {float(row['selection_score']):.4f} |\n"
                )
            f.write("\n---\n\n")
        f.write(
            f"Bucket leaders: one highest-scoring signal per occupied price bucket; "
            f"top {MAX_DELIVERY} bucket leaders selected for delivery.\n"
        )


# ── CLI entry point ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Selection layer for gap_directional_trap candidate_1_v2"
    )
    parser.add_argument(
        "--signal-date",
        type=str,
        default=None,
        help="Signal date YYYY-MM-DD. Defaults to latest raw signal pack.",
    )
    args = parser.parse_args()

    if args.signal_date:
        signal_date = args.signal_date
    else:
        packs = sorted(
            SIGNAL_PACK_DIR.glob("signal_pack__gap_directional_trap__candidate_1_v2__*.csv")
        )
        if not packs:
            print("[ERROR] no raw signal pack found — run the nightly scan first")
            sys.exit(1)
        latest = packs[-1]
        date_part = latest.stem.split("__")[-1]
        signal_date = date_part.replace("_", "-")
        print(f"[auto]   using latest signal pack: {latest.name}")

    run_selection(signal_date)


if __name__ == "__main__":
    main()
