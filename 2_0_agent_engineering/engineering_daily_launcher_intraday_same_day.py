"""
engineering_daily_launcher_intraday_same_day.py

Daily automation launcher for the intraday_same_day Alpaca paper trading track.

Wraps engineering_run_alpaca_paper_intraday_same_day.py with a session lifecycle:

    Phase 1  PREMARKET  (before 09:25 ET) — sleep with 5-min heartbeat log
    Phase 2  STANDBY    (09:25–09:30 ET)  — wait for open
    Phase 3  SESSION    (09:30–16:05 ET)  — heartbeat every 5 min; no API calls
    Phase 4  EOD        (after 16:05 ET)  — fetch full-day bars, run session once
    Phase 5  DONE       — write launcher log entry, exit

Design notes:
    - The core 6-layer architecture is unchanged. The launcher adds only the
      time-aware lifecycle wrapper.
    - For dry-run (submit_orders=false, default): the full session runs once at
      EOD as a single batch. Correct and sufficient — no intra-session changes
      needed.
    - For live paper orders (future, submit_orders=true): entries must fire
      during SESSION (around bar 30–60, ~10:00–11:00 ET). That requires an
      incremental bar accumulator feeding the signal runner bar-by-bar. That
      is the next engineering step and is NOT part of this launcher.
    - If --session-date is a past date, time guards are skipped and the session
      runs immediately (for replay and testing).
    - Weekends and non-trading days are detected and handled gracefully.

Usage:
    # Today's live session (premarket guard active)
    python engineering_daily_launcher_intraday_same_day.py

    # Past date replay (no time guards)
    python engineering_daily_launcher_intraday_same_day.py --session-date 2026-03-25

    # Override tickers
    python engineering_daily_launcher_intraday_same_day.py --tickers SOUN IONQ MARA

    # Verbose logging
    python engineering_daily_launcher_intraday_same_day.py --verbose

Run from repo root:
    cd b:\\git_hub\\claude_code\\ai_trading_assistant
    python 2_0_agent_engineering/engineering_daily_launcher_intraday_same_day.py

----------------------------------------------------------------------------
Windows Task Scheduler — recommended setup
----------------------------------------------------------------------------
Task name : AlpacaPaper_IntraDay_SameDay_Launcher
Trigger   : Daily, 09:00 AM ET, repeat Monday–Friday only
Action    : Start a program
  Program : C:\\path\\to\\python.exe
  Arguments:
    b:\\git_hub\\claude_code\\ai_trading_assistant\\2_0_agent_engineering\\engineering_daily_launcher_intraday_same_day.py
  Start in:
    b:\\git_hub\\claude_code\\ai_trading_assistant

Environment variables (add under Task > Properties > Edit > Environment):
  ALPACA_API_KEY    = <your key>
  ALPACA_API_SECRET = <your secret>

Note: .claude/settings.local.json env vars are only visible to the Claude Code
process. They must also be set as Task Scheduler environment variables (or as
Windows user/system variables) for the scheduled task to pick them up.

Exact scheduled command (single line):
  C:\\path\\to\\python.exe b:\\git_hub\\claude_code\\ai_trading_assistant\\2_0_agent_engineering\\engineering_daily_launcher_intraday_same_day.py
----------------------------------------------------------------------------
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_SCRIPT_PATH = Path(os.path.abspath(__file__))
_ENGINEERING_ROOT = _SCRIPT_PATH.parent   # 2_0_agent_engineering/
_REPO_ROOT = _ENGINEERING_ROOT.parent

if str(_ENGINEERING_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENGINEERING_ROOT))

# ---------------------------------------------------------------------------
# Internal imports — reuse the existing alpaca runner's session function
# directly. No duplication of config loading, credential reading, or session
# wiring.
# ---------------------------------------------------------------------------
from engineering_run_alpaca_paper_intraday_same_day import (  # noqa: E402
    _load_config,
    _resolve_path,
    _read_credentials,
    run_alpaca_session,
    _DEFAULT_CONFIG,
    _DEFAULT_TICKER_FILE,
    _OUTPUT_DIR,
    _STRATEGY_ID,
)
from engineering_source_code.data_feeds.engineering_data_feed_alpaca_minute_bars import AlpacaMinuteBarFeed  # noqa: E402
from engineering_source_code.market_climate_engine.engineering_market_climate_regime_gate import RegimeGate  # noqa: E402
from engineering_source_code.risk_engine.engineering_risk_portfolio_controls import PortfolioRiskControls  # noqa: E402
from engineering_source_code.broker_execution_adapters.engineering_broker_alpaca_paper_adapter import AlpacaPaperAdapter  # noqa: E402
from engineering_source_code.production_utilities.engineering_trade_logger import TradeLogger  # noqa: E402
from engineering_source_code.signal_runners.engineering_intraday_session_manager import IntradaySessionManager  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session phase boundaries (ET)
# ---------------------------------------------------------------------------
_PREMARKET_END   = datetime.time(9, 25)   # premarket wait ends
_SESSION_OPEN    = datetime.time(9, 30)   # regular session opens
_EOD_TRIGGER     = datetime.time(16, 5)   # fetch bars + run session
_POST_CLOSE_HARD = datetime.time(16, 30)  # hard deadline — exit regardless

_HEARTBEAT_INTERVAL_S = 300   # 5-min heartbeat during premarket only
_POLL_INTERVAL_S      = 60    # 1-min bar poll during live SESSION phase


# ---------------------------------------------------------------------------
# Timezone helpers
# ---------------------------------------------------------------------------

def _get_et_tz():
    """Return ET tzinfo using zoneinfo, pytz, or UTC fallback."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("America/New_York")
    except ImportError:
        pass
    try:
        import pytz
        return pytz.timezone("America/New_York")
    except ImportError:
        pass
    logger.warning("No timezone library found — using UTC. ET timing will be approximate.")
    return datetime.timezone.utc


