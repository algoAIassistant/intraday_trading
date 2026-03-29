"""
research_run_child_001_phase_r3_strategy_formalization.py
Track:  intraday_same_day
Family: failed_opening_drive_and_reclaim
Phase:  phase_r3 — strategy formalization

Purpose:
  Test multiple formal execution rule variants against the 873 validated
  child_001 reclaim events. Identifies the strongest phase_r3 candidate
  rule set for advancement to phase_r4 robustness testing.

Input:
  child_001 session_detail CSV (events where condition_met=True)
  Intraday 1-min parquet cache (for post-reclaim path simulation)

Variants tested:
  V1: Any reclaim | No stop            | No target | Hold to close  (baseline)
  V2: Any reclaim | Struct stop (open) | No target | Hold to close
  V3: Any reclaim | Hard stop -1.5%   | No target | Hold to close
  V4: Early only  | No stop            | No target | Hold to close
  V5: Early only  | Struct stop (open) | No target | Hold to close
  V6: Any reclaim | Struct stop (open) | +2.0% tgt | Hold remainder to close
  V7: Any reclaim | Hard stop -1.5%   | +2.0% tgt | Hold remainder to close

Simulation rules:
  Entry price : failure_bar_close from child_001 session_detail CSV
  Stop trigger: bar.low  <= stop_price  → exit at stop_price  (conservative fill)
  Tgt trigger : bar.high >= tgt_price   → exit at tgt_price
  Conflict (stop + tgt same bar): stop takes priority
  Default exit: session close bar close price

Output (research_outputs/.../phase_r3_strategy_formalization/):
  phase_r3__variant_comparison__<DATE>.csv
  phase_r3__V<N>__event_detail__<DATE>.csv  (one per variant)
  phase_r3__formalization_report__<DATE>.txt
"""

import os
import sys
import glob as glob_mod
import datetime
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT  = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", "..", "..", ".."))
CACHE_DIR  = os.path.join(REPO_ROOT, "1_0_strategy_research", "research_data_cache", "intraday_1m")

_LINEAGE = os.path.join(
    REPO_ROOT, "1_0_strategy_research", "research_outputs",
    "family_lineages", "failed_opening_drive_and_reclaim",
)
CHILD001_DIR = os.path.join(_LINEAGE, "child_001_price_filtered_regime_gated")
OUTPUT_DIR   = os.path.join(_LINEAGE, "phase_r3_strategy_formalization")
os.makedirs(OUTPUT_DIR, exist_ok=True)

TODAY = datetime.date.today().strftime("%Y_%m_%d")

# ---------------------------------------------------------------------------
# Session constants — must match family definition
# ---------------------------------------------------------------------------

SESSION_START = "09:30"
SESSION_END   = "15:59"
DRIVE_MINUTES = 30         # drive window = first 30 bars of session
EARLY_RECLAIM_MAX = 60     # matches child_001 early_reclaim_max

# ---------------------------------------------------------------------------
# Variant definitions
# ---------------------------------------------------------------------------

VARIANTS = [
    {
        "id":         "V1",
        "label":      "Any reclaim | No stop | Hold to close",
        "early_only": False,
        "stop_type":  "none",
        "stop_pct":   None,
        "target_pct": None,
    },
    {
        "id":         "V2",
        "label":      "Any reclaim | Structural stop (session_open) | Hold to close",
        "early_only": False,
        "stop_type":  "structural",
        "stop_pct":   None,
        "target_pct": None,
    },
    {
        "id":         "V3",
        "label":      "Any reclaim | Hard stop -1.5% | Hold to close",
        "early_only": False,
        "stop_type":  "hard",
        "stop_pct":   1.5,
        "target_pct": None,
    },
    {
        "id":         "V4",
        "label":      "Early only (<=60 bars) | No stop | Hold to close",
        "early_only": True,
        "stop_type":  "none",
        "stop_pct":   None,
        "target_pct": None,
    },
    {
        "id":         "V5",
        "label":      "Early only (<=60 bars) | Structural stop | Hold to close",
        "early_only": True,
        "stop_type":  "structural",
        "stop_pct":   None,
        "target_pct": None,
    },
    {
        "id":         "V6",
        "label":      "Any reclaim | Structural stop | +2.0% target | Hold remainder",
        "early_only": False,
        "stop_type":  "structural",
        "stop_pct":   None,
        "target_pct": 2.0,
    },
    {
        "id":         "V7",
        "label":      "Any reclaim | Hard stop -1.5% | +2.0% target | Hold remainder",
        "early_only": False,
        "stop_type":  "hard",
        "stop_pct":   1.5,
        "target_pct": 2.0,
    },
]

