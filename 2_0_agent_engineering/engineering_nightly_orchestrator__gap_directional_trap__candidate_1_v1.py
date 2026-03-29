"""
2_0_agent_engineering/engineering_nightly_orchestrator__gap_directional_trap__candidate_1_v1.py

Nightly orchestrator for gap_directional_trap__candidate_1_v1.

Runs the full plan_next_day_day_trade pipeline in sequence:
  Stage 0 — daily data refresh (stock cache, market cache, context model)
  Stage 1 — nightly signal scan
  Stage 2 — top_3 selection layer
  Stage 3 — Telegram delivery

Calls each module as a subprocess.
Does NOT duplicate any refresh, scan, selection, or Telegram logic.
Does NOT modify any input file.

Usage examples:
  # preview full chain with refresh — no Telegram send
  python engineering_nightly_orchestrator__gap_directional_trap__candidate_1_v1.py --signal-date 2026-03-27 --preview

  # live full chain (refresh + scan + select + Telegram)
  TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy \\
      python engineering_nightly_orchestrator__gap_directional_trap__candidate_1_v1.py --signal-date 2026-03-27

  # latest-mode preview (refresh to today, auto-detect signal date)
  python engineering_nightly_orchestrator__gap_directional_trap__candidate_1_v1.py --preview

  # scan + selection only, no Telegram
  python engineering_nightly_orchestrator__gap_directional_trap__candidate_1_v1.py --signal-date 2026-03-27 --skip-telegram

  # skip refresh (data already fresh), scan + selection + Telegram
  python engineering_nightly_orchestrator__gap_directional_trap__candidate_1_v1.py --signal-date 2026-03-27 --skip-refresh

  # force full shared universe for refresh + scan (debug / validation)
  python engineering_nightly_orchestrator__gap_directional_trap__candidate_1_v1.py --signal-date 2026-03-27 --full-universe --skip-telegram

Required environment variables (Stage 3 real send only):
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID

Required environment variables (Stage 0 refresh):
  MASSIVE_API_KEY
"""

import argparse
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ENG_ROOT = Path(__file__).resolve().parent  # 2_0_agent_engineering/

REFRESH_MODULE = (
    ENG_ROOT / "engineering_daily_data_refresh__gap_directional_trap__candidate_1_v1.py"
)

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

TELEGRAM_MODULE = (
    ENG_ROOT
    / "engineering_source_code"
    / "notifications"
    / "telegram_delivery__gap_directional_trap__candidate_1_v1.py"
)

SIGNAL_PACK_DIR = (
    ENG_ROOT
    / "engineering_runtime_outputs"
    / "plan_next_day_day_trade"
    / "gap_directional_trap__candidate_1_v1"
)

SIGNAL_PACK_GLOB = "signal_pack__gap_directional_trap__candidate_1_v1__*.csv"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _banner(stage_name: str, cmd: list) -> None:
    print(f"\n{'='*66}", flush=True)
    print(f"  STAGE: {stage_name}", flush=True)
    cmd_str = " ".join(str(c) for c in cmd)
    # Truncate very long paths for readability
    if len(cmd_str) > 120:
        parts = [Path(cmd[0]).name] + [str(c) for c in cmd[1:]]
        cmd_str = " ".join(parts)
    print(f"  cmd:   {cmd_str}", flush=True)
    print(f"{'='*66}", flush=True)


def run_stage(stage_name: str, cmd: list) -> None:
    """Run one pipeline stage as a subprocess. Halt the orchestrator on failure."""
    _banner(stage_name, cmd)
    sys.stdout.flush()
    result = subprocess.run(cmd)
    sys.stdout.flush()
    if result.returncode != 0:
        print(f"\n[FAIL] Stage '{stage_name}' exited with code {result.returncode}.", flush=True)
        print("[FAIL] Pipeline halted. Remaining stages were not run.", flush=True)
        sys.exit(result.returncode)
    print(f"\n[OK]   {stage_name} completed successfully.", flush=True)


