"""
engineering_nightly_orchestrator__failed_breakdown_reclaim__template_002.py

Standalone nightly orchestrator for:
  failed_breakdown_reclaim__weak_reclaim_depth__time_exit_primary__template_002

Pipeline (3 stages):
  Stage 1 — nightly signal scan
  Stage 2 — run summary (JSON + terminal print)
  Stage 3 — Telegram delivery

Not included (pending future engineering work):
  - Data refresh (shared cache is kept fresh by the existing gap_directional_trap refresh)
  - Selection / ranking layer (phase_r7 skipped — single validated variant in family)

Usage:
  # Full run (scan + summary + Telegram), auto-detect signal date
  TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy \\
      python engineering_nightly_orchestrator__failed_breakdown_reclaim__template_002.py

  # Full run with explicit date
  TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy \\
      python engineering_nightly_orchestrator__failed_breakdown_reclaim__template_002.py --signal-date 2026-03-31

  # Preview — run scan + summary, print Telegram message without sending
  python engineering_nightly_orchestrator__failed_breakdown_reclaim__template_002.py --signal-date 2026-03-31 --preview

  # Skip Telegram — run scan + summary only
  python engineering_nightly_orchestrator__failed_breakdown_reclaim__template_002.py --signal-date 2026-03-31 --skip-telegram

  # Skip scan — re-summarize + re-deliver existing signal pack
  python engineering_nightly_orchestrator__failed_breakdown_reclaim__template_002.py --signal-date 2026-03-31 --skip-scan

Required environment variables (Stage 3 real send only):
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID

Research handoff source:
  1_0_strategy_research/research_outputs/family_lineages/plan_next_day_day_trade/
    failed_breakdown_reclaim/phase_r8_handoff/
    engineering_handoff_note__failed_breakdown_reclaim__template_002.md
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ENG_ROOT = Path(__file__).resolve().parent   # 2_0_agent_engineering/

SCAN_MODULE = (
    ENG_ROOT
    / "integrated_strategy_modules"
    / "plan_next_day_day_trade"
    / "failed_breakdown_reclaim__weak_reclaim_depth__time_exit_primary__template_002"
    / "engineering_nightly_signal_scan__failed_breakdown_reclaim__template_002.py"
)

SIGNAL_PACK_DIR = (
    ENG_ROOT
    / "engineering_runtime_outputs"
    / "plan_next_day_day_trade"
    / "failed_breakdown_reclaim__template_002"
)

SIGNAL_PACK_GLOB = "signal_pack__failed_breakdown_reclaim__template_002__*.csv"

TELEGRAM_MODULE = (
    ENG_ROOT
    / "engineering_source_code"
    / "notifications"
    / "telegram_delivery__failed_breakdown_reclaim__template_002.py"
)

# ---------------------------------------------------------------------------
# Identity (frozen)
# ---------------------------------------------------------------------------
VARIANT_NAME = "failed_breakdown_reclaim__weak_reclaim_depth__time_exit_primary__template_002"

# Required columns in a valid signal pack
REQUIRED_SIGNAL_COLUMNS = {
    "signal_date", "trade_date", "ticker",
    "market_regime_label", "context_confidence",
    "entry_price", "stop_price", "risk_distance_pct",
    "breakdown_depth_pct", "reclaim_pct",
    "adv_dollar_bucket", "price_bucket",
    "warning_flags",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _banner(stage_name: str, cmd: list) -> None:
    print(f"\n{'='*66}", flush=True)
    print(f"  STAGE: {stage_name}", flush=True)
    cmd_str = " ".join(str(c) for c in cmd)
    if len(cmd_str) > 120:
        parts = [Path(cmd[0]).name] + [str(c) for c in cmd[1:]]
        cmd_str = " ".join(parts)
    print(f"  cmd:   {cmd_str}", flush=True)
    print(f"{'='*66}", flush=True)


def run_stage(stage_name: str, cmd: list) -> None:
    """Run one pipeline stage as a subprocess. Halt on non-zero exit."""
    _banner(stage_name, cmd)
    sys.stdout.flush()
    result = subprocess.run(cmd)
    sys.stdout.flush()
    if result.returncode != 0:
        print(f"\n[FAIL] Stage '{stage_name}' exited with code {result.returncode}.", flush=True)
        print("[FAIL] Pipeline halted.", flush=True)
        sys.exit(result.returncode)
    print(f"\n[OK]   {stage_name} completed successfully.", flush=True)


def resolve_date_from_latest_signal_pack() -> str:
    """Return the signal date from the most recently written signal pack (YYYY-MM-DD)."""
    packs = sorted(SIGNAL_PACK_DIR.glob(SIGNAL_PACK_GLOB))
    if not packs:
        print("[FAIL] No signal_pack file found in output dir. Run Stage 1 first.")
        print(f"       Expected dir: {SIGNAL_PACK_DIR}")
        sys.exit(1)
    latest = packs[-1]
    date_part = latest.stem.split("__")[-1]   # YYYY_MM_DD
    return date_part.replace("_", "-")        # YYYY-MM-DD


def load_signal_pack(signal_date: str) -> pd.DataFrame:
    """Load and validate the signal pack CSV for the given signal date."""
    date_tag = signal_date.replace("-", "_")
    filename = f"signal_pack__failed_breakdown_reclaim__template_002__{date_tag}.csv"
    path = SIGNAL_PACK_DIR / filename

    if not path.exists():
        print(f"[FAIL] Signal pack not found: {path}")
        print("       Run Stage 1 (signal scan) first, or check the signal date.")
        sys.exit(1)

    try:
        df = pd.read_csv(path)
    except Exception as exc:
        print(f"[FAIL] Could not read signal pack: {exc}")
        sys.exit(1)

    missing = REQUIRED_SIGNAL_COLUMNS - set(df.columns)
    if missing:
        print(f"[FAIL] Signal pack is malformed — missing columns: {sorted(missing)}")
        sys.exit(1)

    return df


def build_summary(signal_date: str, df: pd.DataFrame) -> dict:
    """Build the run summary dict from the signal pack DataFrame."""
    signal_count = len(df)

    if signal_count > 0:
        first = df.iloc[0]
        trade_date       = str(first["trade_date"])
        market_regime    = str(first["market_regime_label"])
        ctx_confidence   = str(first["context_confidence"])
    else:
        trade_date     = None
        market_regime  = "unknown"
        ctx_confidence = "unknown"

    summary = {
        "variant":            VARIANT_NAME,
        "signal_date":        signal_date,
        "trade_date":         trade_date,
        "market_regime":      market_regime,
        "context_confidence": ctx_confidence,
        "signal_count":       signal_count,
        "execution": {
            "activate_at_et": "13:15",
            "cancel_by_et":   "13:30",
            "flatten_by_et":  "14:30",
        },
        "run_timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "signals": [],
    }

    if signal_count > 0:
        summary_cols = [
            "ticker", "entry_price", "stop_price", "risk_distance_pct",
            "breakdown_depth_pct", "reclaim_pct",
            "adv_dollar_bucket", "price_bucket", "context_confidence",
            "warning_flags",
        ]
        summary["signals"] = df[summary_cols].to_dict(orient="records")

    return summary


def write_summary_json(signal_date: str, summary: dict) -> Path:
    date_tag = signal_date.replace("-", "_")
    filename = f"run_summary__failed_breakdown_reclaim__template_002__{date_tag}.json"
    path = SIGNAL_PACK_DIR / filename
    SIGNAL_PACK_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    return path


def print_run_summary(signal_date: str, summary: dict, summary_path: Path) -> None:
    print()
    print("=" * 66, flush=True)
    print("  RUN SUMMARY  [failed_breakdown_reclaim__template_002]", flush=True)
    print("=" * 66, flush=True)
    print(f"  variant:          {VARIANT_NAME}", flush=True)
    print(f"  signal_date:      {summary['signal_date']}", flush=True)
    print(f"  trade_date:       {summary['trade_date']}", flush=True)
    print(f"  regime:           {summary['market_regime']}  "
          f"(context_confidence: {summary['context_confidence']})", flush=True)
    print(f"  signal_count:     {summary['signal_count']}", flush=True)
    print(f"  ---", flush=True)
    print(f"  execution:        activate 13:15 ET | cancel 13:30 ET | flatten 14:30 ET", flush=True)
    print(f"  ---", flush=True)

    if summary["signal_count"] == 0:
        print("  No qualifying signals for this date.", flush=True)
    else:
        print("  SIGNALS (ordered by breakdown_depth_pct descending):", flush=True)
        for sig in summary["signals"]:
            depth_str   = f"{sig['breakdown_depth_pct']:.3%}"
            reclaim_str = f"{sig['reclaim_pct']:.3%}"
            risk_str    = f"{float(sig['risk_distance_pct']):.1%}" if sig["risk_distance_pct"] != "" else "n/a"
            warn_str    = f"  [!] {sig['warning_flags']}" if sig["warning_flags"] else ""
            print(
                f"    {sig['ticker']:<8}  entry={sig['entry_price']:.2f}  stop={sig['stop_price']:.2f}"
                f"  risk={risk_str}  depth={depth_str}  reclaim={reclaim_str}"
                f"  {sig['adv_dollar_bucket']}  {sig['price_bucket']}"
                f"  conf={sig['context_confidence']}{warn_str}",
                flush=True,
            )

    print(f"  ---", flush=True)
    print(f"  summary JSON:     {summary_path}", flush=True)
    print("=" * 66, flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Nightly orchestrator: failed_breakdown_reclaim__template_002  "
            "(scan -> summary)"
        )
    )
    parser.add_argument(
        "--signal-date",
        metavar="YYYY-MM-DD",
        default=None,
        help="Signal date to process. Defaults to auto-detect from latest signal pack.",
    )
    parser.add_argument(
        "--skip-scan",
        action="store_true",
        help=(
            "Skip Stage 1 (signal scan). "
            "Re-summarize and re-deliver the most recent existing signal pack instead."
        ),
    )
    parser.add_argument(
        "--skip-telegram",
        action="store_true",
        help="Run Stages 1–2 only. Do not run Telegram delivery.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Pass --preview to Stage 3: print Telegram message without sending.",
    )
    args = parser.parse_args()

    print("\n" + "#" * 66, flush=True)
    print("  failed_breakdown_reclaim__template_002  |  nightly orchestrator", flush=True)
    if args.signal_date:
        print(f"  signal_date: {args.signal_date}", flush=True)
    else:
        print("  signal_date: auto-detect after Stage 1", flush=True)
    if args.preview:
        print("  mode: PREVIEW (Telegram will print, not send)", flush=True)
    if args.skip_scan:
        print("  flag: --skip-scan      (Stage 1 will not run)", flush=True)
    if args.skip_telegram:
        print("  flag: --skip-telegram  (Stage 3 will not run)", flush=True)
    print("#" * 66, flush=True)

    # ------------------------------------------------------------------
    # Stage 1: nightly signal scan
    # ------------------------------------------------------------------
    if args.skip_scan:
        print("\n[info]  --skip-scan set. Skipping Stage 1 (signal scan).", flush=True)
    else:
        print(
            "\n[Stage 1] Reads:  market_context, daily_cache, shared_universe\n"
            "          Writes: signal_pack__failed_breakdown_reclaim__template_002__YYYY_MM_DD.csv",
            flush=True,
        )
        cmd_scan = [sys.executable, str(SCAN_MODULE)]
        if args.signal_date:
            cmd_scan += ["--signal-date", args.signal_date]
        run_stage("nightly_signal_scan", cmd_scan)

    # ------------------------------------------------------------------
    # Resolve signal_date
    # ------------------------------------------------------------------
    if args.signal_date:
        signal_date = args.signal_date
    else:
        signal_date = resolve_date_from_latest_signal_pack()
        print(f"\n[info]  signal_date resolved from output: {signal_date}", flush=True)

    # ------------------------------------------------------------------
    # Stage 2: run summary
    # ------------------------------------------------------------------
    date_tag = signal_date.replace("-", "_")
    print(
        f"\n[Stage 2] Reads:  signal_pack__failed_breakdown_reclaim__template_002__{date_tag}.csv\n"
        f"          Writes: run_summary__failed_breakdown_reclaim__template_002__{date_tag}.json",
        flush=True,
    )

    df = load_signal_pack(signal_date)
    summary = build_summary(signal_date, df)
    summary_path = write_summary_json(signal_date, summary)

    print_run_summary(signal_date, summary, summary_path)

    print(f"\n[OK]   summary completed successfully.", flush=True)

    # ------------------------------------------------------------------
    # Stage 3: Telegram delivery
    # ------------------------------------------------------------------
    if args.skip_telegram:
        print("\n[info]  --skip-telegram set. Pipeline complete (Stages 1–2 only).", flush=True)
        return

    mode_note = "PREVIEW (print only)" if args.preview else "LIVE (Telegram send)"
    print(
        f"\n[Stage 3] Reads:  signal_pack__failed_breakdown_reclaim__template_002__{date_tag}.csv\n"
        f"          Mode:   {mode_note}",
        flush=True,
    )
    cmd_tg = [sys.executable, str(TELEGRAM_MODULE), "--signal-date", signal_date]
    if args.preview:
        cmd_tg.append("--preview")
    run_stage("telegram_delivery", cmd_tg)

    print(f"\n[done]  Full nightly pipeline completed.\n", flush=True)


if __name__ == "__main__":
    main()
