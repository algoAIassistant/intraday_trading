"""
engineering_run_paper_replay_intraday_same_day.py

Replay entrypoint for the intraday_same_day paper trading workflow.

Runs one complete session for a given date against the intraday 1-minute
bar cache using the failed_opening_drive_and_reclaim__child_001_v1 module.

Usage:
    python engineering_run_paper_replay_intraday_same_day.py --session-date 2025-06-05
    python engineering_run_paper_replay_intraday_same_day.py --session-date 2026-03-24 --tickers SOUN IONQ MARA
    python engineering_run_paper_replay_intraday_same_day.py --session-date 2025-11-10 --ticker-file path/to/tickers.csv
    python engineering_run_paper_replay_intraday_same_day.py --session-date 2025-06-05 --config path/to/config.yaml --slippage-bp 0

Arguments:
    --session-date    YYYY-MM-DD (required)
    --tickers         Space-separated list of tickers (optional)
    --ticker-file     CSV with a 'ticker' column (optional; default: research liquid universe)
    --config          Path to config YAML (optional; default: standard V1 config)
    --slippage-bp     Roundtrip slippage in basis points (optional; overrides config)
    --portfolio-usd   Portfolio value in USD (optional; overrides config)
    --verbose         Show DEBUG-level logging

Run from repo root or from 2_0_agent_engineering/:
    cd b:/git_hub/claude_code/ai_trading_assistant
    python 2_0_agent_engineering/engineering_run_paper_replay_intraday_same_day.py --session-date 2025-06-05
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap — works when run from repo root or from 2_0_agent_engineering/
# ---------------------------------------------------------------------------
_SCRIPT_PATH = Path(os.path.abspath(__file__))
_ENGINEERING_ROOT = _SCRIPT_PATH.parent   # 2_0_agent_engineering/
_REPO_ROOT = _ENGINEERING_ROOT.parent

# Add engineering root to sys.path so all internal packages resolve
if str(_ENGINEERING_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENGINEERING_ROOT))

# ---------------------------------------------------------------------------
# Internal imports
# ---------------------------------------------------------------------------
from engineering_source_code.market_climate_engine.engineering_market_climate_regime_gate import RegimeGate
from engineering_source_code.risk_engine.engineering_risk_portfolio_controls import PortfolioRiskControls
from engineering_source_code.broker_execution_adapters.engineering_broker_paper_fill_simulator import PaperFillSimulator
from engineering_source_code.production_utilities.engineering_trade_logger import TradeLogger
from engineering_source_code.signal_runners.engineering_signal_runner_intraday_same_day import IntradaySameDaySignalRunner

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
_DEFAULT_CONFIG = _ENGINEERING_ROOT / "engineering_configs" / "engineering_config__failed_opening_drive_and_reclaim__child_001_v1.yaml"
_DEFAULT_TICKER_FILE = _REPO_ROOT / "1_0_strategy_research" / "research_configs" / "research_working_universe_intraday_liquid.csv"
_INTRADAY_CACHE_DIR = _REPO_ROOT / "1_0_strategy_research" / "research_data_cache" / "intraday_1m"
_OUTPUT_DIR = _ENGINEERING_ROOT / "engineering_runtime_outputs"
_STRATEGY_ID = "failed_opening_drive_and_reclaim__child_001_v1"

# Windows reserved filenames that need mangling in the cache
_WIN_RESERVED = {"CON","PRN","AUX","NUL","COM1","COM2","COM3","COM4","COM5",
                 "COM6","COM7","COM8","COM9","LPT1","LPT2","LPT3","LPT4",
                 "LPT5","LPT6","LPT7","LPT8","LPT9"}


def _cache_path(ticker: str) -> Path:
    stem = f"{ticker}__reserved" if ticker.upper() in _WIN_RESERVED else ticker
    return _INTRADAY_CACHE_DIR / f"{stem}.parquet"


def _resolve_path(path_str: str) -> Path:
    """Resolve a path that may be absolute or relative to repo root."""
    p = Path(path_str)
    if p.is_absolute():
        return p
    candidate = _REPO_ROOT / p
    if candidate.exists():
        return candidate
    return p  # return as-is; caller will handle missing file error


def _load_config(config_path: Path) -> dict:
    """Load YAML config. Returns a plain dict."""
    try:
        import yaml
    except ImportError:
        # Minimal YAML fallback for simple key: value configs
        import re
        result = {}
        with open(config_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = re.match(r'^(\w[\w_]*):\s*(.+)$', line)
                if m:
                    key, val = m.group(1), m.group(2).strip().strip('"')
                    result[key] = val
        return result

    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_replay(
    session_date: datetime.date,
    tickers: list[str],
    regime_map_path: Path,
    portfolio_value_usd: float,
    slippage_bp: float,
    output_dir: Path,
) -> dict:
    """Wire up all 6 layers and run one session. Returns summary dict."""
    gate    = RegimeGate(mode="precomputed", regime_map_path=str(regime_map_path))
    risk    = PortfolioRiskControls(
                  portfolio_value_usd,
                  max_open_positions=5,
                  max_position_size_pct=0.10,
                  daily_loss_limit_pct=-0.02,
              )
    broker  = PaperFillSimulator(roundtrip_slippage_bp=slippage_bp)
    tlogger = TradeLogger(output_dir=str(output_dir), strategy_id=_STRATEGY_ID)
    runner  = IntradaySameDaySignalRunner(gate, risk, broker, tlogger, portfolio_value_usd)

    # Load bar data
    bar_data: dict[str, pd.DataFrame] = {}
    missing = []
    for ticker in tickers:
        p = _cache_path(ticker)
        if p.exists():
            bar_data[ticker] = pd.read_parquet(p)
        else:
            missing.append(ticker)

    if missing:
        logging.warning(
            f"No intraday cache for {len(missing)} ticker(s): {missing[:10]}"
            + (" ..." if len(missing) > 10 else "")
        )

    if not bar_data:
        logging.error("No bar data loaded — cannot run session.")
        return {"error": "no_bar_data", "missing_tickers": missing}

    logging.info(f"Bar data loaded for {len(bar_data)} of {len(tickers)} tickers.")
    return runner.run_session(session_date, list(bar_data.keys()), bar_data)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Paper replay runner — intraday_same_day track, V1 strategy."
    )
    parser.add_argument("--session-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--tickers", nargs="+", default=None,
                        help="Space-separated list of tickers.")
    parser.add_argument("--ticker-file", default=None,
                        help="CSV with a 'ticker' column.")
    parser.add_argument("--config", default=str(_DEFAULT_CONFIG),
                        help="Path to config YAML.")
    parser.add_argument("--slippage-bp", type=float, default=None,
                        help="Roundtrip slippage in basis points (overrides config).")
    parser.add_argument("--portfolio-usd", type=float, default=None,
                        help="Portfolio value in USD (overrides config).")
    parser.add_argument("--verbose", action="store_true",
                        help="Show DEBUG-level logging.")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Parse session date
    try:
        session_date = datetime.date.fromisoformat(args.session_date)
    except ValueError:
        print(f"Error: invalid session-date '{args.session_date}'. Use YYYY-MM-DD.")
        sys.exit(1)

    # Load config
    config_path = Path(args.config)
    if not config_path.exists():
        config_path = _resolve_path(args.config)
    if not config_path.exists():
        print(f"Error: config not found: {config_path}")
        sys.exit(1)

    config = _load_config(config_path)
    logging.info(f"Config loaded: {config_path.name}")

    # Resolve regime map path
    raw_regime_path = (
        config.get("regime_gate", {}).get("regime_map_path")
        or config.get("regime_map_path", "")
    )
    regime_map_path = _resolve_path(raw_regime_path)
    if not regime_map_path.exists():
        print(
            f"Error: regime map not found: {regime_map_path}\n"
            f"Run: python 2_0_agent_engineering/engineering_source_code/market_climate_engine/engineering_build_regime_map.py"
        )
        sys.exit(1)

    # Resolve slippage and portfolio value
    paper_cfg = config.get("paper_trading", {})
    risk_cfg  = config.get("risk", {})

    slippage_bp = args.slippage_bp
    if slippage_bp is None:
        slippage_bp = float(paper_cfg.get("roundtrip_slippage_bp", 10))

    portfolio_usd = args.portfolio_usd
    if portfolio_usd is None:
        portfolio_usd = float(risk_cfg.get("portfolio_value_usd", 50000))

    # Resolve ticker list
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

    print(f"\n{'='*60}")
    print(f" Paper replay: {session_date}  |  {len(tickers)} candidates")
    print(f" Regime map  : {regime_map_path.name}")
    print(f" Slippage    : {slippage_bp}bp roundtrip")
    print(f" Portfolio   : ${portfolio_usd:,.0f}")
    print(f"{'='*60}\n")

    summary = run_replay(
        session_date=session_date,
        tickers=tickers,
        regime_map_path=regime_map_path,
        portfolio_value_usd=portfolio_usd,
        slippage_bp=slippage_bp,
        output_dir=_OUTPUT_DIR,
    )

    print(f"\n{'='*60}")
    print(" SESSION SUMMARY")
    print(f"{'='*60}")
    print(json.dumps(summary, indent=2, default=str))

    # Human-readable highlights
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
