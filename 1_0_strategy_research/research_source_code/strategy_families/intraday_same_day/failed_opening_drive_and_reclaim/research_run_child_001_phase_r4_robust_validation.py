"""
research_run_child_001_phase_r4_robust_validation.py
Track:  intraday_same_day
Family: failed_opening_drive_and_reclaim
Phase:  phase_r4 — robust validation

Purpose:
  Stress-test the V1 formal candidate (phase_r3 winner) under realistic conditions.
  Carries V4 (early reclaim only) as secondary comparison variant.

Primary candidate:
  V1 — Any reclaim | No stop | No target | Hold to session close (15:59 ET)
  873 events, 21-month window (2024-03 to 2025-12), non-bearish months only

Secondary variant:
  V4 — Early reclaim only (<=60 bars) | No stop | Hold to close
  166 events (subset of V1)

Dimensions tested:
  1. Slippage sensitivity  : V1 and V4 at 0bp, 5bp, 10bp, 15bp roundtrip
  2. OOS split             : IS (2024, pre-2025) vs OOS (2025)
  3. Ticker concentration  : ranked per-ticker total return, cumulative % of edge
  4. Tail behavior         : loss distribution, worst events, worst months
  5. Exit time sensitivity : 15:00 ET early exit vs 15:59 ET (requires 1m parquet)
  6. V1 vs V4 robustness   : side-by-side on slippage + OOS dimensions

Input:
  Phase_r3 V1 event detail CSV (873 events, pnl_pct pre-computed)
  Phase_r3 V4 event detail CSV (166 events, pnl_pct pre-computed)
  Child_001 session detail CSV (for failure_bar_minutes → 15:00 exit test)
  Intraday 1m parquet cache (for 15:00 exit price lookup)

Output (research_outputs/.../phase_r4_robust_validation/):
  phase_r4__slippage_sensitivity__<DATE>.csv
  phase_r4__oos_split__<DATE>.csv
  phase_r4__concentration_detail__<DATE>.csv
  phase_r4__tail_analysis__<DATE>.csv
  phase_r4__exit_time_sensitivity__<DATE>.csv
  phase_r4__robust_validation_report__<DATE>.txt
"""

import os
import sys
import glob as glob_mod
import datetime
import warnings
import io

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
PHASE_R3_DIR  = os.path.join(_LINEAGE, "phase_r3_strategy_formalization")
CHILD001_DIR  = os.path.join(_LINEAGE, "child_001_price_filtered_regime_gated")
OUTPUT_DIR    = os.path.join(_LINEAGE, "phase_r4_robust_validation")
os.makedirs(OUTPUT_DIR, exist_ok=True)

TODAY = datetime.date.today().strftime("%Y_%m_%d")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SESSION_START    = "09:30"
SESSION_END      = "15:59"
EARLY_EXIT_TIME  = "15:00"
IS_CUTOFF        = datetime.date(2025, 1, 1)   # IS = 2024, OOS = 2025
SLIPPAGE_BPS     = [0, 5, 10, 15]              # roundtrip basis points
DRIVE_MINUTES    = 30

# ---------------------------------------------------------------------------
# Windows reserved filename guard (matches family convention)
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
# Statistics helpers
# ---------------------------------------------------------------------------


