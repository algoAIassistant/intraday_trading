"""
engineering_signal_runner_intraday_same_day.py

Signal runner / orchestrator for the intraday_same_day strategy track.

Coordinates all 6 layers for a complete trading session:
    1. Regime gate  — closes the day if month is bearish
    2. Strategy module  — detects drive + reclaim per ticker
    3. Risk engine  — approves entries and manages portfolio-level controls
    4. Broker adapter  — simulates or executes fills
    5. Trade logger  — logs everything to structured CSV/JSON
    6. Session exit  — forces close of all positions at 15:59 ET

Data format contract (matches research parquet cache exactly):
    bar_data : Dict[str, pd.DataFrame]
        Keys   : ticker symbol strings
        Values : DataFrame with DatetimeIndex (tz-aware, America/New_York)
                 Index = bar OPEN time (Polygon.io convention: 09:30 = first bar)
                 Columns : open, high, low, close, volume

Usage (replay / paper-trading mode):
    runner = IntradaySameDaySignalRunner(
        regime_gate=gate,
        risk_engine=risk,
        broker=broker,
        trade_logger=trade_logger,
        portfolio_value_usd=50_000.0,
    )
    summary = runner.run_session(
        session_date=date(2025, 6, 15),
        candidate_tickers=["SOUN", "IONQ", "MARA"],
        bar_data={"SOUN": df_soun, "IONQ": df_ionq, "MARA": df_mara},
    )

See engineering_documents/engineering_module_spec__failed_opening_drive_and_reclaim__child_001_v1.md
for the full data format and wiring guide.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date, datetime
from datetime import time as dt_time
from typing import Dict, List, Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap — allows running from any directory
# ---------------------------------------------------------------------------
_RUNNER_DIR = os.path.dirname(os.path.abspath(__file__))
_ENGINEERING_ROOT = os.path.normpath(os.path.join(_RUNNER_DIR, "..", ".."))
if _ENGINEERING_ROOT not in sys.path:
    sys.path.insert(0, _ENGINEERING_ROOT)

# ---------------------------------------------------------------------------
# Internal imports
# ---------------------------------------------------------------------------
from engineering_source_code.market_climate_engine.engineering_market_climate_regime_gate import (
    RegimeGate,
)
from engineering_source_code.risk_engine.engineering_risk_portfolio_controls import (
    PortfolioRiskControls,
    RiskDecision,
)
from engineering_source_code.broker_execution_adapters.engineering_broker_paper_fill_simulator import (
    PaperFillSimulator,
    Fill,
)
from engineering_source_code.production_utilities.engineering_trade_logger import (
    TradeLogger,
)
from integrated_strategy_modules.intraday_same_day.failed_opening_drive_and_reclaim__child_001_v1.engineering_strategy_module__failed_opening_drive_and_reclaim__child_001_v1 import (
    FailedOpeningDriveReclaimV1,
    StrategySignal,
    STRATEGY_ID,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session constants
# ---------------------------------------------------------------------------
_SESSION_START = "09:30"
_SESSION_END = "15:59"
_EXIT_TIME = dt_time(15, 59)


class IntradaySameDaySignalRunner:
    """
    Orchestrator for the intraday_same_day strategy track.

    Designed to be the first brick in a future multi-agent ecosystem:
    - All strategy-specific logic is encapsulated in the strategy module
    - All risk logic is encapsulated in the risk engine
    - The signal runner is strategy-agnostic in structure (strategy module
      is pluggable; additional modules can be added alongside V1)

    Processes one complete session via run_session(). Safe to call multiple
    times for multi-day replay — all state is reset per call.
    """

    def __init__(
        self,
        regime_gate: RegimeGate,
        risk_engine: PortfolioRiskControls,
        broker: PaperFillSimulator,
        trade_logger: TradeLogger,
        portfolio_value_usd: float,
    ) -> None:
        self.regime_gate = regime_gate
        self.risk_engine = risk_engine
        self.broker = broker
        self.trade_logger = trade_logger
        self.portfolio_value_usd = portfolio_value_usd

    # ------------------------------------------------------------------
    # Primary entry point
    # ------------------------------------------------------------------

    def run_session(
        self,
        session_date: date,
        candidate_tickers: List[str],
        bar_data: Dict[str, pd.DataFrame],
    ) -> dict:
        """
        Run a complete intraday trading session.

        Parameters:
            session_date       : the trading date
            candidate_tickers  : list of tickers to evaluate for setups
            bar_data           : {ticker: DataFrame} in research cache format
                                 (DatetimeIndex America/New_York, bar open time)

        Returns:
            session_summary dict (also logged to daily_summary JSON)
        """
        logger.info(f"=== Session {session_date}: {len(candidate_tickers)} candidates ===")

        # Session-level state
        entry_fills: Dict[str, Fill] = {}
        session_bar_data: Dict[str, pd.DataFrame] = {}  # trimmed to session hours

        # Open logger and risk engine for the day
        self.trade_logger.begin_session(session_date)
        self.risk_engine.begin_session(session_date, self.portfolio_value_usd)

        # ----------------------------------------------------------------
        # Step 1: Regime gate
        # ----------------------------------------------------------------
        regime_ok = self.regime_gate.is_non_bearish(session_date)
        regime_label = self.regime_gate.get_regime_label(session_date)

        if not regime_ok:
            logger.info(
                f"Session {session_date}: REGIME GATE CLOSED ({regime_label}) — "
                f"no trades today."
            )
            summary = self._build_summary(
                session_date, regime_label, trades_blocked_by_regime=True
            )
            self.trade_logger.log_daily_summary(summary)
            self.trade_logger.end_session()
            return summary

        logger.info(f"Session {session_date}: regime = {regime_label} — gate open.")

        # ----------------------------------------------------------------
        # Step 2: Slice session bars and extract session opens
        # ----------------------------------------------------------------
        for ticker in candidate_tickers:
            df = bar_data.get(ticker)
            if df is None or df.empty:
                continue
            session_df = _extract_session_bars(df, session_date)
            if session_df.empty or len(session_df) < 31:
                # Need at least 30 drive bars + 1 post-drive bar
                continue
            session_bar_data[ticker] = session_df

        # ----------------------------------------------------------------
        # Step 3: Initialise strategy modules for price-eligible tickers
        # ----------------------------------------------------------------
        strategy_instances: Dict[str, FailedOpeningDriveReclaimV1] = {}

        for ticker, session_df in session_bar_data.items():
            session_open = float(session_df.iloc[0]["open"])
            module = FailedOpeningDriveReclaimV1()
            eligible = module.reset_session(ticker, session_open, session_date)
            if eligible:
                strategy_instances[ticker] = module

        logger.info(
            f"Session {session_date}: {len(strategy_instances)} tickers price-eligible "
            f"($5-$20) of {len(session_bar_data)} with sufficient bars."
        )

        # ----------------------------------------------------------------
        # Step 4: Feed bars to each eligible ticker's strategy module
        # ----------------------------------------------------------------
        for ticker, module in strategy_instances.items():
            session_df = session_bar_data[ticker]

            for bar_time, bar in session_df.iterrows():
                bar_close = float(bar["close"])

                # Update unrealized P&L for open positions (for daily limit check)
                if ticker in entry_fills:
                    self.risk_engine.update_unrealized(ticker, bar_close)
                    continue  # already in a position — skip signal detection

                signal = module.on_bar(bar_time=bar_time, bar_close=bar_close)

                if signal is None:
                    continue

                # Signal fired — log and evaluate risk
                self.trade_logger.log_signal(signal)

                risk_decision = self.risk_engine.evaluate_entry(
                    ticker=ticker,
                    entry_price=signal.trigger_price,
                    session_date=session_date,
                )

                if not risk_decision.approved:
                    logger.info(
                        f"Entry BLOCKED by risk engine: {ticker} — {risk_decision.reason}"
                    )
                    continue

                # Execute paper fill
                entry_fill = self.broker.fill_entry(
                    ticker=ticker,
                    bar_time=bar_time,
                    bar_close=signal.trigger_price,
                    shares=risk_decision.position_size_shares,
                    session_date=session_date,
                    strategy_id=signal.strategy_id,
                )

                self.risk_engine.record_entry(
                    ticker, entry_fill.fill_price, entry_fill.shares
                )
                self.trade_logger.log_fill(entry_fill)
                entry_fills[ticker] = entry_fill

        # ----------------------------------------------------------------
        # Step 5: Force exit all open positions at 15:59 ET
        # ----------------------------------------------------------------
        open_tickers = list(entry_fills.keys())
        if open_tickers:
            logger.info(
                f"Session close: exiting {len(open_tickers)} open position(s) at 15:59 ET."
            )
            for ticker in open_tickers:
                exit_fill = self._execute_session_exit(
                    ticker=ticker,
                    session_date=session_date,
                    session_df=session_bar_data.get(ticker, pd.DataFrame()),
                    entry_fill=entry_fills[ticker],
                )
                if exit_fill is not None:
                    self.risk_engine.record_exit(ticker, exit_fill.fill_price)
                    self.trade_logger.log_fill(exit_fill)

        # ----------------------------------------------------------------
        # Step 6: Finalise and log
        # ----------------------------------------------------------------
        summary = self._build_summary(
            session_date, regime_label, trades_blocked_by_regime=False
        )
        self.trade_logger.log_daily_summary(summary)
        self.trade_logger.end_session()

        logger.info(
            f"=== Session {session_date} complete: "
            f"trades={summary.get('total_trades_entered', 0)}, "
            f"pnl={summary.get('total_pnl_pct', 0):+.3f}% ==="
        )
        return summary

    # ------------------------------------------------------------------
    # Exit execution
    # ------------------------------------------------------------------

    def _execute_session_exit(
        self,
        ticker: str,
        session_date: date,
        session_df: pd.DataFrame,
        entry_fill: Fill,
    ) -> Optional[Fill]:
        """Locate the 15:59 ET bar and simulate an exit fill."""
        if session_df.empty:
            logger.warning(f"No bar data for {ticker} at session exit — cannot close.")
            return None

        # Look for 15:59 bar (bar open time = 15:59)
        exit_bars = session_df[session_df.index.time == _EXIT_TIME]

        if not exit_bars.empty:
            exit_bar = exit_bars.iloc[0]
            exit_time = exit_bars.index[0]
            exit_close = float(exit_bar["close"])
        else:
            # Fallback: use the last bar of the session
            last_bar = session_df.iloc[-1]
            exit_time = session_df.index[-1]
            exit_close = float(last_bar["close"])
            logger.warning(
                f"{ticker}: no 15:59 bar found — using last session bar "
                f"at {exit_time.time()} as fallback exit."
            )

        return self.broker.fill_exit(
            ticker=ticker,
            bar_time=exit_time,
            bar_close=exit_close,
            shares=entry_fill.shares,
            session_date=session_date,
            strategy_id=entry_fill.strategy_id,
        )

    # ------------------------------------------------------------------
    # Summary builder
    # ------------------------------------------------------------------

    def _build_summary(
        self,
        session_date: date,
        regime_label: str,
        trades_blocked_by_regime: bool,
    ) -> dict:
        summary = self.risk_engine.get_daily_summary()
        summary["strategy_id"] = STRATEGY_ID
        summary["regime_label"] = regime_label
        summary["trades_blocked_by_regime"] = trades_blocked_by_regime
        return summary


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _extract_session_bars(df: pd.DataFrame, session_date: date) -> pd.DataFrame:
    """
    Slice a ticker DataFrame to regular session hours (09:30–15:59 ET)
    for a specific session date.

    Filters to session_date first, then applies the time window. This is
    required because bar_data DataFrames typically span multiple dates.
    """
    if df.index.tz is None:
        df = df.copy()
        df.index = df.index.tz_localize("UTC").tz_convert("America/New_York")
    elif str(df.index.tz) != "America/New_York":
        df = df.copy()
        df.index = df.index.tz_convert("America/New_York")

    day_mask = df.index.date == session_date
    day_df = df.loc[day_mask]
    if day_df.empty:
        return day_df
    return day_df.between_time(_SESSION_START, _SESSION_END)
