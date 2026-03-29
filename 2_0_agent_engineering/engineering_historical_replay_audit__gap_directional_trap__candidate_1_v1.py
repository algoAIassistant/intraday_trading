"""
2_0_agent_engineering/engineering_historical_replay_audit__gap_directional_trap__candidate_1_v1.py

Historical replay and outcome audit for gap_directional_trap__candidate_1_v1.

For each signal date:
  1. Generates or reuses the raw signal_pack  (calls nightly_signal_scan if needed)
  2. Generates or reuses the selected_top_3   (calls selection_layer if needed)
  3. Evaluates each selected trade against the next-day daily OHLC bar
  4. Classifies the outcome with one of the labels below

Outcome labels:
  pending                       trade_date OHLC not yet available in daily cache
  no_fill                       next_day_high < entry_price  (entry never triggered)
  stop_hit                      entry triggered; low <= stop_price; high < target_price
  target_hit                    entry triggered; high >= target_price; low > stop_price
  moc_win                       entry triggered; no bracket hit; close > entry_price
  moc_loss                      entry triggered; no bracket hit; close <= entry_price
  sequence_ambiguous_daily_bar  entry triggered; both stop and target within daily range;
                                sequence cannot be determined from daily bars alone

Evaluation notes:
  - All outcomes use entry_price as the assumed fill price (consistent with research
    methodology). See open_above_entry column where next_day_open >= entry_price.
  - Realized R is computed relative to the research-defined risk_pct for each trade.
  - Ambiguous trades (both stop and target hit on same bar) are flagged explicitly
    rather than guessed.

Writes two files under:
  engineering_runtime_outputs/plan_next_day_day_trade/gap_directional_trap__candidate_1_v1/

  historical_replay_outcomes__gap_directional_trap__candidate_1_v1__<date_range>.csv
  historical_replay_summary__gap_directional_trap__candidate_1_v1__<date_range>.md

Usage:
  # run default 6-date set (one per year from 2022 to 2026)
  python engineering_historical_replay_audit__gap_directional_trap__candidate_1_v1.py

  # custom date list
  python engineering_historical_replay_audit__gap_directional_trap__candidate_1_v1.py \\
      --signal-dates 2022-01-07,2023-01-03,2024-04-15

  # force regenerate scan + selection even if cached files exist
  python engineering_historical_replay_audit__gap_directional_trap__candidate_1_v1.py --force-rescan

Do NOT:
  - modify the scan module
  - modify the selection module
  - redesign the strategy
  - change frozen entry / stop / target formulas
  - add broker or Telegram code here
"""

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ENG_ROOT  = Path(__file__).resolve().parent   # 2_0_agent_engineering/
REPO_ROOT = ENG_ROOT.parent                   # ai_trading_assistant/

SCAN_MODULE = (
    ENG_ROOT
    / "integrated_strategy_modules"
    / "plan_next_day_day_trade"
    / "gap_directional_trap__bearish_medium_large__candidate_1_v1"
    / "engineering_nightly_signal_scan__gap_directional_trap__candidate_1_v1.py"
)
SELECTION_MODULE = (
    ENG_ROOT
    / "integrated_strategy_modules"
    / "plan_next_day_day_trade"
    / "gap_directional_trap__bearish_medium_large__candidate_1_v1"
    / "engineering_selection_layer__gap_directional_trap__candidate_1_v1.py"
)

SIGNAL_PACK_DIR = (
    ENG_ROOT
    / "engineering_runtime_outputs"
    / "plan_next_day_day_trade"
    / "gap_directional_trap__candidate_1_v1"
)

DAILY_CACHE_DIR = REPO_ROOT / "1_0_strategy_research" / "research_data_cache" / "daily"

VARIANT_ID = "gap_directional_trap__bearish_medium_large__candidate_1_v1"

# ---------------------------------------------------------------------------
# Default signal date set — one per year, all with bearish regime.
# 2026-03-24 is included as the known live test case; its trade date
# (2026-03-25) is not yet in the daily cache so it will be marked pending.
# ---------------------------------------------------------------------------
DEFAULT_SIGNAL_DATES = [
    "2022-01-07",   # 2022 — sustained bear market year
    "2023-01-03",   # 2023 — early-year bearish window
    "2024-04-15",   # 2024 — April selloff episode
    "2025-03-10",   # 2025 — March bearish run
    "2026-02-05",   # 2026 — early February bearish run
    "2026-03-24",   # 2026 — live test date (trade date pending in cache)
]