# ---------------------------------------------------------------------------
# Cache loader
# ---------------------------------------------------------------------------

_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def _safe_cache_path(ticker: str) -> str:
    stem = f"{ticker}__reserved" if ticker.upper() in _WIN_RESERVED else ticker
    return os.path.join(CACHE_DIR, f"{stem}.parquet")


def load_ticker_cache(ticker: str) -> pd.DataFrame | None:
    path = _safe_cache_path(ticker)
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert("America/New_York")
    return df

# ---------------------------------------------------------------------------
# Trade simulation
# ---------------------------------------------------------------------------

def simulate_trade(
    post_entry_bars: pd.DataFrame,
    entry_price: float,
    session_open: float,
    stop_type: str,
    stop_pct: float | None,
    target_pct: float | None,
) -> dict:
    """
    Simulate one trade from entry bar close to session close.

    stop_type:
      'none'       — no stop
      'structural' — exit if bar.low <= session_open (at session_open price)
      'hard'       — exit if bar.low <= entry * (1 - stop_pct/100)

    Returns dict: pnl_pct, exit_reason ('stop'|'target'|'close'), n_bars_held
    """
    if post_entry_bars.empty:
        return {"pnl_pct": 0.0, "exit_reason": "close", "n_bars_held": 0}

    stop_price   = None
    target_price = None

    if stop_type == "structural":
        stop_price = session_open
    elif stop_type == "hard" and stop_pct is not None:
        stop_price = entry_price * (1.0 - stop_pct / 100.0)

    if target_pct is not None:
        target_price = entry_price * (1.0 + target_pct / 100.0)

    for i, (_, bar) in enumerate(post_entry_bars.iterrows()):
        stop_triggered   = stop_price   is not None and bar["low"]  <= stop_price
        target_triggered = target_price is not None and bar["high"] >= target_price

        if stop_triggered and target_triggered:
            # Conservative: stop wins when both trigger in same bar
            exit_p = stop_price
            pnl    = (exit_p - entry_price) / entry_price * 100.0
            return {"pnl_pct": round(pnl, 4), "exit_reason": "stop", "n_bars_held": i + 1}

        if stop_triggered:
            exit_p = stop_price
            pnl    = (exit_p - entry_price) / entry_price * 100.0
            return {"pnl_pct": round(pnl, 4), "exit_reason": "stop", "n_bars_held": i + 1}

        if target_triggered:
            exit_p = target_price
            pnl    = (exit_p - entry_price) / entry_price * 100.0
            return {"pnl_pct": round(pnl, 4), "exit_reason": "target", "n_bars_held": i + 1}

    # Held to close
    exit_p = post_entry_bars["close"].iloc[-1]
    pnl    = (exit_p - entry_price) / entry_price * 100.0
    return {"pnl_pct": round(pnl, 4), "exit_reason": "close", "n_bars_held": len(post_entry_bars)}

# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def _stats(rets: pd.Series, label: str, stop_reasons: pd.Series | None = None,
           target_reasons: pd.Series | None = None) -> dict:
    n = len(rets)
    if n == 0:
        return {"id": label, "n": 0, "mean": 0.0, "median": 0.0, "std": 0.0,
                "win_rate": 0.0, "p10": 0.0, "p90": 0.0, "t_stat": 0.0,
                "stop_rate": 0.0, "target_rate": 0.0, "expectancy": 0.0}
    mean   = rets.mean()
    median = rets.median()
    std    = rets.std(ddof=1)
    win    = (rets > 0).mean()
    p10    = np.percentile(rets, 10)
    p90    = np.percentile(rets, 90)
    t_stat = mean / (std / np.sqrt(n)) if std > 0 else 0.0

    stop_rate   = (stop_reasons   == "stop").mean()   if stop_reasons   is not None else 0.0
    target_rate = (target_reasons == "target").mean() if target_reasons is not None else 0.0
    # Expectancy: win_rate * avg_win + loss_rate * avg_loss
    winners  = rets[rets > 0]
    losers   = rets[rets <= 0]
    avg_win  = winners.mean() if len(winners) > 0 else 0.0
    avg_loss = losers.mean()  if len(losers)  > 0 else 0.0
    expectancy = win * avg_win + (1 - win) * avg_loss

    return {
        "id":          label,
        "n":           n,
        "mean":        round(mean,        4),
        "median":      round(median,      4),
        "std":         round(std,         4),
        "win_rate":    round(win,         4),
        "p10":         round(p10,         4),
        "p90":         round(p90,         4),
        "t_stat":      round(t_stat,      3),
        "stop_rate":   round(stop_rate,   4),
        "target_rate": round(target_rate, 4),
        "expectancy":  round(expectancy,  4),
    }