def resolve_date_from_latest_signal_pack() -> str:
    """
    Read the most recent signal_pack filename and return its date as YYYY-MM-DD.
    Called after Stage 1 when no --signal-date was provided.
    """
    packs = sorted(SIGNAL_PACK_DIR.glob(SIGNAL_PACK_GLOB))
    if not packs:
        print("[FAIL] Stage 1 produced no signal_pack file. Cannot continue.")
        sys.exit(1)
    latest = packs[-1]
    date_part = latest.stem.split("__")[-1]   # YYYY_MM_DD
    return date_part.replace("_", "-")        # YYYY-MM-DD


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Nightly orchestrator: gap_directional_trap__candidate_1_v1  "
            "(scan -> selection -> Telegram)"
        )
    )
    parser.add_argument(
        "--signal-date",
        metavar="YYYY-MM-DD",
        default=None,
        help="Signal date to process. Defaults to latest from market context (Stage 1 auto-detect).",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Pass --preview to Telegram stage: print message without sending.",
    )
    parser.add_argument(
        "--skip-telegram",
        action="store_true",
        help="Run Stages 0–2 only. Do not run Telegram delivery.",
    )
    parser.add_argument(
        "--skip-refresh",
        action="store_true",
        help=(
            "Skip Stage 0 (data refresh). Use when data is already fresh "
            "and you only want to re-run scan / selection / Telegram."
        ),
    )
    parser.add_argument(
        "--full-universe",
        action="store_true",
        help=(
            "Pass --full-universe to Stage 0 (refresh) and Stage 1 (scan). "
            "Forces use of the full shared universe (~4,700 tickers) instead of "
            "the module-specific operational universe (~1,400 tickers). "
            "Use for debugging or when validating the operational universe optimization."
        ),
    )
    args = parser.parse_args()

    print("\n" + "#" * 66, flush=True)
    print("  gap_directional_trap__candidate_1_v1  |  nightly orchestrator", flush=True)
    if args.signal_date:
        print(f"  signal_date: {args.signal_date}", flush=True)
    else:
        print("  signal_date: auto-detect (Stage 0 refresh → Stage 1 resolve)", flush=True)
    if args.preview:
        print("  mode: PREVIEW (Telegram will print, not send)", flush=True)
    if args.skip_telegram:
        print("  flag: --skip-telegram (Stage 3 will not run)", flush=True)
    if args.skip_refresh:
        print("  flag: --skip-refresh  (Stage 0 will not run)", flush=True)
    if args.full_universe:
        print("  flag: --full-universe (refresh + scan use full shared universe)", flush=True)
    print("#" * 66, flush=True)

    # ------------------------------------------------------------------
    # Stage 0: daily data refresh
    # ------------------------------------------------------------------
    if args.skip_refresh:
        print("\n[info]  --skip-refresh set. Skipping Stage 0 (data refresh).", flush=True)
    else:
        print(
            "\n[Stage 0] Extends stock + market parquets and rebuilds market context.",
            flush=True,
        )
        cmd_refresh = [sys.executable, str(REFRESH_MODULE)]
        if args.signal_date:
            cmd_refresh += ["--signal-date", args.signal_date]
        if args.preview:
            cmd_refresh.append("--preview")
        if args.full_universe:
            cmd_refresh.append("--full-universe")
        run_stage("daily_data_refresh", cmd_refresh)

    # ------------------------------------------------------------------
    # Stage 1: nightly signal scan
    # ------------------------------------------------------------------
    print(
        "\n[Stage 1] Reads:  market_context, daily_cache, universe\n"
        f"          Writes: signal_pack__gap_directional_trap__candidate_1_v1__YYYY_MM_DD.csv",
        flush=True,
    )
    cmd_scan = [sys.executable, str(SCAN_MODULE)]
    if args.signal_date:
        cmd_scan += ["--signal-date", args.signal_date]
    if args.full_universe:
        cmd_scan.append("--full-universe")
    run_stage("nightly_signal_scan", cmd_scan)

    # ------------------------------------------------------------------
    # Resolve signal_date for remaining stages
    # ------------------------------------------------------------------
    if args.signal_date:
        signal_date = args.signal_date
    else:
        signal_date = resolve_date_from_latest_signal_pack()
        print(f"\n[info]  signal_date resolved from output: {signal_date}", flush=True)

    date_tag = signal_date.replace("-", "_")

    # ------------------------------------------------------------------
    # Stage 2: top_3 selection layer
    # ------------------------------------------------------------------
    print(
        f"\n[Stage 2] Reads:  signal_pack__gap_directional_trap__candidate_1_v1__{date_tag}.csv\n"
        f"          Writes: ranked_signal_pack...__{date_tag}.csv\n"
        f"                  selected_top_3__...__{date_tag}.csv\n"
        f"                  selection_summary__...__{date_tag}.md",
        flush=True,
    )
    cmd_sel = [sys.executable, str(SELECTION_MODULE), "--signal-date", signal_date]
    run_stage("selection_layer", cmd_sel)

    # ------------------------------------------------------------------
    # Stage 3: Telegram delivery
    # ------------------------------------------------------------------
    if args.skip_telegram:
        print("\n[info]  --skip-telegram set. Pipeline complete (Stages 0–2 only).", flush=True)
        return

    mode_note = "PREVIEW (print only)" if args.preview else "LIVE (Telegram send)"
    print(
        f"\n[Stage 3] Reads:  selected_top_3__gap_directional_trap__candidate_1_v1__{date_tag}.csv\n"
        f"          Mode:   {mode_note}",
        flush=True,
    )
    cmd_tg = [sys.executable, str(TELEGRAM_MODULE), "--signal-date", signal_date]
    if args.preview:
        cmd_tg.append("--preview")
    run_stage("telegram_delivery", cmd_tg)

    print("\n[done]  Full nightly pipeline completed.\n", flush=True)


if __name__ == "__main__":
    main()