# ---------------------------------------------------------------------------
# Outcome label constants
# ---------------------------------------------------------------------------
LABEL_PENDING    = "pending"
LABEL_NO_FILL    = "no_fill"
LABEL_STOP_HIT   = "stop_hit"
LABEL_TARGET_HIT = "target_hit"
LABEL_MOC_WIN    = "moc_win"
LABEL_MOC_LOSS   = "moc_loss"
LABEL_AMBIGUOUS  = "sequence_ambiguous_daily_bar"

ALL_OUTCOME_LABELS = [
    LABEL_PENDING, LABEL_NO_FILL, LABEL_STOP_HIT, LABEL_TARGET_HIT,
    LABEL_MOC_WIN, LABEL_MOC_LOSS, LABEL_AMBIGUOUS,
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_daily_parquet(ticker: str) -> "pd.DataFrame | None":
    """Load a ticker's daily parquet from the research cache.

    Returns a DataFrame with plain string date index (YYYY-MM-DD), or None.
    """
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


def run_scan_if_needed(signal_date: str, force: bool = False) -> Path:
    """Run the nightly scan module for signal_date if the signal_pack doesn't exist."""
    date_tag    = signal_date.replace("-", "_")
    signal_pack = SIGNAL_PACK_DIR / f"signal_pack__gap_directional_trap__candidate_1_v1__{date_tag}.csv"
    if signal_pack.exists() and not force:
        print(f"    [scan]      reuse {signal_pack.name}", flush=True)
        return signal_pack
    print(f"    [scan]      running scan for {signal_date} ...", flush=True)
    result = subprocess.run(
        [sys.executable, str(SCAN_MODULE), "--signal-date", signal_date],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout[-2000:] if result.stdout else "", flush=True)
        print(result.stderr[-1000:] if result.stderr else "", file=sys.stderr, flush=True)
        raise RuntimeError(f"Scan failed for {signal_date} (exit {result.returncode})")
    # Extract final signal count line from stdout for a brief status print
    for line in reversed(result.stdout.splitlines()):
        if "FINAL SIGNAL COUNT" in line or "signal_date" in line:
            print(f"    [scan]      {line.strip()}", flush=True)
            break
    return signal_pack


def run_selection_if_needed(signal_date: str, force: bool = False) -> Path:
    """Run the selection layer for signal_date if the selected_top_3 doesn't exist."""
    date_tag = signal_date.replace("-", "_")
    selected = SIGNAL_PACK_DIR / f"selected_top_3__gap_directional_trap__candidate_1_v1__{date_tag}.csv"
    if selected.exists() and not force:
        print(f"    [selection] reuse {selected.name}", flush=True)
        return selected
    print(f"    [selection] running selection for {signal_date} ...", flush=True)
    result = subprocess.run(
        [sys.executable, str(SELECTION_MODULE), "--signal-date", signal_date],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout[-2000:] if result.stdout else "", flush=True)
        print(result.stderr[-1000:] if result.stderr else "", file=sys.stderr, flush=True)
        raise RuntimeError(f"Selection failed for {signal_date} (exit {result.returncode})")
    for line in reversed(result.stdout.splitlines()):
        if "selected for delivery" in line or "selected_count" in line:
            print(f"    [selection] {line.strip()}", flush=True)
            break
    return selected


def classify_outcome(
    entry: float,
    stop: float,
    target: float,
    risk_pct: float,
    trade_bar: "pd.Series | None",
) -> dict:
    """Return outcome classification dict for one trade from its next-day daily bar.

    Uses entry_price as assumed fill price throughout (consistent with research
    methodology). open_above_entry flag is added for transparency.
    """
    # Trade date not in cache yet
    if trade_bar is None:
        return dict(
            next_day_open=None, next_day_high=None, next_day_low=None, next_day_close=None,
            open_above_entry=None,
            entry_triggered=False, stop_hit_flag=False, target_hit_flag=False, moc_exit_flag=False,
            realized_exit_price=None, realized_pnl_pct=None, realized_r=None,
            outcome_label=LABEL_PENDING,
        )

    nd_open  = float(trade_bar["open"])
    nd_high  = float(trade_bar["high"])
    nd_low   = float(trade_bar["low"])
    nd_close = float(trade_bar["close"])

    open_above_entry = bool(nd_open >= entry)
    entry_triggered  = bool(nd_high >= entry)   # buy-stop: triggered when high touches entry

    base = dict(
        next_day_open=round(nd_open, 4),
        next_day_high=round(nd_high, 4),
        next_day_low=round(nd_low, 4),
        next_day_close=round(nd_close, 4),
        open_above_entry=open_above_entry,
    )

    if not entry_triggered:
        return {**base,
                "entry_triggered": False, "stop_hit_flag": False,
                "target_hit_flag": False, "moc_exit_flag": False,
                "realized_exit_price": None, "realized_pnl_pct": None,
                "realized_r": None, "outcome_label": LABEL_NO_FILL}

    stop_in_range   = bool(nd_low  <= stop)
    target_in_range = bool(nd_high >= target)

    # Both bracket levels touched — cannot determine sequence from daily bars
    if stop_in_range and target_in_range:
        return {**base,
                "entry_triggered": True, "stop_hit_flag": True,
                "target_hit_flag": True, "moc_exit_flag": False,
                "realized_exit_price": None, "realized_pnl_pct": None,
                "realized_r": None, "outcome_label": LABEL_AMBIGUOUS}

    # Stop hit only
    if stop_in_range:
        pnl_pct = (stop - entry) / entry
        return {**base,
                "entry_triggered": True, "stop_hit_flag": True,
                "target_hit_flag": False, "moc_exit_flag": False,
                "realized_exit_price": round(stop, 4),
                "realized_pnl_pct": round(pnl_pct, 4),
                "realized_r": -1.0,   # stop = -1R by construction
                "outcome_label": LABEL_STOP_HIT}

    # Target hit only
    if target_in_range:
        pnl_pct = (target - entry) / entry
        return {**base,
                "entry_triggered": True, "stop_hit_flag": False,
                "target_hit_flag": True, "moc_exit_flag": False,
                "realized_exit_price": round(target, 4),
                "realized_pnl_pct": round(pnl_pct, 4),
                "realized_r": 2.0,    # target = +2R by construction
                "outcome_label": LABEL_TARGET_HIT}

    # Neither stop nor target — MOC exit at close
    pnl_pct = (nd_close - entry) / entry
    realized_r = pnl_pct / risk_pct if risk_pct > 0 else 0.0
    outcome = LABEL_MOC_WIN if nd_close > entry else LABEL_MOC_LOSS
    return {**base,
            "entry_triggered": True, "stop_hit_flag": False,
            "target_hit_flag": False, "moc_exit_flag": True,
            "realized_exit_price": round(nd_close, 4),
            "realized_pnl_pct": round(pnl_pct, 4),
            "realized_r": round(realized_r, 3),
            "outcome_label": outcome}


# ---------------------------------------------------------------------------
# Per-date audit
# ---------------------------------------------------------------------------

def audit_signal_date(signal_date: str, force: bool) -> tuple[list[dict], int]:
    """Audit all selected trades for one signal_date.

    Returns (list_of_outcome_dicts, raw_signal_count).
    """
    print(f"\n  --- {signal_date} ---", flush=True)

    date_tag     = signal_date.replace("-", "_")
    sp_path      = SIGNAL_PACK_DIR / f"signal_pack__gap_directional_trap__candidate_1_v1__{date_tag}.csv"
    sel_path     = SIGNAL_PACK_DIR / f"selected_top_3__gap_directional_trap__candidate_1_v1__{date_tag}.csv"

    run_scan_if_needed(signal_date, force=force)
    run_selection_if_needed(signal_date, force=force)

    # Raw signal count
    raw_count = 0
    if sp_path.exists():
        try:
            raw_count = len(pd.read_csv(sp_path))
        except Exception:
            pass

    if not sel_path.exists():
        print(f"    [warn] selected_top_3 not found after selection run", flush=True)
        return [], raw_count

    df_all = pd.read_csv(sel_path, dtype=str)
    df_sel = df_all[df_all["selected_for_delivery"].str.strip().str.lower() == "true"].copy()

    print(f"    raw_signals={raw_count}   selected={len(df_sel)}", flush=True)

    if df_sel.empty:
        return [], raw_count

    rows: list[dict] = []
    for _, row in df_sel.iterrows():
        ticker     = str(row["ticker"]).strip()
        trade_date = str(row["trade_date"]).strip()
        entry      = float(row["entry_price"])
        stop       = float(row["stop_price"])
        target     = float(row["target_price"])
        risk_pct   = float(row["risk_pct"])

        # Load next-day bar from daily cache
        daily     = load_daily_parquet(ticker)
        trade_bar = None
        if daily is not None and trade_date in daily.index:
            trade_bar = daily.loc[trade_date]

        outcome = classify_outcome(entry, stop, target, risk_pct, trade_bar)
        label   = outcome["outcome_label"]

        print(
            f"    {ticker:6s}  entry={entry:.4f}  stop={stop:.4f}  target={target:.4f}"
            f"  trade_date={trade_date}  -> {label}",
            flush=True,
        )

        rows.append({
            "signal_date":            signal_date,
            "trade_date":             trade_date,
            "ticker":                 ticker,
            "selection_rank_overall": str(row.get("selection_rank_overall", "")).strip(),
            "entry_price":            round(entry, 4),
            "stop_price":             round(stop, 4),
            "target_price":           round(target, 4),
            "risk_pct":               round(risk_pct, 4),
            **outcome,
        })

    return rows, raw_count


# ---------------------------------------------------------------------------
# Summary builders
# ---------------------------------------------------------------------------

def _md_row(cells: list) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |"


def build_summary_md(
    all_outcomes: list[dict],
    signal_dates: list[str],
    date_meta: dict,
    output_csv: Path,
    output_summary: Path,
) -> str:
    """Build the markdown summary text."""
    df = pd.DataFrame(all_outcomes) if all_outcomes else pd.DataFrame()
    total_trades = len(df)

    lines: list[str] = [
        f"# historical_replay_summary__{VARIANT_ID}",
        "",
        f"variant_id:     {VARIANT_ID}",
        f"signal_dates:   {len(signal_dates)}",
        f"trades_audited: {total_trades}",
        "",
        "**Evaluation notes:**",
        "- entry_price used as assumed fill price throughout (consistent with research methodology)",
        "- see `open_above_entry` column in outcomes CSV where next_day_open >= entry_price",
        "- daily-bar-only evaluation: stop/target sequence within the day cannot be resolved",
        "",
        "---",
        "",
        "## Per-date summary",
        "",
        _md_row(["signal_date", "raw_signals", "selected", "outcome_breakdown"]),
        _md_row(["---", "---", "---", "---"]),
    ]

    for sd in signal_dates:
        meta = date_meta.get(sd, {})
        raw  = meta.get("raw_count", 0)
        sel  = meta.get("selected_count", 0)
        if df.empty or "signal_date" not in df.columns:
            breakdown = "no_data"
        else:
            date_rows = df[df["signal_date"] == sd]
            if date_rows.empty:
                breakdown = "no_selected_signals"
            else:
                counts = date_rows["outcome_label"].value_counts().to_dict()
                parts  = [f"{lbl}:{counts[lbl]}" for lbl in ALL_OUTCOME_LABELS if lbl in counts]
                breakdown = "  ".join(parts) if parts else "unknown"
        lines.append(_md_row([sd, raw, sel, breakdown]))

    lines += [
        "",
        "---",
        "",
        "## Aggregate outcome distribution",
        "",
    ]

    if not df.empty and "outcome_label" in df.columns:
        for lbl in ALL_OUTCOME_LABELS:
            n   = int((df["outcome_label"] == lbl).sum())
            pct = 100.0 * n / total_trades if total_trades > 0 else 0.0
            lines.append(f"- {lbl}: {n} / {total_trades}  ({pct:.0f}%)")
    else:
        lines.append("- no trades audited")

    lines += [
        "",
        "---",
        "",
        "## Individual trade outcomes",
        "",
    ]

    if not df.empty:
        show_cols = [
            "signal_date", "trade_date", "ticker", "selection_rank_overall",
            "entry_price", "stop_price", "target_price",
            "next_day_open", "next_day_high", "next_day_low", "next_day_close",
            "open_above_entry", "entry_triggered", "outcome_label",
            "realized_exit_price", "realized_pnl_pct", "realized_r",
        ]
        sub = df[[c for c in show_cols if c in df.columns]]

        # Manual markdown table (avoids tabulate dependency)
        headers = list(sub.columns)
        lines.append(_md_row(headers))
        lines.append(_md_row(["---"] * len(headers)))
        for _, r in sub.iterrows():
            lines.append(_md_row([r[c] for c in headers]))
    else:
        lines.append("No trades to display.")

    lines += [
        "",
        "---",
        "",
        "## Next step",
        "",
        "This batch completes: historical replay and outcome audit.",
        "",
        "Suggested next engineering batch:",
        "  `engineering_build_windows_task_scheduler__gap_directional_trap__candidate_1_v1`",
        "  Scope: PowerShell script to register a Windows Task Scheduler task that runs",
        "  the nightly orchestrator after market close. Single install / single uninstall.",
        "  Secrets (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID) read from a local env file or",
        "  Windows credential store — not embedded in the task definition.",
        "",
        "---",
        "",
        "## Output files",
        "",
        f"- outcomes CSV:  `{output_csv.name}`",
        f"- summary MD:    `{output_summary.name}`",
        f"- location:      `{output_csv.parent}`",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Historical replay / outcome audit: gap_directional_trap__candidate_1_v1"
    )
    parser.add_argument(
        "--signal-dates",
        metavar="YYYY-MM-DD,...",
        default=None,
        help=(
            "Comma-separated list of signal dates to audit. "
            f"Default: {','.join(DEFAULT_SIGNAL_DATES)}"
        ),
    )
    parser.add_argument(
        "--force-rescan",
        action="store_true",
        help="Re-run scan + selection even when cached output files already exist.",
    )
    args = parser.parse_args()

    if args.signal_dates:
        signal_dates = [d.strip() for d in args.signal_dates.split(",") if d.strip()]
    else:
        signal_dates = DEFAULT_SIGNAL_DATES

    print("\n" + "#" * 66, flush=True)
    print("  gap_directional_trap__candidate_1_v1  |  historical replay audit", flush=True)
    print(f"  signal dates: {signal_dates}", flush=True)
    if args.force_rescan:
        print("  mode: --force-rescan (will regenerate scan + selection files)", flush=True)
    print("#" * 66, flush=True)

    SIGNAL_PACK_DIR.mkdir(parents=True, exist_ok=True)

    # Audit each date
    all_outcomes: list[dict] = []
    date_meta: dict = {}

    for sd in signal_dates:
        try:
            outcomes, raw_count = audit_signal_date(sd, force=args.force_rescan)
        except RuntimeError as exc:
            print(f"\n[FAIL] {exc}", flush=True)
            sys.exit(1)
        all_outcomes.extend(outcomes)
        date_meta[sd] = {
            "raw_count":      raw_count,
            "selected_count": len(outcomes),
        }

    # Build output filenames from date range
    sorted_dates = sorted(signal_dates)
    date_range   = (
        f"{sorted_dates[0].replace('-', '_')}"
        f"__{sorted_dates[-1].replace('-', '_')}"
    )

    output_csv = (
        SIGNAL_PACK_DIR
        / f"historical_replay_outcomes__gap_directional_trap__candidate_1_v1__{date_range}.csv"
    )
    output_summary = (
        SIGNAL_PACK_DIR
        / f"historical_replay_summary__gap_directional_trap__candidate_1_v1__{date_range}.md"
    )

    # Write outcomes CSV
    if all_outcomes:
        pd.DataFrame(all_outcomes).to_csv(output_csv, index=False)
    else:
        pd.DataFrame().to_csv(output_csv, index=False)

    # Write summary MD
    summary_text = build_summary_md(
        all_outcomes, signal_dates, date_meta, output_csv, output_summary
    )
    output_summary.write_text(summary_text, encoding="utf-8")

    # Final console summary
    total = len(all_outcomes)
    print("\n" + "=" * 66, flush=True)
    print("  HISTORICAL REPLAY AUDIT COMPLETE", flush=True)
    print("=" * 66, flush=True)
    print(f"  signal dates processed:  {len(signal_dates)}", flush=True)
    print(f"  total trades audited:    {total}", flush=True)
    if total > 0:
        df_out = pd.DataFrame(all_outcomes)
        for lbl in ALL_OUTCOME_LABELS:
            n = int((df_out["outcome_label"] == lbl).sum())
            if n > 0:
                pct = 100.0 * n / total
                print(f"    {lbl}: {n}  ({pct:.0f}%)", flush=True)
    print("=" * 66, flush=True)
    print(f"  outputs:", flush=True)
    print(f"    {output_csv}", flush=True)
    print(f"    {output_summary}", flush=True)
    print("=" * 66, flush=True)


if __name__ == "__main__":
    main()