# ---------------------------------------------------------------------------
# Concentration helper
# ---------------------------------------------------------------------------

def _concentration(df: pd.DataFrame) -> str:
    if df.empty:
        return "  N/A"
    by_ticker = (
        df.groupby("ticker")["pnl_pct"]
        .agg(total_return="sum", n_events="count")
        .assign(win_rate=lambda x: x.index.map(
            lambda t: (df[df["ticker"] == t]["pnl_pct"] > 0).mean()
        ))
        .sort_values("total_return", ascending=False)
    )
    total_pos = by_ticker[by_ticker["total_return"] > 0]["total_return"].sum()
    top5  = by_ticker.head(5)["total_return"].sum()  / total_pos if total_pos > 0 else 0
    top10 = by_ticker.head(10)["total_return"].sum() / total_pos if total_pos > 0 else 0
    pct_positive = (by_ticker["total_return"] > 0).mean()
    return (
        f"  Top-5 tickers:  {top5:.1%} of positive return\n"
        f"  Top-10 tickers: {top10:.1%} of positive return\n"
        f"  Tickers positive: {pct_positive:.1%} of {len(by_ticker)} tickers with events\n"
        f"  Top contributors: {', '.join(by_ticker.head(5).index.tolist())}"
    )

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # -- Locate child_001 session detail CSV
    candidates = sorted(
        glob_mod.glob(os.path.join(CHILD001_DIR, "*__session_detail__*.csv")),
        reverse=True,
    )
    if not candidates:
        print(f"ERROR: no session_detail CSV found in:\n  {CHILD001_DIR}")
        sys.exit(1)
    session_detail_path = candidates[0]
    print(f"Event source : {os.path.basename(session_detail_path)}")

    raw_df = pd.read_csv(session_detail_path)
    events = raw_df[raw_df["condition_met"].astype(str) == "True"].copy()
    events["date"]         = pd.to_datetime(events["date"]).dt.date
    events["early_reclaim"] = events["early_reclaim"].astype(str) == "True"

    print(f"Validated events : {len(events)} (condition_met=True)")
    print(f"Tickers          : {events['ticker'].nunique()}")
    print(f"Early reclaims   : {events['early_reclaim'].sum()} / {len(events)}")
    print()

    # -- Simulate all variants
    # Accumulate results per variant
    all_results = {v["id"]: [] for v in VARIANTS}

    n_ok   = 0
    n_fail = 0

    for ticker, ticker_events in events.groupby("ticker"):
        full_df = load_ticker_cache(ticker)
        if full_df is None:
            n_fail += len(ticker_events)
            continue

        for _, ev in ticker_events.iterrows():
            date          = ev["date"]
            entry_price   = float(ev["failure_bar_close"])
            session_open  = float(ev["session_open"])
            entry_bar_idx = int(ev["failure_bar_minutes"]) - 1   # 0-indexed in session
            early_reclaim = bool(ev["early_reclaim"])
            drive_mag     = float(ev["drive_magnitude_pct"])
            year_month    = str(ev["year_month"])

            # Extract session for this date
            day_df  = full_df[full_df.index.date == date]
            session = day_df.between_time(SESSION_START, SESSION_END)

            if len(session) <= entry_bar_idx:
                n_fail += 1
                continue

            # Bars AFTER the entry bar (entry is at entry_bar_idx, we hold from next bar)
            post_entry = session.iloc[entry_bar_idx + 1:]

            for v in VARIANTS:
                # Early-only filter
                if v["early_only"] and not early_reclaim:
                    continue

                result = simulate_trade(
                    post_entry_bars=post_entry,
                    entry_price=entry_price,
                    session_open=session_open,
                    stop_type=v["stop_type"],
                    stop_pct=v["stop_pct"],
                    target_pct=v["target_pct"],
                )
                all_results[v["id"]].append({
                    "ticker":       ticker,
                    "date":         str(date),
                    "year_month":   year_month,
                    "early_reclaim": early_reclaim,
                    "drive_mag":    drive_mag,
                    "session_open": session_open,
                    "entry_price":  entry_price,
                    "pnl_pct":      result["pnl_pct"],
                    "exit_reason":  result["exit_reason"],
                    "n_bars_held":  result["n_bars_held"],
                })
            n_ok += 1

    print(f"Events processed : {n_ok}  |  Failed (no cache): {n_fail}")
    print()

    # -- Build comparison table + write detail CSVs
    comparison_rows = []

    for v in VARIANTS:
        res_list = all_results[v["id"]]
        if not res_list:
            continue
        res_df = pd.DataFrame(res_list)
        rets   = res_df["pnl_pct"]
        row    = _stats(rets, v["id"],
                        stop_reasons=res_df["exit_reason"],
                        target_reasons=res_df["exit_reason"])
        row["label"] = v["label"]
        comparison_rows.append(row)

        # Write per-variant event detail
        detail_path = os.path.join(
            OUTPUT_DIR,
            f"phase_r3__{v['id'].lower()}__event_detail__{TODAY}.csv",
        )
        res_df.to_csv(detail_path, index=False)

    comparison_df = pd.DataFrame(comparison_rows)[
        ["id", "label", "n", "mean", "median", "std", "win_rate",
         "p10", "p90", "t_stat", "stop_rate", "target_rate", "expectancy"]
    ]

    cmp_csv = os.path.join(OUTPUT_DIR, f"phase_r3__variant_comparison__{TODAY}.csv")
    comparison_df.to_csv(cmp_csv, index=False)

    # -- Select winner: highest t-stat among variants with t >= 2.0 and mean > 0
    eligible = comparison_df[(comparison_df["t_stat"] >= 2.0) & (comparison_df["mean"] > 0)]
    if eligible.empty:
        winner_id = comparison_df.loc[comparison_df["t_stat"].idxmax(), "id"]
        winner_note = "WARNING: no variant reached t>=2.0 — selecting highest t-stat"
    else:
        winner_id   = eligible.loc[eligible["t_stat"].idxmax(), "id"]
        winner_note = "Best by t-stat (t>=2.0, mean>0)"

    winner_df  = pd.DataFrame(all_results[winner_id])
    winner_row = comparison_df[comparison_df["id"] == winner_id].iloc[0]
    winner_v   = next(v for v in VARIANTS if v["id"] == winner_id)

    # -- Print report
    lines = []
    lines += [
        "=" * 76,
        "PHASE_R3 STRATEGY FORMALIZATION — VARIANT COMPARISON",
        "Family : failed_opening_drive_and_reclaim",
        "Branch : child_001 (price $5-20, drive_down>=2%, reclaim, non-bearish)",
        f"Date   : {TODAY}",
        f"Events : {n_ok} processed  ({n_fail} failed — no cache)",
        "=" * 76,
        "",
        f"{'ID':<4} {'N':>5} {'Mean%':>7} {'Win%':>6} {'t':>6} {'p10%':>7} {'p90%':>7} "
        f"{'Stop%':>6} {'Tgt%':>6} {'E[pnl]':>7}",
        "-" * 76,
    ]
    for _, row in comparison_df.iterrows():
        marker = " <<< WINNER" if row["id"] == winner_id else ""
        lines.append(
            f"  {row['id']:<4} {row['n']:>5} {row['mean']:>+7.3f} "
            f"{row['win_rate']:>6.1%} {row['t_stat']:>+6.2f} "
            f"{row['p10']:>+7.3f} {row['p90']:>+7.3f} "
            f"{row['stop_rate']:>6.1%} {row['target_rate']:>6.1%} "
            f"{row['expectancy']:>+7.3f}{marker}"
        )

    lines += ["", "Label key:"]
    for v in VARIANTS:
        if v["id"] in comparison_df["id"].values:
            lines.append(f"  {v['id']}: {v['label']}")

    lines += [
        "",
        "=" * 76,
        f"WINNER: {winner_id} — {winner_row['label']}",
        f"Selection basis : {winner_note}",
        "",
        f"  n          : {int(winner_row['n'])}",
        f"  mean       : {winner_row['mean']:+.3f}%",
        f"  win rate   : {winner_row['win_rate']:.1%}",
        f"  t-stat     : {winner_row['t_stat']:+.2f}",
        f"  expectancy : {winner_row['expectancy']:+.3f}% per trade",
        f"  p10 / p90  : {winner_row['p10']:+.3f}% / {winner_row['p90']:+.3f}%",
        "",
    ]

    lines += ["CONCENTRATION (winner):"]
    lines.append(_concentration(winner_df))

    lines += [
        "",
        "=" * 76,
        "FORMAL CANDIDATE SPECIFICATION (phase_r3 survivor)",
        "=" * 76,
        "",
        "Strategy family : failed_opening_drive_and_reclaim",
        "Branch          : child_001__price_filtered_regime_gated",
        f"Formalized rule : {winner_id}",
        "",
        "CONDITION (inherited from child_001 locked validation):",
        "  1. Market month is non-bearish (universe-avg OTC > -0.10%)",
        "  2. Session open price in $5-20 range",
        "  3. First 30-minute drive is downward with abs magnitude >= 2.0%",
        "  4. Any post-drive bar closes >= session_open (price reclaims open)",
        "",
        "ENTRY:",
    ]

    if winner_v["early_only"]:
        lines.append(f"  Buy at close of the reclaim bar, ONLY if reclaim occurs within bar 60")
        lines.append(f"  (i.e., within 60 minutes of session open = within 30 min of drive end)")
    else:
        lines.append(f"  Buy at close of the first reclaim bar (any bar from bar 31 onward)")

    lines.append("")
    lines.append("STOP:")
    if winner_v["stop_type"] == "none":
        lines.append("  No stop applied — hold position through intraday noise")
    elif winner_v["stop_type"] == "structural":
        lines.append("  Structural stop: exit if any subsequent 1-min bar low <= session_open")
        lines.append("  Exit price: session_open (limit/stop-limit at session_open)")
    elif winner_v["stop_type"] == "hard":
        lines.append(f"  Hard stop: exit if any subsequent bar low <= entry * {1 - winner_v['stop_pct']/100:.4f}")
        lines.append(f"  (Entry price - {winner_v['stop_pct']:.1f}%)")

    lines.append("")
    lines.append("PROFIT TARGET:")
    if winner_v["target_pct"] is None:
        lines.append("  No fixed target — hold to close unless stopped")
    else:
        lines.append(f"  Exit if any subsequent bar high >= entry * {1 + winner_v['target_pct']/100:.4f}")
        lines.append(f"  (+{winner_v['target_pct']:.1f}% from entry price)")

    lines += [
        "",
        "TIME-BASED EXIT:",
        "  Hold to session close (15:59 ET) unless stop or target is hit first",
        "  Note: test a 15:00 ET hard exit in phase_r4 slippage sensitivity",
        "",
        "DIRECTION: Long only",
        "HOLDING PERIOD: Intraday — flat by close (same-day exit enforced)",
        "",
        "INITIAL EXPECTANCY ESTIMATE (in-sample, 21-month window):",
        f"  Gross mean return per trade : {winner_row['mean']:+.3f}%",
        f"  Win rate                    : {winner_row['win_rate']:.1%}",
        f"  Gross expectancy            : {winner_row['expectancy']:+.3f}% per trade",
        f"  Note: no slippage, commission, or spread applied.",
        f"  Phase_r4 stress test must apply 5bp–15bp slippage sensitivity.",
        "",
        "REGIME FILTER (carried from child_001):",
        "  Non-bearish months only (universe-avg OTC > -0.10%)",
        "  Regime computed from universe of liquid common stocks monthly average",
        "  7 bearish months validated in 2024-2025 dataset (signal does not invert in non-bearish)",
        "",
        "=" * 76,
        f"READY FOR PHASE_R4: {'YES — advancing' if winner_row['t_stat'] >= 2.0 else 'MARGINAL — review before advancing'}",
        "=" * 76,
    ]

    report_text = "\n".join(lines)
    print(report_text)

    report_path = os.path.join(OUTPUT_DIR, f"phase_r3__formalization_report__{TODAY}.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    print(f"\nOutputs written to: {OUTPUT_DIR}")
    print(f"  Comparison CSV   : {os.path.basename(cmp_csv)}")
    print(f"  Report           : {os.path.basename(report_path)}")
    print(f"  Detail CSVs      : phase_r3__v*__event_detail__{TODAY}.csv (one per variant)")


if __name__ == "__main__":
    main()