_ET_TZ = _get_et_tz()


def _now_et() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).astimezone(_ET_TZ)


def _is_weekday(dt: datetime.datetime) -> bool:
    return dt.weekday() < 5  # Monday=0, Friday=4


# ---------------------------------------------------------------------------
# Launcher log (one .jsonl file per session date)
# ---------------------------------------------------------------------------

def _launcher_log(output_dir: Path, session_date: datetime.date, event: str, extra: dict | None = None) -> None:
    """Append one JSON line to the per-day launcher log file."""
    log_dir = output_dir / _STRATEGY_ID
    log_dir.mkdir(parents=True, exist_ok=True)
    date_str = session_date.strftime("%Y_%m_%d")
    log_path = log_dir / f"launcher_log__{date_str}.jsonl"
    entry = {
        "ts": _now_et().isoformat(),
        "session_date": str(session_date),
        "event": event,
    }
    if extra:
        entry.update(extra)
    logger.info(f"[LAUNCHER] {event}" + (f" | {extra}" if extra else ""))
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


# ---------------------------------------------------------------------------
# Core daily session runner
# ---------------------------------------------------------------------------

def run_daily_session(
    session_date: datetime.date,
    tickers: list,
    config: dict,
    output_dir: Path,
    skip_time_guards: bool = False,
) -> dict:
    """
    Run the full daily session lifecycle.

    Parameters:
        session_date      : trading date
        tickers           : candidate ticker list
        config            : loaded config dict
        output_dir        : engineering_runtime_outputs/
        skip_time_guards  : True for past-date replays — runs immediately

    Returns:
        session summary dict from the signal runner, or a skip-reason dict.
    """

    def _log(event: str, extra: dict | None = None) -> None:
        _launcher_log(output_dir, session_date, event, extra)

    _log("LAUNCHER_STARTED", {
        "tickers": len(tickers),
        "skip_time_guards": skip_time_guards,
        "submit_orders": config.get("alpaca_submit_orders", False),
    })

    # ----------------------------------------------------------------
    # Past-date replay: skip all time guards
    # ----------------------------------------------------------------
    if skip_time_guards:
        _log("TIME_GUARDS_SKIPPED")
        print(f"  [REPLAY] Past date {session_date} — running immediately.")
        summary = run_alpaca_session(
            session_date=session_date,
            tickers=tickers,
            config=config,
            submit_orders_override=None,
            output_dir=output_dir,
        )
        _log("SESSION_COMPLETE", {
            "signals": summary.get("signals_emitted", 0),
            "trades": summary.get("total_trades_entered", 0),
            "pnl_pct": summary.get("total_pnl_pct", 0.0),
            "regime": summary.get("regime_label", "unknown"),
        })
        return summary

    # ----------------------------------------------------------------
    # Fail fast: check credentials before the premarket wait
    # ----------------------------------------------------------------
    api_key, api_secret = _read_credentials(config)

    paper_url     = config.get("alpaca_paper_base_url", "https://paper-api.alpaca.markets")
    data_url      = config.get("alpaca_data_base_url", "https://data.alpaca.markets")
    regime_map_p  = _resolve_path(str(config.get("regime_map_path", "")))
    submit_orders = config.get("alpaca_submit_orders", False)
    slippage_bp   = float(config.get("roundtrip_slippage_bp", 10))
    portfolio_usd = float(config.get("portfolio_value_usd", 50000))
    max_positions = int(config.get("max_open_positions", 5))
    max_size_pct  = float(config.get("max_position_size_pct", 0.10))
    loss_limit    = float(config.get("daily_loss_limit_pct", -0.02))

    # ----------------------------------------------------------------
    # Phase 1: PREMARKET — wait until 09:25 ET
    # ----------------------------------------------------------------
    while True:
        now_et = _now_et()

        if not _is_weekday(now_et):
            msg = f"Today is {now_et.strftime('%A')} — not a trading day."
            _log("NON_TRADING_DAY", {"weekday": now_et.strftime("%A")})
            print(f"\n  {msg} Exiting.")
            return {"skipped": "non_trading_day", "session_date": str(session_date)}

        if now_et.time() >= _PREMARKET_END:
            break  # ready to enter session phase

        target = datetime.datetime.combine(now_et.date(), _PREMARKET_END).replace(tzinfo=_ET_TZ)
        wait_s = max(0.0, (target - now_et).total_seconds())
        sleep_s = min(wait_s, _HEARTBEAT_INTERVAL_S)
        _log("PREMARKET_WAIT", {"time_et": now_et.strftime("%H:%M"), "wait_s": int(wait_s)})
        print(f"  [PREMARKET] {now_et.strftime('%H:%M ET')} — market opens at 09:30. "
              f"Sleeping {sleep_s:.0f}s ...")
        time.sleep(sleep_s)

    # ----------------------------------------------------------------
    # Wire up the 6 layers for the intraday session
    # ----------------------------------------------------------------
    feed    = AlpacaMinuteBarFeed(api_key=api_key, api_secret=api_secret, data_base_url=data_url)
    gate    = RegimeGate(mode="precomputed", regime_map_path=str(regime_map_p))
    risk    = PortfolioRiskControls(
                  portfolio_usd,
                  max_open_positions=max_positions,
                  max_position_size_pct=max_size_pct,
                  daily_loss_limit_pct=loss_limit,
              )
    broker  = AlpacaPaperAdapter(
                  api_key=api_key,
                  api_secret=api_secret,
                  paper_base_url=paper_url,
                  roundtrip_slippage_bp=slippage_bp,
                  submit_orders=submit_orders,
              )
    tlogger = TradeLogger(output_dir=str(output_dir), strategy_id=_STRATEGY_ID)
    manager = IntradaySessionManager(gate, risk, broker, tlogger, portfolio_usd, session_date)

    # Open session: regime check + open logger + init risk engine
    regime_ok = manager.open_session(tickers)
    _log("SESSION_OPENED", {
        "regime_ok":     regime_ok,
        "regime":        manager.regime_label,
        "submit_orders": submit_orders,
    })

    # Regime blocked — write daily summary (no trades) and exit early
    if not regime_ok:
        summary = manager.close_session()
        _log("SESSION_COMPLETE_REGIME_BLOCKED", {"regime": summary.get("regime_label")})
        print(f"  [REGIME] Gate closed ({manager.regime_label}) — no trades today. Exiting.")
        return summary

    # ----------------------------------------------------------------
    # Phase 2+3: SESSION — active intraday poll every 60 seconds
    # Fetches new 1-min bars from Alpaca, feeds them to the session
    # manager, and fires entries the moment the signal appears.
    # ----------------------------------------------------------------
    _log("SESSION_PHASE_ENTERED")
    print(f"\n  [SESSION] Market hours. Polling every {_POLL_INTERVAL_S}s for live bars ...")

    while True:
        now_et = _now_et()

        if now_et.time() >= _EOD_TRIGGER:
            _log("EOD_TRIGGER_REACHED", {"time_et": now_et.strftime("%H:%M")})
            break

        if now_et.time() >= _POST_CLOSE_HARD:
            _log("POST_CLOSE_HARD_LIMIT_REACHED", {"time_et": now_et.strftime("%H:%M")})
            break

        bar_data = feed.fetch_session_bars(tickers, session_date)
        cycle    = manager.update(bar_data)

        _log("SESSION_POLL", {
            "time_et":     now_et.strftime("%H:%M"),
            "new_bars":    cycle.get("new_bars_processed", 0),
            "new_signals": cycle.get("new_signals", 0),
            "new_entries": cycle.get("new_entries", 0),
            "open_pos":    manager.open_position_count(),
        })

        if cycle.get("new_entries", 0) > 0:
            print(f"  [SESSION] {now_et.strftime('%H:%M ET')} — "
                  f"ENTRY FIRED ({cycle['new_entries']} new position(s)). "
                  f"Open: {manager.open_position_count()}")
        elif cycle.get("new_bars_processed", 0) > 0:
            print(f"  [SESSION] {now_et.strftime('%H:%M ET')} — "
                  f"+{cycle['new_bars_processed']} bar(s). "
                  f"Open: {manager.open_position_count()}")

        time.sleep(_POLL_INTERVAL_S)

    # ----------------------------------------------------------------
    # Phase 4: EOD — fetch final bars, force-exit all positions, close
    # ----------------------------------------------------------------
    _log("EOD_EXIT_STARTED")
    print(f"\n  [EOD] {_now_et().strftime('%H:%M ET')} — flattening all positions ...")

    final_bars = feed.fetch_session_bars(tickers, session_date)
    manager.force_eod_exit(final_bars)
    summary = manager.close_session()

    _log("SESSION_COMPLETE", {
        "signals": summary.get("signals_emitted", 0),
        "trades":  summary.get("total_trades_entered", 0),
        "pnl_pct": summary.get("total_pnl_pct", 0.0),
        "regime":  summary.get("regime_label", "unknown"),
    })

    print(f"  [DONE] Session complete for {session_date}.")
    return summary


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Daily automation launcher — intraday_same_day Alpaca paper track.\n"
            "Starts premarket, monitors the session, and triggers EOD batch at 16:05 ET."
        )
    )
    parser.add_argument(
        "--session-date", default=None,
        help="YYYY-MM-DD. Defaults to today. Past dates skip time guards.",
    )
    parser.add_argument(
        "--tickers", nargs="+", default=None,
        help="Space-separated ticker list (overrides ticker file).",
    )
    parser.add_argument(
        "--ticker-file", default=None,
        help="CSV with a 'ticker' column.",
    )
    parser.add_argument(
        "--config", default=str(_DEFAULT_CONFIG),
        help="Path to config YAML.",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show DEBUG-level logging.",
    )
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    # ------------------------------------------------------------------
    # Load config
    # ------------------------------------------------------------------
    config_path = Path(args.config)
    if not config_path.exists():
        config_path = _resolve_path(args.config)
    if not config_path.exists():
        print(f"Error: config not found: {config_path}")
        sys.exit(1)
    config = _load_config(config_path)
    logging.info(f"Config loaded: {config_path.name}")

    # ------------------------------------------------------------------
    # Regime map check
    # ------------------------------------------------------------------
    regime_map_path = _resolve_path(str(config.get("regime_map_path", "")))
    if not regime_map_path.exists():
        print(
            f"Error: regime map not found: {regime_map_path}\n"
            f"Run: python 2_0_agent_engineering/engineering_source_code/"
            f"market_climate_engine/engineering_build_regime_map.py"
        )
        sys.exit(1)

    # ------------------------------------------------------------------
    # Session date
    # ------------------------------------------------------------------
    today = datetime.date.today()
    if args.session_date:
        try:
            session_date = datetime.date.fromisoformat(args.session_date)
        except ValueError:
            print(f"Error: invalid session-date '{args.session_date}'. Use YYYY-MM-DD.")
            sys.exit(1)
        skip_time_guards = session_date < today
    else:
        session_date = today
        skip_time_guards = False

    # ------------------------------------------------------------------
    # Ticker list
    # ------------------------------------------------------------------
    if args.tickers:
        tickers = args.tickers
    else:
        ticker_file = Path(args.ticker_file) if args.ticker_file else _DEFAULT_TICKER_FILE
        if not ticker_file.exists():
            print(f"Error: ticker file not found: {ticker_file}")
            sys.exit(1)
        df_t = pd.read_csv(ticker_file)
        if "ticker" not in df_t.columns:
            print(f"Error: ticker file must have a 'ticker' column. Found: {list(df_t.columns)}")
            sys.exit(1)
        tickers = df_t["ticker"].dropna().tolist()

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    submit_active = config.get("alpaca_submit_orders", False)
    print(f"\n{'='*60}")
    print(f" Daily Launcher  : intraday_same_day")
    print(f" Session date    : {session_date}")
    print(f" Candidates      : {len(tickers)}")
    print(f" Regime map      : {regime_map_path.name}")
    print(f" Submit mode     : {'LIVE PAPER ORDERS' if submit_active else 'DRY-RUN (no orders sent)'}")
    print(f" Time guards     : {'SKIPPED (past date)' if skip_time_guards else 'ACTIVE (premarket to 16:05 ET)'}")
    print(f"{'='*60}\n")

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    summary = run_daily_session(
        session_date=session_date,
        tickers=tickers,
        config=config,
        output_dir=_OUTPUT_DIR,
        skip_time_guards=skip_time_guards,
    )

    # ------------------------------------------------------------------
    # Final summary print
    # ------------------------------------------------------------------
    if summary.get("skipped"):
        print(f"\nSkipped: {summary['skipped']}")
        return

    print(f"\n{'='*60}")
    print(" LAUNCHER SUMMARY")
    print(f"{'='*60}")
    print(f"  Date     : {summary.get('session_date', session_date)}")
    print(f"  Regime   : {summary.get('regime_label', 'unknown')}")
    print(f"  Signals  : {summary.get('signals_emitted', 0)}")
    print(f"  Trades   : {summary.get('total_trades_entered', 0)}")
    print(f"  P&L      : {summary.get('total_pnl_pct', 0.0):+.3f}%  "
          f"(${summary.get('total_pnl', 0.0):+.2f})")
    print(f"  Submit   : {'LIVE PAPER ORDERS' if submit_active else 'DRY-RUN'}")
    print(f"{'='*60}")

    output_dir_path = _OUTPUT_DIR / _STRATEGY_ID
    print(f"\nOutput files: {output_dir_path}/")
    if output_dir_path.exists():
        date_str = session_date.strftime("%Y_%m_%d")
        for prefix in ["signals", "fills", "daily_summary", "launcher_log"]:
            candidates = sorted(output_dir_path.glob(f"{prefix}__{date_str}*"))
            if candidates:
                print(f"  {candidates[0].name}")


if __name__ == "__main__":
    main()