def _stats(rets: pd.Series, label: str = "") -> dict:
    n = len(rets)
    if n == 0:
        return {
            "label": label, "n": 0, "mean": 0.0, "median": 0.0, "std": 0.0,
            "win_rate": 0.0, "t_stat": 0.0, "expectancy": 0.0,
            "p5": 0.0, "p10": 0.0, "p90": 0.0, "p95": 0.0,
        }
    mean   = rets.mean()
    median = rets.median()
    std    = rets.std(ddof=1)
    win    = (rets > 0).mean()
    t_stat = mean / (std / np.sqrt(n)) if std > 0 else 0.0
    winners  = rets[rets > 0]
    losers   = rets[rets <= 0]
    avg_win  = winners.mean() if len(winners) > 0 else 0.0
    avg_loss = losers.mean()  if len(losers)  > 0 else 0.0
    expectancy = win * avg_win + (1 - win) * avg_loss
    return {
        "label":      label,
        "n":          n,
        "mean":       round(mean,       4),
        "median":     round(median,     4),
        "std":        round(std,        4),
        "win_rate":   round(win,        4),
        "t_stat":     round(t_stat,     3),
        "expectancy": round(expectancy, 4),
        "p5":         round(float(np.percentile(rets,  5)), 4),
        "p10":        round(float(np.percentile(rets, 10)), 4),
        "p90":        round(float(np.percentile(rets, 90)), 4),
        "p95":        round(float(np.percentile(rets, 95)), 4),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Ensure stdout handles UTF-8 on Windows consoles
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    elif sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    # ------------------------------------------------------------------
    # Load inputs
    # ------------------------------------------------------------------

    # V1 event detail
    v1_files = sorted(
        glob_mod.glob(os.path.join(PHASE_R3_DIR, "*v1*event_detail*.csv")),
        reverse=True,
    )
    if not v1_files:
        print(f"ERROR: V1 event detail not found in {PHASE_R3_DIR}")
        sys.exit(1)

    # V4 event detail
    v4_files = sorted(
        glob_mod.glob(os.path.join(PHASE_R3_DIR, "*v4*event_detail*.csv")),
        reverse=True,
    )
    if not v4_files:
        print(f"ERROR: V4 event detail not found in {PHASE_R3_DIR}")
        sys.exit(1)

    # Child_001 session detail (for failure_bar_minutes)
    sd_files = sorted(
        glob_mod.glob(os.path.join(CHILD001_DIR, "*session_detail*.csv")),
        reverse=True,
    )
    if not sd_files:
        print(f"ERROR: child_001 session_detail not found in {CHILD001_DIR}")
        sys.exit(1)

    print(f"V1 source : {os.path.basename(v1_files[0])}")
    print(f"V4 source : {os.path.basename(v4_files[0])}")
    print(f"SD source : {os.path.basename(sd_files[0])}")
    print()

    v1_df = pd.read_csv(v1_files[0])
    v4_df = pd.read_csv(v4_files[0])
    sd_df = pd.read_csv(sd_files[0])

    v1_df["date"] = pd.to_datetime(v1_df["date"]).dt.date
    v4_df["date"] = pd.to_datetime(v4_df["date"]).dt.date
    sd_df["date"] = pd.to_datetime(sd_df["date"]).dt.date

    # Filter session_detail to condition_met=True events only (matches V1 universe)
    sd_events = sd_df[sd_df["condition_met"].astype(str) == "True"].copy()

    # Build lookup: (ticker, date) -> failure_bar_minutes
    fbm_lookup = {
        (row["ticker"], row["date"]): int(row["failure_bar_minutes"])
        for _, row in sd_events.iterrows()
    }

    print(f"V1 events : {len(v1_df)}")
    print(f"V4 events : {len(v4_df)}")
    print(f"SD events (condition_met=True): {len(sd_events)}")
    print()

    report_lines = []

    def _hdr(title: str, width: int = 70) -> list:
        return ["", "=" * width, title, "=" * width]

    def _row(label: str, val: str) -> str:
        return f"  {label:<38} {val}"

    # ==================================================================
    # DIMENSION 1: SLIPPAGE SENSITIVITY
    # ==================================================================
    print("Running dimension 1: slippage sensitivity...")

    slip_rows_v1 = []
    slip_rows_v4 = []

    for bps in SLIPPAGE_BPS:
        slip_pct = bps / 100.0
        r1 = _stats(v1_df["pnl_pct"] - slip_pct, label=f"V1 @ {bps}bp RT")
        r4 = _stats(v4_df["pnl_pct"] - slip_pct, label=f"V4 @ {bps}bp RT")
        slip_rows_v1.append(r1)
        slip_rows_v4.append(r4)

    slip_df_v1 = pd.DataFrame(slip_rows_v1)
    slip_df_v4 = pd.DataFrame(slip_rows_v4)

    combined_slip = pd.concat([slip_df_v1, slip_df_v4], ignore_index=True)
    slip_csv = os.path.join(OUTPUT_DIR, f"phase_r4__slippage_sensitivity__{TODAY}.csv")
    combined_slip[["label", "n", "mean", "win_rate", "t_stat", "expectancy", "p10", "p90"]].to_csv(
        slip_csv, index=False
    )

    report_lines += _hdr("DIMENSION 1: SLIPPAGE SENSITIVITY (roundtrip)")
    report_lines.append(
        f"\n  {'Label':<20} {'N':>5} {'Mean%':>7} {'Win%':>6} {'t':>6} {'E[pnl]%':>8}"
    )
    report_lines.append("  " + "-" * 50)
    for r in slip_rows_v1:
        alive = " [ok]" if r["t_stat"] >= 2.0 and r["mean"] > 0 else " [--]"
        report_lines.append(
            f"  {r['label']:<20} {r['n']:>5} {r['mean']:>+7.3f} "
            f"{r['win_rate']:>6.1%} {r['t_stat']:>+6.2f} {r['expectancy']:>+8.3f}{alive}"
        )
    report_lines.append("")
    for r in slip_rows_v4:
        alive = " [ok]" if r["t_stat"] >= 2.0 and r["mean"] > 0 else " [--]"
        report_lines.append(
            f"  {r['label']:<20} {r['n']:>5} {r['mean']:>+7.3f} "
            f"{r['win_rate']:>6.1%} {r['t_stat']:>+6.2f} {r['expectancy']:>+8.3f}{alive}"
        )

    # Breakeven slippage: where expectancy hits zero
    for r in slip_rows_v1:
        if r["expectancy"] <= 0:
            breakeven_bps = SLIPPAGE_BPS[slip_rows_v1.index(r)]
            break
    else:
        breakeven_bps = f"> {SLIPPAGE_BPS[-1]}"

    report_lines.append(
        f"\n  V1 breakeven slippage: {breakeven_bps}bp roundtrip"
    )
    report_lines.append(
        "  ([ok] = t>=2.0 and mean>0; [--] = below threshold)"
    )

    # ==================================================================
    # DIMENSION 2: OOS SPLIT
    # ==================================================================
    print("Running dimension 2: out-of-sample split...")

    v1_is  = v1_df[v1_df["date"] <  IS_CUTOFF].copy()
    v1_oos = v1_df[v1_df["date"] >= IS_CUTOFF].copy()
    v4_is  = v4_df[v4_df["date"] <  IS_CUTOFF].copy()
    v4_oos = v4_df[v4_df["date"] >= IS_CUTOFF].copy()

    oos_rows = [
        {**_stats(v1_df["pnl_pct"],  "V1 Full (21m)"), "window": "2024-03 to 2025-12"},
        {**_stats(v1_is["pnl_pct"],  "V1 IS  (2024)"), "window": "2024-03 to 2024-12"},
        {**_stats(v1_oos["pnl_pct"], "V1 OOS (2025)"), "window": "2025-04 to 2025-12"},
        {**_stats(v4_df["pnl_pct"],  "V4 Full (21m)"), "window": "2024-03 to 2025-12"},
        {**_stats(v4_is["pnl_pct"],  "V4 IS  (2024)"), "window": "2024-03 to 2024-12"},
        {**_stats(v4_oos["pnl_pct"], "V4 OOS (2025)"), "window": "2025-04 to 2025-12"},
    ]
    oos_df = pd.DataFrame(oos_rows)
    oos_csv = os.path.join(OUTPUT_DIR, f"phase_r4__oos_split__{TODAY}.csv")
    oos_df[["label", "window", "n", "mean", "win_rate", "t_stat", "expectancy"]].to_csv(
        oos_csv, index=False
    )

    report_lines += _hdr("DIMENSION 2: OOS SPLIT  (IS = 2024, OOS = 2025)")
    report_lines.append(
        f"\n  {'Label':<20} {'Window':<22} {'N':>5} {'Mean%':>7} {'Win%':>6} {'t':>6}"
    )
    report_lines.append("  " + "-" * 68)
    for r in oos_rows:
        alive = " [ok]" if r["t_stat"] >= 2.0 and r["mean"] > 0 else " [--]"
        report_lines.append(
            f"  {r['label']:<20} {r['window']:<22} {r['n']:>5} "
            f"{r['mean']:>+7.3f} {r['win_rate']:>6.1%} {r['t_stat']:>+6.2f}{alive}"
        )

    # OOS verdict note
    oos_t = oos_rows[2]["t_stat"]   # V1 OOS
    is_t  = oos_rows[1]["t_stat"]   # V1 IS
    oos_mean = oos_rows[2]["mean"]
    is_mean  = oos_rows[1]["mean"]
    oos_note = (
        "OOS STRONGER than IS (edge is not in-sample-only)"
        if oos_mean > is_mean else
        "OOS weaker than IS — typical edge decay; check if t_stat holds"
    )
    report_lines.append(f"\n  V1 IS mean={is_mean:+.3f}%  IS t={is_t:+.2f}  |  OOS mean={oos_mean:+.3f}%  OOS t={oos_t:+.2f}")
    report_lines.append(f"  Note: {oos_note}")

    # ==================================================================
    # DIMENSION 3: TICKER CONCENTRATION
    # ==================================================================
    print("Running dimension 3: ticker concentration...")

    by_ticker = (
        v1_df.groupby("ticker")["pnl_pct"]
        .agg(total_return="sum", n_events="count", mean_return="mean")
        .reset_index()
    )
    by_ticker["win_rate"] = by_ticker["ticker"].map(
        lambda t: (v1_df[v1_df["ticker"] == t]["pnl_pct"] > 0).mean()
    )
    by_ticker = by_ticker.sort_values("total_return", ascending=False).reset_index(drop=True)
    by_ticker["rank"] = range(1, len(by_ticker) + 1)

    total_pos = by_ticker[by_ticker["total_return"] > 0]["total_return"].sum()
    cumulative = 0.0
    cum_pcts = []
    for _, row in by_ticker.iterrows():
        if row["total_return"] > 0:
            cumulative += row["total_return"]
        cum_pcts.append(cumulative / total_pos if total_pos > 0 else 0.0)
    by_ticker["cum_pct_of_positive_return"] = cum_pcts

    conc_csv = os.path.join(OUTPUT_DIR, f"phase_r4__concentration_detail__{TODAY}.csv")
    by_ticker.round(4).to_csv(conc_csv, index=False)

    n_tickers = len(by_ticker)
    n_positive = (by_ticker["total_return"] > 0).sum()
    pct_positive = n_positive / n_tickers

    top5_pct  = by_ticker.head(5)["total_return"].clip(lower=0).sum() / total_pos if total_pos > 0 else 0
    top10_pct = by_ticker.head(10)["total_return"].clip(lower=0).sum() / total_pos if total_pos > 0 else 0

    # Find how many tickers needed for 50% and 80% of positive return
    def _tickers_for_pct(target_pct: float) -> int:
        for i, v in enumerate(cum_pcts):
            if v >= target_pct:
                return i + 1
        return n_tickers

    n_for_50 = _tickers_for_pct(0.50)
    n_for_80 = _tickers_for_pct(0.80)

    report_lines += _hdr("DIMENSION 3: TICKER CONCENTRATION")
    report_lines.append(f"\n  Total tickers with events : {n_tickers}")
    report_lines.append(f"  Tickers with positive total return : {n_positive} ({pct_positive:.1%})")
    report_lines.append(f"  Top-5  tickers  : {top5_pct:.1%} of positive return")
    report_lines.append(f"  Top-10 tickers  : {top10_pct:.1%} of positive return")
    report_lines.append(f"  Tickers needed for 50% of positive return: {n_for_50}")
    report_lines.append(f"  Tickers needed for 80% of positive return: {n_for_80}")
    report_lines.append(f"\n  Top-10 by total return:")
    report_lines.append(f"  {'Rank':<5} {'Ticker':<8} {'TotalRet%':>9} {'N':>5} {'MeanRet%':>9} {'WinRate':>8}")
    report_lines.append("  " + "-" * 48)
    for _, row in by_ticker.head(10).iterrows():
        report_lines.append(
            f"  {int(row['rank']):<5} {row['ticker']:<8} {row['total_return']:>+9.3f} "
            f"{int(row['n_events']):>5} {row['mean_return']:>+9.3f} {row['win_rate']:>8.1%}"
        )

    # Concentration verdict
    conc_ok = top10_pct < 0.60
    report_lines.append(
        f"\n  Concentration verdict: {'ACCEPTABLE' if conc_ok else 'ELEVATED'} "
        f"(top-10 at {top10_pct:.1%}, threshold = 60%)"
    )

    # ==================================================================
    # DIMENSION 4: TAIL BEHAVIOR
    # ==================================================================
    print("Running dimension 4: tail behavior...")

    rets = v1_df["pnl_pct"]

    # Full distribution
    dist_stats = _stats(rets, "V1 full")

    # Worst and best events
    worst_10 = v1_df.nsmallest(10, "pnl_pct")[
        ["ticker", "date", "year_month", "drive_mag", "entry_price", "pnl_pct"]
    ].reset_index(drop=True)
    best_10 = v1_df.nlargest(10, "pnl_pct")[
        ["ticker", "date", "year_month", "drive_mag", "entry_price", "pnl_pct"]
    ].reset_index(drop=True)

    # Monthly summary
    monthly_stats = (
        v1_df.groupby("year_month")["pnl_pct"]
        .agg(n="count", mean="mean", win_rate=lambda x: (x > 0).mean())
        .reset_index()
    )
    monthly_stats["t_stat"] = monthly_stats.apply(
        lambda r: (
            r["mean"] / (v1_df[v1_df["year_month"] == r["year_month"]]["pnl_pct"].std(ddof=1) / np.sqrt(r["n"]))
            if r["n"] > 1 else 0.0
        ),
        axis=1,
    )
    monthly_stats = monthly_stats.sort_values("year_month")

    negative_months = monthly_stats[monthly_stats["mean"] < 0]
    n_neg = len(negative_months)
    n_total_months = len(monthly_stats)

    # Max loss event
    max_loss_event = v1_df.loc[v1_df["pnl_pct"].idxmin()]
    max_gain_event = v1_df.loc[v1_df["pnl_pct"].idxmax()]

    # Loss distribution
    losses_only = rets[rets < 0]
    loss_p25 = float(np.percentile(losses_only, 25)) if len(losses_only) > 0 else 0.0
    loss_p50 = float(np.percentile(losses_only, 50)) if len(losses_only) > 0 else 0.0
    loss_p75 = float(np.percentile(losses_only, 75)) if len(losses_only) > 0 else 0.0
    loss_p95 = float(np.percentile(losses_only, 95)) if len(losses_only) > 0 else 0.0

    # Write tail CSVs
    tail_worst_csv = os.path.join(OUTPUT_DIR, f"phase_r4__tail_analysis__{TODAY}.csv")
    tail_combined = pd.concat([
        worst_10.assign(category="worst_10"),
        best_10.assign(category="best_10"),
    ])
    tail_combined.to_csv(tail_worst_csv, index=False)

    monthly_csv = os.path.join(OUTPUT_DIR, f"phase_r4__monthly_breakdown__{TODAY}.csv")
    monthly_stats.round(4).to_csv(monthly_csv, index=False)

    report_lines += _hdr("DIMENSION 4: TAIL BEHAVIOR")
    report_lines.append(f"\n  Return distribution (V1, n={len(rets)}):")
    report_lines.append(f"    p5  = {dist_stats['p5']:+.3f}%  |  p10 = {dist_stats['p10']:+.3f}%")
    report_lines.append(f"    p90 = {dist_stats['p90']:+.3f}%  |  p95 = {dist_stats['p95']:+.3f}%")
    report_lines.append(f"    std = {dist_stats['std']:.3f}%  |  median = {dist_stats['median']:+.3f}%")
    report_lines.append(f"\n  Loss-side analysis ({len(losses_only)} losing trades = {len(losses_only)/len(rets):.1%}):")
    report_lines.append(f"    Loss p25 = {loss_p25:+.3f}%  p50 = {loss_p50:+.3f}%  p75 = {loss_p75:+.3f}%  p95 = {loss_p95:+.3f}%")
    report_lines.append(
        f"    Worst single event: {max_loss_event['ticker']} on {max_loss_event['date']} "
        f"({max_loss_event['pnl_pct']:+.3f}%, drive={max_loss_event['drive_mag']:.2f}%)"
    )
    report_lines.append(
        f"    Best single event : {max_gain_event['ticker']} on {max_gain_event['date']} "
        f"({max_gain_event['pnl_pct']:+.3f}%, drive={max_gain_event['drive_mag']:.2f}%)"
    )
    report_lines.append(f"\n  Monthly breakdown ({n_total_months} non-bearish months):")
    report_lines.append(f"    Negative months: {n_neg} / {n_total_months} ({n_neg/n_total_months:.1%})")
    report_lines.append(f"    {'Month':<12} {'N':>5} {'Mean%':>8} {'Win%':>6} {'t':>6}")
    report_lines.append("    " + "-" * 42)
    for _, row in monthly_stats.iterrows():
        flag = " *" if row["mean"] < 0 else ""
        report_lines.append(
            f"    {row['year_month']:<12} {int(row['n']):>5} {row['mean']:>+8.3f} "
            f"{row['win_rate']:>6.1%} {row['t_stat']:>+6.2f}{flag}"
        )
    report_lines.append("    (* = negative mean month)")
    report_lines.append(f"\n  Top-5 worst events:")
    for _, row in worst_10.head(5).iterrows():
        report_lines.append(
            f"    {row['ticker']:<6} {str(row['date']):<12} {row['year_month']:<8} "
            f"{row['pnl_pct']:>+8.3f}%  drive={row['drive_mag']:.2f}%"
        )

    # ==================================================================
    # DIMENSION 5: EXIT TIME SENSITIVITY  (15:00 vs 15:59)
    # ==================================================================
    print("Running dimension 5: exit time sensitivity (15:00 vs 15:59)...")
    print("  Re-reading 1m parquets for 15:00 bar close prices...")

    early_exit_rows = []
    n_ok   = 0
    n_fail = 0
    n_late_entry = 0   # entries after 15:00 (15:00 exit not applicable)

    for ticker, ticker_events in v1_df.groupby("ticker"):
        full_df = load_ticker_cache(ticker)
        if full_df is None:
            n_fail += len(ticker_events)
            continue

        for _, ev in ticker_events.iterrows():
            date         = ev["date"]
            entry_price  = float(ev["entry_price"])
            key          = (ticker, date)
            fbm          = fbm_lookup.get(key)

            if fbm is None:
                n_fail += 1
                continue

            day_df  = full_df[full_df.index.date == date]
            session = day_df.between_time(SESSION_START, SESSION_END)

            if session.empty:
                n_fail += 1
                continue

            # Entry bar index (0-indexed from session start)
            entry_bar_idx = fbm - 1

            # 15:00 bar: how many bars from 09:30 to 15:00 inclusive
            early_session = day_df.between_time(SESSION_START, EARLY_EXIT_TIME)
            n_early_bars = len(early_session)   # bars up to and including 15:00

            # If entry is at or after 15:00 bar → 15:00 exit not meaningful
            if entry_bar_idx >= n_early_bars:
                n_late_entry += 1
                # Use V1 pnl (held to 15:59) as-is
                early_exit_rows.append({
                    "ticker":          ticker,
                    "date":            str(date),
                    "year_month":      ev["year_month"],
                    "entry_price":     entry_price,
                    "pnl_v1_1559":     float(ev["pnl_pct"]),
                    "pnl_early_1500":  float(ev["pnl_pct"]),  # same — entry after 15:00
                    "late_entry":      True,
                })
                n_ok += 1
                continue

            # 15:00 exit price: close of last bar in early_session
            exit_price_1500 = float(early_session["close"].iloc[-1])
            pnl_1500 = (exit_price_1500 - entry_price) / entry_price * 100.0

            early_exit_rows.append({
                "ticker":          ticker,
                "date":            str(date),
                "year_month":      ev["year_month"],
                "entry_price":     entry_price,
                "pnl_v1_1559":     float(ev["pnl_pct"]),
                "pnl_early_1500":  round(pnl_1500, 4),
                "late_entry":      False,
            })
            n_ok += 1

    print(f"  15:00 exit: {n_ok} events computed  ({n_fail} failed, {n_late_entry} late entries kept as-is)")

    early_exit_df = pd.DataFrame(early_exit_rows)
    exit_csv = os.path.join(OUTPUT_DIR, f"phase_r4__exit_time_sensitivity__{TODAY}.csv")
    early_exit_df.to_csv(exit_csv, index=False)

    # Compare stats
    if len(early_exit_df) > 0:
        stats_1559 = _stats(early_exit_df["pnl_v1_1559"],    "V1 hold to 15:59")
        stats_1500 = _stats(early_exit_df["pnl_early_1500"], "V1 exit at 15:00")

        # Also compute for V4 subset (early reclaim only)
        v4_keys = set(zip(v4_df["ticker"], v4_df["date"].astype(str)))
        early_exit_df["key"] = list(zip(early_exit_df["ticker"], early_exit_df["date"]))
        v4_early = early_exit_df[early_exit_df["key"].isin(v4_keys)].copy()
        stats_v4_1559 = _stats(v4_early["pnl_v1_1559"],    "V4 hold to 15:59")
        stats_v4_1500 = _stats(v4_early["pnl_early_1500"], "V4 exit at 15:00")
    else:
        stats_1559 = stats_1500 = stats_v4_1559 = stats_v4_1500 = {}

    report_lines += _hdr("DIMENSION 5: EXIT TIME SENSITIVITY  (15:00 ET vs 15:59 ET)")
    report_lines.append(
        f"\n  Events computed: {n_ok}  |  Failed: {n_fail}  |  Late-entry (kept as V1): {n_late_entry}"
    )
    if stats_1559:
        report_lines.append(
            f"\n  {'Variant':<26} {'N':>5} {'Mean%':>7} {'Win%':>6} {'t':>6} {'E[pnl]%':>8}"
        )
        report_lines.append("  " + "-" * 58)
        for s in [stats_1559, stats_1500, stats_v4_1559, stats_v4_1500]:
            alive = " [ok]" if s.get("t_stat", 0) >= 2.0 and s.get("mean", 0) > 0 else " [--]"
            report_lines.append(
                f"  {s['label']:<26} {s['n']:>5} {s['mean']:>+7.3f} "
                f"{s['win_rate']:>6.1%} {s['t_stat']:>+6.2f} {s['expectancy']:>+8.3f}{alive}"
            )

    # ==================================================================
    # DIMENSION 6: V1 vs V4 SIDE-BY-SIDE SUMMARY
    # ==================================================================

    report_lines += _hdr("DIMENSION 6: V1 vs V4 SIDE-BY-SIDE")

    v4_is_df  = v4_df[v4_df["date"] <  IS_CUTOFF]
    v4_oos_df = v4_df[v4_df["date"] >= IS_CUTOFF]

    comparison_pairs = [
        ("V1 Full",         v1_df["pnl_pct"]),
        ("V1 IS (2024)",    v1_is["pnl_pct"]),
        ("V1 OOS (2025)",   v1_oos["pnl_pct"]),
        ("V4 Full",         v4_df["pnl_pct"]),
        ("V4 IS (2024)",    v4_is_df["pnl_pct"]),
        ("V4 OOS (2025)",   v4_oos_df["pnl_pct"]),
    ]

    report_lines.append(
        f"\n  {'Variant':<22} {'N':>5} {'Mean%':>7} {'Win%':>6} {'t':>6} {'E[pnl]%':>8}"
    )
    report_lines.append("  " + "-" * 58)
    for label, series in comparison_pairs:
        s = _stats(series, label)
        alive = " [ok]" if s["t_stat"] >= 2.0 and s["mean"] > 0 else " [--]"
        report_lines.append(
            f"  {s['label']:<22} {s['n']:>5} {s['mean']:>+7.3f} "
            f"{s['win_rate']:>6.1%} {s['t_stat']:>+6.2f} {s['expectancy']:>+8.3f}{alive}"
        )

    report_lines.append("")
    report_lines.append("  V4 vs V1 interpretation:")
    v4_full_t = _stats(v4_df["pnl_pct"])["t_stat"]
    v1_full_t = _stats(v1_df["pnl_pct"])["t_stat"]
    v4_full_mean = _stats(v4_df["pnl_pct"])["mean"]
    v1_full_mean = _stats(v1_df["pnl_pct"])["mean"]
    report_lines.append(
        f"  V4 has higher mean ({v4_full_mean:+.3f}% vs V1 {v1_full_mean:+.3f}%) "
        f"but lower n (166 vs 873)"
    )
    report_lines.append(
        f"  V4 t-stat = {v4_full_t:.2f} vs V1 t-stat = {v1_full_t:.2f}"
    )
    if v4_full_t >= 2.0 and v4_full_mean > v1_full_mean:
        report_lines.append(
            "  V4 remains a viable sub-filter but does not replace V1 as primary candidate"
        )
    else:
        report_lines.append(
            "  V1 remains stronger overall; V4 is a complementary angle"
        )

    # ==================================================================
    # FINAL VERDICT
    # ==================================================================

    # Collect pass/fail flags for verdict
    flags = {}

    # Slippage: V1 alive at 10bp?
    slip_10 = slip_rows_v1[SLIPPAGE_BPS.index(10)]
    flags["slip_10bp_ok"] = slip_10["t_stat"] >= 2.0 and slip_10["mean"] > 0

    # OOS: alive?
    flags["oos_t_ok"]    = oos_rows[2]["t_stat"] >= 1.8  # OOS allowed slightly lower threshold
    flags["oos_mean_ok"] = oos_rows[2]["mean"]   > 0

    # Concentration: top-10 < 60%?
    flags["conc_ok"] = top10_pct < 0.60

    # Tail: p5 not catastrophic? (>= -8% is acceptable for intraday)
    flags["tail_ok"] = dist_stats["p5"] >= -8.0

    # Monthly: fewer than 40% negative months?
    flags["monthly_ok"] = (n_neg / n_total_months) < 0.40

    # Exit time: 15:00 exit still alive?
    flags["exit_1500_ok"] = (
        stats_1500.get("t_stat", 0) >= 2.0 and stats_1500.get("mean", 0) > 0
        if stats_1500 else False
    )

    all_pass = all(flags.values())
    critical_pass = flags["slip_10bp_ok"] and flags["oos_mean_ok"] and flags["oos_t_ok"]

    report_lines += _hdr("PHASE_R4 VERDICT", width=70)
    report_lines.append("")
    report_lines.append(f"  {'Check':<45} {'Result'}")
    report_lines.append("  " + "-" * 60)
    report_lines.append(f"  {'V1 survives 10bp roundtrip slippage (t>=2.0)':<45} {'PASS' if flags['slip_10bp_ok'] else 'FAIL'}")
    report_lines.append(f"  {'OOS 2025 mean > 0':<45} {'PASS' if flags['oos_mean_ok']   else 'FAIL'}")
    report_lines.append(f"  {'OOS 2025 t-stat >= 1.8':<45} {'PASS' if flags['oos_t_ok']      else 'FAIL'}")
    report_lines.append(f"  {'Concentration: top-10 < 60% of positive return':<45} {'PASS' if flags['conc_ok']       else 'FAIL'}")
    report_lines.append(f"  {'Tail: p5 >= -8%':<45} {'PASS' if flags['tail_ok']       else 'FAIL'}")
    report_lines.append(f"  {'Monthly: < 40% negative months':<45} {'PASS' if flags['monthly_ok']    else 'FAIL'}")
    report_lines.append(f"  {'15:00 exit still alive (t>=2.0)':<45} {'PASS' if flags['exit_1500_ok'] else 'FAIL'}")
    report_lines.append("")

    if all_pass:
        verdict = "GO — V1 PASSES ALL PHASE_R4 CHECKS. Recommend advancing to promotion."
        verdict_detail = (
            "V1 survives realistic friction, shows out-of-sample stability, "
            "acceptable concentration, and clean tail behavior. "
            "Branch is ready for promotion to frozen_survivors/."
        )
    elif critical_pass:
        verdict = "CONDITIONAL GO — V1 passes critical checks. Minor issues noted."
        verdict_detail = (
            "V1 clears the three critical gates (slippage, OOS mean, OOS t). "
            "Non-critical flags should be reviewed before promotion but do not block. "
            "Recommend advancing with caveats documented."
        )
    else:
        verdict = "NO-GO — V1 fails one or more critical phase_r4 checks."
        verdict_detail = (
            "One or more of slippage survival, OOS direction, or OOS significance "
            "has failed. Branch requires narrowing, a new formulation, or closure."
        )

    report_lines.append(f"  VERDICT: {verdict}")
    report_lines.append(f"  {verdict_detail}")

    # V4 verdict
    v4_oos_t    = _stats(v4_oos_df["pnl_pct"])["t_stat"]
    v4_oos_mean = _stats(v4_oos_df["pnl_pct"])["mean"]
    v4_slip_10  = _stats(v4_df["pnl_pct"] - 10 / 100.0)
    v4_alive    = v4_oos_mean > 0 and v4_slip_10["mean"] > 0

    report_lines.append("")
    report_lines.append(
        f"  V4 (early reclaim sub-filter): "
        f"{'VIABLE secondary variant' if v4_alive else 'does not add robustness beyond V1'}"
    )
    report_lines.append(
        f"  V4 OOS 2025 mean={v4_oos_mean:+.3f}%  t={v4_oos_t:.2f}  "
        f"| 10bp slip mean={v4_slip_10['mean']:+.3f}%"
    )

    # ==================================================================
    # Header block (prepend)
    # ==================================================================

    header = [
        "=" * 70,
        "PHASE_R4 ROBUST VALIDATION REPORT",
        "Family : failed_opening_drive_and_reclaim",
        "Branch : child_001 (price $5-20, drive_down>=2%, reclaim, non-bearish)",
        f"Date   : {TODAY}",
        f"V1 events : {len(v1_df)}   V4 events : {len(v4_df)}",
        "=" * 70,
    ]

    full_report = "\n".join(header + report_lines)

    # Print to console
    print()
    print(full_report)

    # Write report
    report_path = os.path.join(OUTPUT_DIR, f"phase_r4__robust_validation_report__{TODAY}.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(full_report)

    print(f"\nOutputs written to: {OUTPUT_DIR}")
    print(f"  Report                : {os.path.basename(report_path)}")
    print(f"  Slippage sensitivity  : phase_r4__slippage_sensitivity__{TODAY}.csv")
    print(f"  OOS split             : phase_r4__oos_split__{TODAY}.csv")
    print(f"  Concentration detail  : phase_r4__concentration_detail__{TODAY}.csv")
    print(f"  Tail analysis         : phase_r4__tail_analysis__{TODAY}.csv")
    print(f"  Monthly breakdown     : phase_r4__monthly_breakdown__{TODAY}.csv")
    print(f"  Exit time sensitivity : phase_r4__exit_time_sensitivity__{TODAY}.csv")


if __name__ == "__main__":
    main()
