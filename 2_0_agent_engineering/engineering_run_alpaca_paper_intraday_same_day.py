"""
engineering_run_alpaca_paper_intraday_same_day.py

Alpaca Paper Trading entrypoint for the intraday_same_day strategy track.

Fetches live/recent 1-minute bars from Alpaca Data v2, runs the
failed_opening_drive_and_reclaim__child_001_v1 strategy module, and either:
  - logs the intended orders (dry-run, default), or
  - submits market orders to Alpaca Paper Trading (when submit_orders=true)

All 6 engineering layers are wired:
    1. Regime gate          (precomputed CSV — same as phase_e0)
    2. Alpaca minute bars   (live/recent data from Alpaca Data v2)
    3. Strategy module      (frozen V1 detector — unchanged from phase_e0)
    4. Risk engine          (portfolio controls — unchanged from phase_e0)
    5. Alpaca paper broker  (dry-run by default; submit_orders=true for live)
    6. Trade logger         (same structured CSV/JSON output as phase_e0)

Usage:
    # Connectivity check only (no session logic)
    python engineering_run_alpaca_paper_intraday_same_day.py --validate

    # Dry-run for today (default: submit_orders=false)
    python engineering_run_alpaca_paper_intraday_same_day.py

    # Dry-run for a specific date (Alpaca data must cover that date)
    python engineering_run_alpaca_paper_intraday_same_day.py --session-date 2026-03-24

    # With specific tickers
    python engineering_run_alpaca_paper_intraday_same_day.py --tickers SOUN IONQ MARA

    # Enable live paper order submission (ONLY when ready)
    # 1. Set in config: alpaca_submit_orders: true
    # 2. Or override at runtime:
    python engineering_run_alpaca_paper_intraday_same_day.py --submit-orders

Credentials (set before running):
    PowerShell (Windows):
        $env:ALPACA_API_KEY    = "your_key"
        $env:ALPACA_API_SECRET = "your_secret"

    Bash/zsh (Linux/macOS):
        export ALPACA_API_KEY=your_key
        export ALPACA_API_SECRET=your_secret

Run from repo root:
    # PowerShell
    cd b:\\git_hub\\claude_code\\ai_trading_assistant
    python 2_0_agent_engineering/engineering_run_alpaca_paper_intraday_same_day.py --validate

    # Bash
    cd b:/git_hub/claude_code/ai_trading_assistant
    python 2_0_agent_engineering/engineering_run_alpaca_paper_intraday_same_day.py --validate
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import re
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_SCRIPT_PATH = Path(os.path.abspath(__file__))
_ENGINEERING_ROOT = _SCRIPT_PATH.parent
_REPO_ROOT = _ENGINEERING_ROOT.parent

if str(_ENGINEERING_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENGINEERING_ROOT))

# ---------------------------------------------------------------------------
# Internal imports
# ---------------------------------------------------------------------------
from engineering_source_code.market_climate_engine.engineering_market_climate_regime_gate import RegimeGate
from engineering_source_code.risk_engine.engineering_risk_portfolio_controls import PortfolioRiskControls
from engineering_source_code.production_utilities.engineering_trade_logger import TradeLogger
from engineering_source_code.signal_runners.engineering_signal_runner_intraday_same_day import IntradaySameDaySignalRunner
from engineering_source_code.data_feeds.engineering_data_feed_alpaca_minute_bars import AlpacaMinuteBarFeed
from engineering_source_code.broker_execution_adapters.engineering_broker_alpaca_paper_adapter import AlpacaPaperAdapter

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
_DEFAULT_CONFIG = (
    _ENGINEERING_ROOT
    / "engineering_configs"
    / "engineering_config__alpaca_paper__failed_opening_drive_and_reclaim__child_001_v1.yaml"
)
_DEFAULT_TICKER_FILE = (
    _REPO_ROOT / "1_0_strategy_research" / "research_configs" / "research_working_universe_intraday_liquid.csv"
)
_OUTPUT_DIR = _ENGINEERING_ROOT / "engineering_runtime_outputs"
_STRATEGY_ID = "failed_opening_drive_and_reclaim__child_001_v1"


def _resolve_path(path_str: str) -> Path:
    p = Path(path_str)
    if p.is_absolute():
        return p
    candidate = _REPO_ROOT / p
    if candidate.exists():
        return candidate
    return p


def _load_config(config_path: Path) -> dict:
    """
    Load a flat key: value YAML config file.

    Handles string values (quoted or unquoted), booleans (true/false),
    integers, floats, and null. Comments (#) and blank lines are ignored.
    This loader works without the PyYAML module.
    """
    result: dict = {}
    with open(config_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r'^([\w][\w_\.]*):\s*(.*)$', line)
            if not m:
                continue
            key = m.group(1)
            raw = m.group(2).strip().strip('"').strip("'")
            # Inline comment removal
            raw = re.sub(r'\s+#.*$', '', raw).strip()
            # Type coercion
            if raw.lower() == "true":
                result[key] = True
            elif raw.lower() == "false":
                result[key] = False
            elif raw.lower() in ("null", "~", ""):
                result[key] = None
            else:
                try:
                    result[key] = int(raw)
                except ValueError:
                    try:
                        result[key] = float(raw)
                    except ValueError:
                        result[key] = raw
    return result


def _read_credentials(config: dict) -> tuple[str, str]:
    """Read Alpaca credentials from environment variables named in config."""
    key_env = config.get("alpaca_api_key_env", "ALPACA_API_KEY")
    secret_env = config.get("alpaca_api_secret_env", "ALPACA_API_SECRET")

    api_key = os.environ.get(key_env, "")
    api_secret = os.environ.get(secret_env, "")

    if not api_key:
        print(f"Error: environment variable '{key_env}' is not set.")
        print(f"  PowerShell : $env:{key_env} = \"your_alpaca_api_key\"")
        print(f"  Bash/zsh   : export {key_env}=your_alpaca_api_key")
        sys.exit(1)
    if not api_secret:
        print(f"Error: environment variable '{secret_env}' is not set.")
        print(f"  PowerShell : $env:{secret_env} = \"your_alpaca_api_secret\"")
        print(f"  Bash/zsh   : export {secret_env}=your_alpaca_api_secret")
        sys.exit(1)

    return api_key, api_secret


def run_validation(config: dict) -> None:
    """
    Connectivity validation mode.

    Checks:
      1. Alpaca Paper account access (broker endpoint)
      2. Alpaca Data v2 access (data endpoint — SPY spot check)
    Does not run any session logic or submit any orders.
    """
    api_key, api_secret = _read_credentials(config)

    paper_url = config.get("alpaca_paper_base_url", "https://paper-api.alpaca.markets")
    data_url = config.get("alpaca_data_base_url", "https://data.alpaca.markets")

    print(f"\n{'='*60}")
    print(" ALPACA CONNECTIVITY VALIDATION")
    print(f"{'='*60}")
    print(f" Paper URL : {paper_url}")
    print(f" Data URL  : {data_url}")
    print(f"{'='*60}\n")

    # Broker (account) check
    broker = AlpacaPaperAdapter(
        api_key=api_key,
        api_secret=api_secret,
        paper_base_url=paper_url,
        submit_orders=False,
    )
    broker_result = broker.validate_connectivity()
    status = "OK" if broker_result["ok"] else "FAIL"
    print(f"[{status}] Broker account : {broker_result['message']}")
    if broker_result.get("ok"):
        print(f"       Portfolio value: ${broker_result.get('portfolio_value', 'N/A')}")
        print(f"       Buying power   : ${broker_result.get('buying_power', 'N/A')}")
    else:
        print(f"       Error: {broker_result.get('error', 'unknown')}")

    # Data feed check
    feed = AlpacaMinuteBarFeed(
        api_key=api_key,
        api_secret=api_secret,
        data_base_url=data_url,
    )
    feed_result = feed.validate_connectivity()
    status = "OK" if feed_result["ok"] else "FAIL"
    print(f"\n[{status}] Data feed      : {feed_result['message']}")
    if not feed_result.get("ok"):
        print(f"       Error: {feed_result.get('error', 'unknown')}")

    # Open positions check
    print("\nOpen Alpaca Paper positions:")
    positions = broker.get_open_positions()
    if not positions:
        print("  (none)")
    else:
        for pos in positions:
            print(f"  {pos.get('symbol')}: {pos.get('qty')} shares @ avg ${pos.get('avg_entry_price')}")

    print(f"\n{'='*60}")
    all_ok = broker_result["ok"] and feed_result["ok"]
    print(f" Validation {'PASSED' if all_ok else 'FAILED'}")
    print(f"{'='*60}\n")

    if not all_ok:
        sys.exit(1)


def run_alpaca_session(
    session_date: datetime.date,
    tickers: list,
    config: dict,
    submit_orders_override: bool | None,
    output_dir: Path,
) -> dict:
    """Wire all 6 layers and run one session using Alpaca data + broker."""
    api_key, api_secret = _read_credentials(config)

    paper_url = config.get("alpaca_paper_base_url", "https://paper-api.alpaca.markets")
    data_url = config.get("alpaca_data_base_url", "https://data.alpaca.markets")
    regime_map_path = _resolve_path(str(config.get("regime_map_path", "")))

    submit_orders = config.get("alpaca_submit_orders", False)
    if submit_orders_override is not None:
        submit_orders = submit_orders_override

    slippage_bp = float(config.get("roundtrip_slippage_bp", 10))
    portfolio_usd = float(config.get("portfolio_value_usd", 50000))
    max_positions = int(config.get("max_open_positions", 5))
    max_size_pct = float(config.get("max_position_size_pct", 0.10))
    loss_limit = float(config.get("daily_loss_limit_pct", -0.02))

    # Fetch bars from Alpaca
    feed = AlpacaMinuteBarFeed(
        api_key=api_key,
        api_secret=api_secret,
        data_base_url=data_url,
    )
    bar_data = feed.fetch_session_bars(tickers, session_date)

    if not bar_data:
        logging.error("No bar data fetched from Alpaca — cannot run session.")
        return {"error": "no_bar_data", "session_date": str(session_date)}

    logging.info(
        f"Alpaca bar data fetched for {len(bar_data)} of {len(tickers)} tickers."
    )

    # Wire layers
    gate = RegimeGate(mode="precomputed", regime_map_path=str(regime_map_path))
    risk = PortfolioRiskControls(
        portfolio_usd,
        max_open_positions=max_positions,
        max_position_size_pct=max_size_pct,
        daily_loss_limit_pct=loss_limit,
    )
    broker = AlpacaPaperAdapter(
        api_key=api_key,
        api_secret=api_secret,
        paper_base_url=paper_url,
        roundtrip_slippage_bp=slippage_bp,
        submit_orders=submit_orders,
    )
    tlogger = TradeLogger(output_dir=str(output_dir), strategy_id=_STRATEGY_ID)
    runner = IntradaySameDaySignalRunner(gate, risk, broker, tlogger, portfolio_usd)

    return runner.run_session(session_date, list(bar_data.keys()), bar_data)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Alpaca Paper Trading runner — intraday_same_day track, V1 strategy."
    )
    parser.add_argument(
        "--session-date",
        default=None,
        help="YYYY-MM-DD (default: today).",
    )
    parser.add_argument(
        "--tickers", nargs="+", default=None,
        help="Space-separated list of tickers.",
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
        "--submit-orders", action="store_true",
        help="Enable live paper order submission (overrides config alpaca_submit_orders).",
    )
    parser.add_argument(
        "--validate", action="store_true",
        help="Run connectivity validation only (no session logic).",
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

    # Load config
    config_path = Path(args.config)
    if not config_path.exists():
        config_path = _resolve_path(args.config)
    if not config_path.exists():
        print(f"Error: config not found: {config_path}")
        sys.exit(1)

    config = _load_config(config_path)
    logging.info(f"Config loaded: {config_path.name}")

    # Validation-only mode
    if args.validate:
        run_validation(config)
        return

    # Regime map check
    regime_map_path = _resolve_path(str(config.get("regime_map_path", "")))
    if not regime_map_path.exists():
        print(
            f"Error: regime map not found: {regime_map_path}\n"
            f"Run: python 2_0_agent_engineering/engineering_source_code/market_climate_engine/"
            f"engineering_build_regime_map.py"
        )
        sys.exit(1)

    # Session date
    if args.session_date:
        try:
            session_date = datetime.date.fromisoformat(args.session_date)
        except ValueError:
            print(f"Error: invalid session-date '{args.session_date}'. Use YYYY-MM-DD.")
            sys.exit(1)
    else:
        session_date = datetime.date.today()

    # Ticker list
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

    # Submit-orders override
    submit_override = True if args.submit_orders else None
    submit_active = submit_override if submit_override is not None else config.get("alpaca_submit_orders", False)

    print(f"\n{'='*60}")
    print(f" Alpaca Paper: {session_date}  |  {len(tickers)} candidates")
    print(f" Regime map  : {regime_map_path.name}")
    print(f" Slippage    : {config.get('roundtrip_slippage_bp', 10)}bp roundtrip")
    print(f" Portfolio   : ${float(config.get('portfolio_value_usd', 50000)):,.0f}")
    print(f" Submit mode : {'LIVE PAPER ORDERS' if submit_active else 'DRY-RUN (no orders sent)'}")
    print(f"{'='*60}\n")

    if submit_active:
        print("WARNING: submit_orders=true — market orders WILL be submitted to Alpaca Paper.")
        print("Press Enter to continue or Ctrl+C to abort.")
        try:
            input()
        except KeyboardInterrupt:
            print("\nAborted.")
            sys.exit(0)

    summary = run_alpaca_session(
        session_date=session_date,
        tickers=tickers,
        config=config,
        submit_orders_override=submit_override,
        output_dir=_OUTPUT_DIR,
    )

    print(f"\n{'='*60}")
    print(" SESSION SUMMARY")
    print(f"{'='*60}")
    print(json.dumps(summary, indent=2, default=str))

    regime = summary.get("regime_label", "unknown")
    blocked = summary.get("trades_blocked_by_regime", False)
    trades = summary.get("total_trades_entered", 0)
    pnl_pct = summary.get("total_pnl_pct", 0.0)
    signals = summary.get("signals_emitted", 0)

    print(f"\nHighlights:")
    print(f"  Regime       : {regime}")
    print(f"  Gate blocked : {blocked}")
    print(f"  Signals      : {signals}")
    print(f"  Trades       : {trades}")
    print(f"  Total P&L    : {pnl_pct:+.3f}%  (${summary.get('total_pnl', 0):+.2f})")
    print(f"  Submit mode  : {'LIVE PAPER ORDERS SUBMITTED' if submit_active else 'DRY-RUN'}")

    output_dir_path = _OUTPUT_DIR / _STRATEGY_ID
    print(f"\nOutput files: {output_dir_path}/")
    if output_dir_path.exists():
        date_str = session_date.strftime("%Y_%m_%d")
        for suffix in ["signals", "fills", "daily_summary"]:
            candidates = list(output_dir_path.glob(f"{suffix}__{date_str}*"))
            if candidates:
                print(f"  {candidates[0].name}")


if __name__ == "__main__":
    main()
